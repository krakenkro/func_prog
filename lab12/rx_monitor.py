"""Задание 1. Мониторинг серверов (ЛР 11, задание 5) средствами RxPY.

Тот же компонент «потоки → потоки», но все операторы — из библиотеки:
``rx.combine_latest``, ``ops.map``, ``ops.start_with``,
``ops.distinct_until_changed``, ``ops.skip``, ``ops.scan``, ``ops.filter``,
``ops.buffer_with_count``, ``ops.share``.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.subject import Subject
from reactivex.testing import TestScheduler
from rx_helpers import (
    diagram,
    on_completed,
    on_next,
    recorded_events,
    run,
)

CPU_LIMIT, MEM_LIMIT, WINDOW = 90.0, 80.0, 5


class Streams(NamedTuple):
    """Выходные потоки мониторинга."""

    alerts: Observable
    moving_avg: Observable
    batch_avg: Observable


def is_overloaded(cpu_mem: tuple[float, float]) -> bool:
    """Правило оповещения: CPU > 90 % и память > 80 % одновременно."""
    cpu, mem = cpu_mem
    return cpu > CPU_LIMIT and mem > MEM_LIMIT


def push_window(window: tuple[float, ...], x: float) -> tuple[float, ...]:
    """Окно из WINDOW последних значений."""
    return (window + (x,))[-WINDOW:]


def monitoring(cpu: Observable, mem: Observable, req: Observable) -> Streams:
    """Реактивный компонент мониторинга (без побочных эффектов)."""
    alerts = rx.combine_latest(cpu, mem).pipe(
        ops.map(is_overloaded),
        ops.start_with(False),
        ops.distinct_until_changed(),
        ops.skip(1),
        ops.map(
            lambda bad: (
                "ТРЕВОГА: CPU и память перегружены"
                if bad
                else "норма восстановлена"
            )
        ),
    )
    shared_req = req.pipe(ops.share())
    moving_avg = shared_req.pipe(
        ops.scan(push_window, ()),
        ops.filter(lambda w: len(w) == WINDOW),
        ops.map(lambda w: round(sum(w) / WINDOW, 1)),
    )
    batch_avg = shared_req.pipe(
        ops.buffer_with_count(WINDOW),
        ops.map(lambda b: round(sum(b) / len(b), 1)),
    )
    return Streams(alerts, moving_avg, batch_avg)


def generate(n: int) -> tuple[tuple[float, float, int], ...]:
    """Те же детерминированные метрики, что и в ЛР 11."""
    return tuple(
        (
            round(70 + 25 * math.sin(i / 2), 1),
            round(75 + 10 * math.sin(i / 3 + 1), 1),
            100 + (i * 37) % 50,
        )
        for i in range(n)
    )


# --------------------------- мраморная диаграмма ---------------------------
CPU_MSGS = (
    on_next(210, 50.0),
    on_next(230, 95.0),
    on_next(260, 92.0),
    on_next(290, 60.0),
    on_completed(320),
)
MEM_MSGS = (on_next(205, 85.0), on_next(250, 88.0), on_completed(320))
REQ_MSGS = tuple(on_next(210 + 10 * i, 10 * (i + 1)) for i in range(10)) + (
    on_completed(320),
)


def marble_demo() -> str:
    """Диаграммы мониторинга на TestScheduler (1 символ = 10 единиц)."""

    def build(
        s: TestScheduler, pick: Callable[[Streams], Observable]
    ) -> Observable:
        return pick(
            monitoring(
                s.create_hot_observable(*CPU_MSGS),
                s.create_hot_observable(*MEM_MSGS),
                s.create_hot_observable(*REQ_MSGS),
            )
        )

    def level(limit: float) -> Callable[[float], str]:
        return lambda v: "H" if v > limit else "L"

    rows = (
        (
            "cpu (H > 90)",
            diagram(recorded_events(*CPU_MSGS), fmt=level(CPU_LIMIT)),
        ),
        (
            "mem (H > 80)",
            diagram(recorded_events(*MEM_MSGS), fmt=level(MEM_LIMIT)),
        ),
        (
            "оповещения",
            diagram(
                run(lambda s: build(s, lambda m: m.alerts)),
                fmt=lambda a: "A" if a[0] == "Т" else "n",
            ),
        ),
        ("запросы", diagram(recorded_events(*REQ_MSGS), fmt=lambda v: "r")),
        (
            "скольз. ср.",
            diagram(
                run(lambda s: build(s, lambda m: m.moving_avg)),
                fmt=lambda v: "m",
            ),
        ),
        (
            "пакет из 5",
            diagram(
                run(lambda s: build(s, lambda m: m.batch_avg)),
                fmt=lambda v: "b",
            ),
        ),
    )
    return "\n".join(f"  {name:<12} {d}" for name, d in rows)


# ------------------- сравнение с rx_mini (ЛР 11) ---------------------------
Step = tuple[str, str, Any]  # (поток cpu/mem, вид N/E/C, значение)
SCENARIOS: tuple[tuple[str, tuple[Step, ...], bool], ...] = (
    (
        "завершение источников",
        (
            ("cpu", "N", 95.0),
            ("mem", "N", 85.0),
            ("cpu", "N", 50.0),
            ("cpu", "C", None),
            ("mem", "C", None),
        ),
        True,
    ),
    (
        "ошибка источника",
        (
            ("cpu", "N", 95.0),
            ("mem", "N", 85.0),
            ("cpu", "E", ValueError("датчик")),
            ("cpu", "N", 10.0),
        ),
        True,
    ),
    ("ошибка в функции map", (("mem", "N", 85.0), ("cpu", "N", None)), True),
    (
        "ошибка без on_error",
        (("cpu", "N", 95.0), ("cpu", "E", ValueError("датчик"))),
        False,
    ),
)


def drive(
    subject_cls: type,
    monitor: Callable[..., Any],
    steps: tuple[Step, ...],
    with_on_error: bool,
) -> str:
    """Прогнать сценарий через компонент мониторинга данной библиотеки."""
    cpu, mem = subject_cls(), subject_cls()
    out: list[str] = []
    alerts = monitor(cpu, mem, subject_cls()).alerts

    def on_value(a: str) -> None:
        out.append("A" if a.startswith("ТРЕВОГА") else "n")

    if with_on_error:
        alerts.subscribe(
            on_value,
            lambda e: out.append(f"E:{type(e).__name__}"),
            lambda: out.append("C"),
        )
    else:
        alerts.subscribe(on_value)
    streams = {"cpu": cpu, "mem": mem}
    try:
        for name, kind, value in steps:
            target = streams[name]
            if kind == "N":
                target.on_next(value)
            elif kind == "E":
                target.on_error(value)
            else:
                target.on_completed()
    except Exception as e:  # noqa: BLE001 - фиксируем, что ошибка «всплыла»
        out.append(f"исключение {type(e).__name__} у источника")
    return " ".join(out) or "—"


def compare_with_rx_mini() -> list[tuple[str, str, str]]:
    """(сценарий, результат rx_mini, результат RxPY)."""
    lab11 = str(Path(__file__).resolve().parents[1] / "lab11")
    if lab11 not in sys.path:
        sys.path.insert(0, lab11)
    import rx_mini  # модуль ЛР 11 (путь добавлен выше)
    import server_monitor

    return [
        (
            title,
            drive(rx_mini.Subject, server_monitor.monitoring, steps, handler),
            drive(Subject, monitoring, steps, handler),
        )
        for title, steps, handler in SCENARIOS
    ]


if __name__ == "__main__":
    cpu, mem, req = Subject(), Subject(), Subject()
    streams = monitoring(cpu, mem, req)
    tick = {"t": 0}
    streams.alerts.subscribe(lambda a: print(f"t={tick['t']:>2}  [!] {a}"))
    streams.moving_avg.subscribe(
        lambda a: print(f"t={tick['t']:>2}  скользящее среднее: {a}")
    )
    streams.batch_avg.subscribe(
        lambda a: print(f"t={tick['t']:>2}  среднее по пакету из 5: {a}"),
        on_completed=lambda: print("поток запросов завершён"),
    )
    for t, (c, m, r) in enumerate(generate(20)):
        tick["t"] = t
        cpu.on_next(c)
        mem.on_next(m)
        req.on_next(r)
    req.on_completed()

    print("\nМраморная диаграмма (TestScheduler, 1 символ = 10 единиц):")
    print(marble_demo())
    print("\nОшибки и завершение: rx_mini (ЛР 11) против RxPY")
    print(f"  {'сценарий':<24}{'rx_mini':<22}RxPY")
    for title, mini, rxpy in compare_with_rx_mini():
        print(f"  {title:<24}{mini:<22}{rxpy}")
