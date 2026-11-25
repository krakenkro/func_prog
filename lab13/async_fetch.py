"""Задание 4. Асинхронная загрузка из 20 имитированных источников.

* конкурентная загрузка — ``asyncio.gather(..., return_exceptions=True)``;
* не более 5 одновременных запросов — ``asyncio.Semaphore(5)``;
* тайм-аут на запрос — ``asyncio.wait_for``;
* результаты агрегирует синхронное чистое ядро ``aggregate``;
* сравнение с последовательной загрузкой.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from typing import NamedTuple


class Source(NamedTuple):
    """Описание имитированного источника."""

    name: str
    delay: float
    fails: bool
    value: int


class Summary(NamedTuple):
    """Итог агрегирования."""

    ok: int
    errors: dict[str, int]
    total: int
    best: str


Fetch = Callable[[Source], Awaitable[int]]


def plan_sources(n: int = 20, seed: int = 4, scale: float = 1.0,
                 fail_rate: float = 0.15) -> tuple[Source, ...]:
    """Детерминированный набор источников (задержки 0.05–0.6 с × scale)."""
    rnd = random.Random(seed)
    return tuple(
        Source(f"src{i:02d}", round(rnd.uniform(0.05, 0.6), 3) * scale,
               rnd.random() < fail_rate, rnd.randint(10, 99))
        for i in range(n)
    )


async def fetch(source: Source) -> int:
    """Имитация запроса: ожидание и, возможно, ошибка соединения."""
    await asyncio.sleep(source.delay)
    if source.fails:
        raise ConnectionError(f"{source.name}: соединение сброшено")
    return source.value


async def guarded(source: Source, sem: asyncio.Semaphore, timeout: float,
                  fetch_fn: Fetch) -> int:
    """Запрос под семафором и с тайм-аутом."""
    async with sem:
        return await asyncio.wait_for(fetch_fn(source), timeout)


async def fetch_all(sources: Sequence[Source], limit: int = 5,
                    timeout: float = 0.5,
                    fetch_fn: Fetch = fetch) -> list[int | BaseException]:
    """Конкурентная загрузка; исключения возвращаются как значения."""
    sem = asyncio.Semaphore(limit)
    return await asyncio.gather(
        *(guarded(s, sem, timeout, fetch_fn) for s in sources),
        return_exceptions=True,
    )


async def fetch_sequential(sources: Sequence[Source], timeout: float = 0.5,
                           fetch_fn: Fetch = fetch,
                           ) -> list[int | BaseException]:
    """Последовательная загрузка с той же обработкой ошибок."""
    results: list[int | BaseException] = []
    for s in sources:
        try:
            results.append(await asyncio.wait_for(fetch_fn(s), timeout))
        except Exception as exc:  # noqa: BLE001 — ошибка как значение
            results.append(exc)
    return results


def aggregate(sources: Sequence[Source],
              results: Sequence[int | BaseException]) -> Summary:
    """Чистое ядро: успехи, ошибки по типам, сумма, лучший источник."""
    pairs = tuple(zip(sources, results, strict=True))
    good = tuple((s.name, r) for s, r in pairs
                 if not isinstance(r, BaseException))
    errors = Counter(type(r).__name__ for _, r in pairs
                     if isinstance(r, BaseException))
    best = max(good, key=lambda p: p[1])[0] if good else "-"
    return Summary(len(good), dict(sorted(errors.items())),
                   sum(v for _, v in good), best)


async def compare(sources: Sequence[Source]) -> None:
    """Оболочка: замер обоих вариантов и печать итогов."""
    for title, coro in (("конкурентно (Semaphore(5))", fetch_all(sources)),
                        ("последовательно", fetch_sequential(sources))):
        t0 = time.perf_counter()
        results = await coro
        elapsed = time.perf_counter() - t0
        print(f"{title}: {elapsed:.2f} с → {aggregate(sources, results)}")


if __name__ == "__main__":
    src = plan_sources()
    for s in src:
        print(f"  {s.name}: задержка {s.delay:.3f} с"
              f"{'  ошибка' if s.fails else ''}"
              f"{'  > тайм-аута' if s.delay > 0.5 else ''}")
    print(f"сумма задержек: {sum(s.delay for s in src):.2f} с")
    asyncio.run(compare(src))
