"""Задание 1. Классический паттерн «Наблюдатель» и его ограничения.

``EventSource`` — простейший издатель: список обработчиков и ``emit``.
Датчик температуры имеет трёх подписчиков: журнал, сигнализацию, статистику.
Ниже то же решение на ``Observable`` — для сравнения.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rx_mini import (
    Subject,
    buffer_with_count,
    combine_latest,
    distinct_until_changed,
    map_,
    reduce_,
    skip,
    start_with,
)

Handler = Callable[[Any], None]


class EventSource:
    """Издатель событий: subscribe(handler) -> unsubscribe, emit(value)."""

    def __init__(self) -> None:
        """Пустой список подписчиков."""
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        """Добавить обработчик; вернуть функцию отписки."""
        self._handlers.append(handler)
        return lambda: self._handlers.remove(handler)

    def emit(self, value: Any) -> None:
        """Вызвать всех подписчиков."""
        for h in tuple(self._handlers):
            h(value)


READINGS: tuple[float, ...] = (21.5, 22.0, 35.2, 36.1, 24.0, 23.5, 38.0)
ALARM_LEVEL = 35.0


def classic_demo(readings: tuple[float, ...]) -> list[str]:
    """Решение «в лоб»: каждый подписчик сам фильтрует и хранит состояние."""
    out: list[str] = []
    sensor = EventSource()
    stats = {"n": 0, "sum": 0.0, "max": float("-inf")}  # внешнее состояние
    alarm_on = {"value": False}

    def log(t: float) -> None:
        out.append(f"[журнал] {t:.1f} °C")

    def alarm(t: float) -> None:
        # фильтрация и подавление повторов — внутри подписчика вручную
        now = t > ALARM_LEVEL
        if now != alarm_on["value"]:
            alarm_on["value"] = now
            out.append("[тревога] ВКЛ" if now else "[тревога] выкл")

    def statistics(t: float) -> None:
        stats["n"] += 1
        stats["sum"] += t
        stats["max"] = max(stats["max"], t)

    unsubscribe_log = sensor.subscribe(log)
    sensor.subscribe(alarm)
    sensor.subscribe(statistics)
    for i, t in enumerate(readings):
        if i == 4:
            unsubscribe_log()
        sensor.emit(t)
    out.append(
        f"[статистика] n={stats['n']}, "
        f"среднее={stats['sum'] / stats['n']:.2f}, "
        f"макс={stats['max']:.1f}"
    )
    return out


def reactive_demo(readings: tuple[float, ...]) -> list[str]:
    """То же на Observable: фильтрация, состояние и подавление — операторы."""
    out: list[str] = []
    sensor = Subject()
    log_sub = sensor.subscribe(lambda t: out.append(f"[журнал] {t:.1f} °C"))
    sensor.pipe(
        map_(lambda t: t > ALARM_LEVEL),
        start_with(False),  # исходное состояние — «выкл»
        distinct_until_changed(),  # только смены состояния
        skip(1),  # само исходное состояние не нужно
        map_(lambda on: "[тревога] ВКЛ" if on else "[тревога] выкл"),
    ).subscribe(out.append)
    sensor.pipe(
        reduce_(
            lambda acc, t: (acc[0] + 1, acc[1] + t, max(acc[2], t)),
            (0, 0.0, float("-inf")),
        ),
        map_(
            lambda s: (
                f"[статистика] n={s[0]}, среднее={s[1] / s[0]:.2f}, "
                f"макс={s[2]:.1f}"
            )
        ),
    ).subscribe(out.append)
    for i, t in enumerate(readings):
        if i == 4:
            log_sub.dispose()
        sensor.on_next(t)
    sensor.on_completed()
    return out


def combined_demo() -> list[str]:
    """Задачи, неудобные для EventSource: объединение двух источников.

    «Душно»: температура > 26 и влажность > 70 одновременно; средняя
    температура по окну из 3 измерений.
    """
    out: list[str] = []
    temp, hum = Subject(), Subject()
    combine_latest(temp, hum).pipe(
        map_(lambda th: th[0] > 26 and th[1] > 70),
        distinct_until_changed(),
        map_(lambda stuffy: "душно!" if stuffy else "норма"),
    ).subscribe(lambda s: out.append(f"[климат] {s}"))
    temp.pipe(buffer_with_count(3), map_(lambda w: sum(w) / len(w))).subscribe(
        lambda avg: out.append(f"[окно] средняя {avg:.1f}")
    )
    for t, h in ((24, 60), (27, 65), (28, 75), (29, 80), (25, 80), (24, 50)):
        temp.on_next(t)
        hum.on_next(h)
    return out


if __name__ == "__main__":
    print("=== Классический Наблюдатель ===")
    print("\n".join(classic_demo(READINGS)))
    print("\n=== То же на Observable ===")
    print("\n".join(reactive_demo(READINGS)))
    print("\n=== Объединение двух источников и окно (только Observable) ===")
    print("\n".join(combined_demo()))
