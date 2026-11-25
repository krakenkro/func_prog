"""Задание 5. Мониторинг серверов на собственной библиотеке.

* потоки cpu, memory, requests генерируются детерминированно;
* оповещение «CPU > 90 % и память > 80 % одновременно» — combine_latest;
* подавление повторных оповещений — distinct_until_changed;
* скользящее среднее числа запросов за 5 событий — scan (окно) и
  buffer_with_count (пакетное среднее).

Логика — чистая функция ``monitoring(cpu, mem, req)``: потоки → потоки.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from rx_mini import (
    Observable,
    Subject,
    buffer_with_count,
    combine_latest,
    distinct_until_changed,
    filter_,
    map_,
    scan,
    skip,
    start_with,
)

CPU_LIMIT, MEM_LIMIT, WINDOW = 90.0, 80.0, 5


class Streams(NamedTuple):
    """Выходные потоки мониторинга."""

    alerts: Observable
    moving_avg: Observable
    batch_avg: Observable


def is_overloaded(cpu_mem: tuple[float, float]) -> bool:
    """Правило оповещения."""
    cpu, mem = cpu_mem
    return cpu > CPU_LIMIT and mem > MEM_LIMIT


def push_window(window: tuple[float, ...], x: float) -> tuple[float, ...]:
    """Сдвинуть окно из WINDOW последних значений (чистая функция)."""
    return (window + (x,))[-WINDOW:]


def monitoring(cpu: Observable, mem: Observable, req: Observable) -> Streams:
    """Реактивный компонент мониторинга (без побочных эффектов)."""
    alerts = combine_latest(cpu, mem).pipe(
        map_(is_overloaded),
        start_with(False),  # исходное состояние — «норма»
        distinct_until_changed(),  # только смены состояния
        skip(1),  # само исходное состояние — не событие
        map_(
            lambda bad: (
                "ТРЕВОГА: CPU и память перегружены"
                if bad
                else "норма восстановлена"
            )
        ),
    )
    moving_avg = req.pipe(
        scan(push_window, ()),
        filter_(lambda w: len(w) == WINDOW),
        map_(lambda w: round(sum(w) / WINDOW, 1)),
    )
    batch_avg = req.pipe(
        buffer_with_count(WINDOW), map_(lambda b: round(sum(b) / len(b), 1))
    )
    return Streams(alerts, moving_avg, batch_avg)


def generate(n: int) -> tuple[tuple[float, float, int], ...]:
    """Детерминированные метрики (cpu %, память %, запросов) на n тиков."""
    return tuple(
        (
            round(70 + 25 * math.sin(i / 2), 1),
            round(75 + 10 * math.sin(i / 3 + 1), 1),
            100 + (i * 37) % 50,
        )
        for i in range(n)
    )


if __name__ == "__main__":
    cpu, mem, req = Subject(), Subject(), Subject()
    streams = monitoring(cpu, mem, req)
    tick = {"t": 0}
    streams.alerts.subscribe(lambda a: print(f"t={tick['t']:>2}  [!] {a}"))
    streams.moving_avg.subscribe(
        lambda a: print(f"t={tick['t']:>2}  скользящее среднее: {a}")
    )
    streams.batch_avg.subscribe(
        lambda a: print(f"t={tick['t']:>2}  среднее по пакету из 5: {a}")
    )
    for t, (c, m, r) in enumerate(generate(20)):
        tick["t"] = t
        print(f"t={t:>2}  cpu={c:5.1f}  mem={m:5.1f}  req={r}")
        cpu.on_next(c)
        mem.on_next(m)
        req.on_next(r)
