"""Задание 5. Интеграция RxPY с asyncio.

Каждые 0,2 с асинхронный «загрузчик» опрашивает три имитированных
источника (``async def fetch`` с ``asyncio.sleep``), результаты попадают
в реактивный поток (``rx.from_future`` + ``asyncio.ensure_future``),
объединяются ``zip`` по номеру опроса, и вычисляется скользящее среднее.
Через заданное время ``take_until(timer)`` завершает поток, после чего
все подписки освобождаются.

Чистая часть — ``aggregate`` и ``summary`` (потоки → потоки), её можно
тестировать на TestScheduler; асинхронная «оболочка» — ``run_loader``.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.abc import SchedulerBase
from reactivex.scheduler.eventloop import AsyncIOScheduler
from reactivex.testing import TestScheduler
from rx_helpers import diagram, run

SOURCES: tuple[str, ...] = ("датчик-A", "датчик-B", "датчик-C")
LATENCY: Mapping[str, float] = MappingProxyType(
    {"датчик-A": 0.03, "датчик-B": 0.08, "датчик-C": 0.05}
)  # задержка ответа, с (неизменяемое отображение)
WINDOW = 3
Reading = tuple[str, int, float]  # (источник, номер опроса, значение)


def reading(source: str, tick: int) -> Reading:
    """Детерминированное показание источника в опросе ``tick``."""
    phase = SOURCES.index(source)
    return source, tick, round(20 + 5 * math.sin(tick / 2 + phase), 2)


async def fetch(source: str, tick: int) -> Reading:
    """Имитация сетевого запроса: задержка и показание."""
    await asyncio.sleep(LATENCY[source])
    return reading(source, tick)


def push_window(window: tuple[float, ...], x: float) -> tuple[float, ...]:
    """Окно из WINDOW последних значений."""
    return (window + (x,))[-WINDOW:]


def aggregate(rounds: Observable) -> Observable:
    """(показания трёх источников за опрос) → (опрос, среднее, скольз. ср.)."""

    def mean(readings: tuple[Reading, ...]) -> tuple[int, float]:
        return readings[0][1], round(
            sum(r[2] for r in readings) / len(readings), 2
        )

    return rounds.pipe(
        ops.map(mean),
        ops.scan(
            lambda acc, tm: (tm[0], tm[1], push_window(acc[2], tm[1])),
            (0, 0.0, ()),
        ),
        ops.map(
            lambda acc: (acc[0], acc[1], round(sum(acc[2]) / len(acc[2]), 2))
        ),
    )


def summary(aggregated: Observable) -> Observable:
    """Итоговая сводка при завершении потока."""
    return aggregated.pipe(
        ops.reduce(
            lambda acc, x: (acc[0] + 1, min(acc[1], x[1]), max(acc[2], x[1])),
            (0, math.inf, -math.inf),
        ),
        ops.map(
            lambda s: f"сводка: опросов {s[0]}, среднее min={s[1]}, max={s[2]}"
        ),
    )


Request = Callable[[str, int], Observable]


def asyncio_request(source: str, tick: int) -> Observable:
    """Запрос через asyncio: корутина fetch → future → Observable."""
    return rx.from_future(asyncio.ensure_future(fetch(source, tick)))


def rounds_stream(ticks: Observable, request: Request) -> Observable:
    """Ответы трёх источников на каждый тик, объединённые zip по опросу."""
    return rx.zip(
        *(
            ticks.pipe(ops.flat_map(lambda i, s=s: request(s, i)))
            for s in SOURCES
        )
    )


def virtual_request(scheduler: SchedulerBase, scale: float) -> Request:
    """Модель запроса в виртуальном времени (задержка × scale единиц)."""
    return lambda source, tick: rx.timer(
        LATENCY[source] * scale, scheduler=scheduler
    ).pipe(ops.map(lambda _: reading(source, tick)))


async def run_loader(
    duration: float = 1.1, period: float = 0.2, echo: bool = True
) -> list[Any]:
    """Запустить загрузчик на ``duration`` секунд и вернуть результаты."""
    loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler(loop)
    done: asyncio.Future[None] = loop.create_future()
    started = time.perf_counter()
    out: list[Any] = []

    def emit(item: Any) -> None:
        out.append(item)
        if echo:
            print(f"[{time.perf_counter() - started:4.2f} с] {item}")

    ticks = rx.interval(period, scheduler=scheduler).pipe(
        ops.take_until(rx.timer(duration, scheduler=scheduler)), ops.share()
    )  # один таймер на все источники
    rounds = rounds_stream(ticks, asyncio_request).pipe(
        ops.share()
    )  # каждый fetch — ровно один раз
    aggregated = aggregate(rounds).pipe(ops.share())
    subscriptions = [
        rounds.subscribe(
            lambda r: emit(
                "опрос "
                + str(r[0][1])
                + ": "
                + ", ".join(f"{s}={v}" for s, _, v in r)
            ),
            scheduler=scheduler,
        ),
        aggregated.subscribe(
            lambda a: emit(
                f"опрос {a[0]}: среднее {a[1]}, скользящее ({WINDOW}) {a[2]}"
            ),
            scheduler=scheduler,
        ),
        summary(aggregated).subscribe(
            emit,
            on_error=lambda e: done.set_exception(e),
            on_completed=lambda: done.set_result(None),
            scheduler=scheduler,
        ),
    ]
    try:
        await asyncio.wait_for(done, duration + 2)
    finally:
        for sub in subscriptions:  # корректная отписка от всего
            sub.dispose()
    emit("все подписки освобождены, загрузчик остановлен")
    return out


def marble_demo() -> str:
    """Мраморная диаграмма загрузчика на TestScheduler.

    Время масштабировано: 1 с = 100 единиц, период 0,2 с = 20 единиц,
    работа 1,1 с = 110 единиц; 1 символ диаграммы = 2 единицы (20 мс).
    """

    def build(s: TestScheduler) -> Observable:
        ticks = rx.interval(20, scheduler=s).pipe(
            ops.take_until(rx.timer(110, scheduler=s)), ops.share()
        )
        request = virtual_request(s, 100)
        tagged = [ticks.pipe(ops.map(lambda i: ("тик", i)))]
        tagged += [
            ticks.pipe(
                ops.flat_map(lambda i, src=src: request(src, i)),
                ops.map(lambda r: (r[0], r[1])),
            )
            for src in SOURCES
        ]
        tagged.append(
            rounds_stream(ticks, request).pipe(
                ops.map(lambda r: ("zip", r[0][1]))
            )
        )
        return rx.merge(*tagged)

    events = run(build)
    rows = ["тик", *SOURCES, "zip"]
    lines = []
    for row in rows:
        own = [(t, k, v) for t, k, v in events if k == "N" and v[0] == row]
        lines.append(
            f"{row:<9} "
            + diagram(own, step=2, end=310, fmt=lambda v: str(v[1]))
        )
    done = [(t, k, v) for t, k, v in events if k == "C"]
    lines.append(f"{'итог':<9} " + diagram(done, step=2, end=310))
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(run_loader())
    print("\nМраморная диаграмма (TestScheduler, 1 символ = 20 мс):")
    print(marble_demo())
