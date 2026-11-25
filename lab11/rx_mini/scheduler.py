"""Дополнительное задание: виртуальное время и операторы времени.

``VirtualScheduler`` хранит очередь отложенных действий, упорядоченную по
времени. ``advance_to(t)`` мгновенно «проматывает» время, выполняя все
действия до момента t. Поэтому тесты операторов времени детерминированы
и не требуют реального ожидания.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .core import CompositeDisposable, Disposable, Observable, SafeObserver
from .core import inner as _inner
from .operators import Operator
from .subjects import Subject


@dataclass(order=True)
class _Task:
    """Запланированное действие."""

    time: float
    seq: int
    action: Callable[[], None] = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class VirtualScheduler:
    """Планировщик с виртуальным временем."""

    def __init__(self) -> None:
        """Время начинается с 0."""
        self.now: float = 0
        self._queue: list[_Task] = []
        self._seq = 0

    def schedule(self, delay: float, action: Callable[[], None]) -> Disposable:
        """Выполнить action через delay единиц времени; вернуть отмену."""
        self._seq += 1
        task = _Task(self.now + max(delay, 0), self._seq, action)
        heapq.heappush(self._queue, task)
        return Disposable(lambda: setattr(task, "cancelled", True))

    def advance_to(self, t: float) -> None:
        """Выполнить все действия с временем ≤ t и установить now = t."""
        while self._queue and self._queue[0].time <= t:
            task = heapq.heappop(self._queue)
            if not task.cancelled:
                self.now = task.time
                task.action()
        self.now = max(self.now, t)

    def advance_by(self, dt: float) -> None:
        """Продвинуть время на dt."""
        self.advance_to(self.now + dt)


# ============================ операторы времени ============================
def interval(period: float, scheduler: VirtualScheduler) -> Observable:
    """0, 1, 2, … через каждые period единиц времени."""

    def subscribe(obs: SafeObserver) -> Disposable:
        state: dict[str, Any] = {"n": 0, "task": Disposable()}

        def tick() -> None:
            if obs.is_stopped:
                return
            obs.on_next(state["n"])
            state["n"] += 1
            state["task"] = scheduler.schedule(period, tick)

        state["task"] = scheduler.schedule(period, tick)
        return Disposable(lambda: state["task"].dispose())

    return Observable(subscribe)


def delay(t: float, scheduler: VirtualScheduler) -> Operator:
    """Сдвинуть значения и завершение на t; ошибка — сразу."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            group = CompositeDisposable()
            group.add(
                src.subscribe(
                    _inner(
                        obs,
                        on_next=lambda v: group.add(
                            scheduler.schedule(t, lambda: obs.on_next(v))
                        ),
                        on_completed=lambda: group.add(
                            scheduler.schedule(t, obs.on_completed)
                        ),
                    )
                )
            )
            return group

        return Observable(subscribe)

    return op


def debounce(t: float, scheduler: VirtualScheduler) -> Operator:
    """Выдать значение, только если за ним t единиц не было новых."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state: dict[str, Any] = {
                "task": Disposable(),
                "value": None,
                "has": False,
            }

            def fire() -> None:
                state["has"] = False
                obs.on_next(state["value"])

            def on_next(v: Any) -> None:
                state["task"].dispose()
                state["value"], state["has"] = v, True
                state["task"] = scheduler.schedule(t, fire)

            def on_completed() -> None:
                state["task"].dispose()
                if state["has"]:
                    fire()
                obs.on_completed()

            d = src.subscribe(
                _inner(obs, on_next=on_next, on_completed=on_completed)
            )
            return CompositeDisposable(
                d, Disposable(lambda: state["task"].dispose())
            )

        return Observable(subscribe)

    return op


def throttle_first(t: float, scheduler: VirtualScheduler) -> Operator:
    """Пропустить первое значение и игнорировать следующие в течение t."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state: dict[str, float | None] = {"last": None}

            def on_next(v: Any) -> None:
                last = state["last"]
                if last is None or scheduler.now - last >= t:
                    state["last"] = scheduler.now
                    obs.on_next(v)

            return src.subscribe(_inner(obs, on_next=on_next))

        return Observable(subscribe)

    return op


# ============================ тестовые помощники ===========================
def timed_hot(
    scheduler: VirtualScheduler, *events: tuple[float, tuple[Any, ...]]
) -> Subject:
    """Горячий источник: события (время, уведомление) по расписанию."""
    subject = Subject()
    for at, n in events:

        def emit(n: tuple[Any, ...] = n) -> None:
            if n[0] == "N":
                subject.on_next(n[1])
            elif n[0] == "E":
                subject.on_error(n[1])
            else:
                subject.on_completed()

        scheduler.schedule(at - scheduler.now, emit)
    return subject


def record(
    observable: Observable, scheduler: VirtualScheduler, until: float
) -> list[tuple[float, tuple[Any, ...]]]:
    """Подписаться, промотать время до until и вернуть (время, уведомление)."""
    out: list[tuple[float, tuple[Any, ...]]] = []
    sub = observable.subscribe(
        lambda v: out.append((scheduler.now, ("N", v))),
        lambda e: out.append((scheduler.now, ("E", e))),
        lambda: out.append((scheduler.now, ("C",))),
    )
    scheduler.advance_to(until)
    sub.dispose()
    return out
