"""Общие помощники ЛР 12: запуск на TestScheduler и мраморные диаграммы."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from reactivex import Observable
from reactivex.notification import OnCompleted, OnError, OnNext
from reactivex.testing import ReactiveTest, TestScheduler
from reactivex.testing.recorded import Recorded

on_next = ReactiveTest.on_next
on_completed = ReactiveTest.on_completed
on_error = ReactiveTest.on_error

SUBSCRIBED = 200  # момент подписки в TestScheduler.start по умолчанию


def run(
    build: Callable[[TestScheduler], Observable], disposed: int = 1000
) -> list[tuple[float, str, Any]]:
    """Построить поток на новом TestScheduler и вернуть его уведомления.

    ``build(scheduler)`` создаёт источники (``create_hot_observable``) и
    тестируемую цепочку. Результат — список (время, вид, значение), где
    вид — "N", "E" или "C".
    """
    scheduler = TestScheduler()
    result = scheduler.start(lambda: build(scheduler), disposed=disposed)
    return [simplify(m) for m in result.messages]


def simplify(m: Recorded[Any]) -> tuple[float, str, Any]:
    """Recorded → (время, "N"/"E"/"C", значение или ошибка)."""
    v = m.value
    if isinstance(v, OnNext):
        return (m.time, "N", v.value)
    if isinstance(v, OnError):
        return (m.time, "E", v.exception)
    assert isinstance(v, OnCompleted)
    return (m.time, "C", None)


def values(events: Iterable[tuple[float, str, Any]]) -> list[Any]:
    """Только значения."""
    return [v for _, kind, v in events if kind == "N"]


def times(events: Iterable[tuple[float, str, Any]]) -> list[float]:
    """Моменты всех уведомлений."""
    return [t for t, _, _ in events]


def diagram(
    events: Iterable[tuple[float, str, Any]],
    start: int = SUBSCRIBED,
    end: int = 0,
    step: int = 10,
    fmt: Callable[[Any], str] = str,
) -> str:
    """Нарисовать «мраморную» диаграмму: один символ — ``step`` единиц.

    Значение рисуется ``fmt(value)``; несколько событий в одной клетке —
    в скобках; ``|`` — завершение, ``#`` — ошибка.
    """
    cells: dict[int, list[str]] = {}
    for t, kind, v in events:
        sym = "|" if kind == "C" else "#" if kind == "E" else fmt(v)
        cells.setdefault(int((t - start) // step), []).append(sym)
    last = max(list(cells) + [int((end - start) // step) if end else -1])
    out = []
    for i in range(last + 1):
        syms = cells.get(i, [])
        out.append(
            "-"
            if not syms
            else syms[0]
            if len(syms) == 1
            else "(" + "".join(syms) + ")"
        )
    return "".join(out)


def recorded_events(*msgs: Recorded[Any]) -> list[tuple[float, str, Any]]:
    """Диаграмма входного горячего источника из on_next(...) и т.п."""
    return [simplify(m) for m in msgs]
