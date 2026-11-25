"""Мраморное тестирование.

* ``materialize`` — подписаться и получить список уведомлений
  ``("N", v)``, ``("E", e)``, ``("C",)``;
* ``hot`` — горячий источник на Subject, воспроизводящий события по ``run()``;
* ``marble`` — прогнать оператор на текстовых «мраморных» диаграммах.

Нотация диаграмм: каждый символ — один тик времени; ``-`` — ничего,
``|`` — завершение, ``#`` — ошибка, любой другой символ — значение
(можно передать словарь ``values`` для подстановки). Несколько событий
в один тик записываются в скобках: ``(ab|)``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .core import Observable
from .subjects import Subject

Notification = tuple[Any, ...]


class MarbleError(Exception):
    """Ошибка, которую порождает символ ``#`` в диаграмме."""

    def __eq__(self, other: object) -> bool:
        """Все MarbleError равны — удобно сравнивать уведомления."""
        return isinstance(other, MarbleError)

    def __hash__(self) -> int:
        """Хеш согласован с ``__eq__``."""
        return hash(MarbleError)


def materialize(observable: Observable) -> list[Notification]:
    """Список уведомлений, полученных подпиской на поток."""
    out: list[Notification] = []
    observable.subscribe(
        lambda v: out.append(("N", v)),
        lambda e: out.append(("E", e)),
        lambda: out.append(("C",)),
    )
    return out


def values(notifications: list[Notification]) -> list[Any]:
    """Только значения из списка уведомлений."""
    return [n[1] for n in notifications if n[0] == "N"]


class Hot:
    """Горячий источник: события отправляются только по команде run()."""

    def __init__(self, *events: Any) -> None:
        """События: ("N", v), ("E", e), ("C",) или просто значения."""
        self.subject = Subject()
        self.events = events

    @property
    def observable(self) -> Observable:
        """Поток, на который подписываются тестируемые операторы."""
        return self.subject

    def run(self) -> None:
        """Воспроизвести события."""
        for ev in self.events:
            _dispatch(self.subject, ev)


def hot(*events: Any) -> Hot:
    """Создать горячий источник."""
    return Hot(*events)


def _dispatch(subject: Subject, ev: Any) -> None:
    """Отправить одно уведомление в субъект."""
    if isinstance(ev, tuple) and ev and ev[0] in ("N", "E", "C"):
        if ev[0] == "N":
            subject.on_next(ev[1])
        elif ev[0] == "E":
            subject.on_error(ev[1])
        else:
            subject.on_completed()
    else:
        subject.on_next(ev)


def parse_marbles(
    diagram: str, values: dict[str, Any] | None = None
) -> list[tuple[int, Notification]]:
    """Разобрать диаграмму в список (тик, уведомление)."""
    vals = values or {}
    events: list[tuple[int, Notification]] = []
    tick, group = 0, False
    for ch in diagram:
        if ch == "(":
            group = True
            continue
        if ch == ")":
            group = False
            tick += 1
            continue
        if ch == "|":
            events.append((tick, ("C",)))
        elif ch == "#":
            events.append((tick, ("E", MarbleError("#"))))
        elif ch != "-":
            events.append((tick, ("N", vals.get(ch, ch))))
        if not group:
            tick += 1
    return events


def render_marbles(
    events: list[tuple[int, Notification]], fmt: Callable[[Any], str] = str
) -> str:
    """Нарисовать диаграмму по списку (тик, уведомление)."""
    by_tick: dict[int, list[str]] = {}
    for t, n in events:
        sym = "|" if n[0] == "C" else "#" if n[0] == "E" else fmt(n[1])
        by_tick.setdefault(t, []).append(sym)
    last = max(by_tick, default=-1)
    cells = []
    for t in range(last + 1):
        syms = by_tick.get(t, [])
        cells.append(
            "-"
            if not syms
            else syms[0]
            if len(syms) == 1
            else "(" + "".join(syms) + ")"
        )
    return "".join(cells)


def marble(
    operator: Callable[..., Observable],
    *diagrams: str,
    values: dict[str, Any] | None = None,
    fmt: Callable[[Any], str] = str,
) -> str:
    """Применить ``operator`` к горячим источникам из диаграмм.

    Возвращает выходную диаграмму. Источники с событиями в одном тике
    обрабатываются в порядке аргументов.
    """
    parsed = [parse_marbles(d, values) for d in diagrams]
    subjects = [Subject() for _ in diagrams]
    clock = {"now": 0}
    out: list[tuple[int, Notification]] = []
    operator(*subjects).subscribe(
        lambda v: out.append((clock["now"], ("N", v))),
        lambda e: out.append((clock["now"], ("E", e))),
        lambda: out.append((clock["now"], ("C",))),
    )
    horizon = max((t for p in parsed for t, _ in p), default=-1)
    for t in range(horizon + 1):
        clock["now"] = t
        for subj, p in zip(subjects, parsed, strict=True):
            for _, n in (e for e in p if e[0] == t):
                _dispatch(subj, n)
    return render_marbles(out, fmt)
