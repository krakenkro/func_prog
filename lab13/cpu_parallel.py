"""Задание 3. CPU-bound задача последовательно, в потоках и в процессах.

Задача — подсчёт простых чисел в диапазоне методом пробного деления.
Измеряется время для 1, 2, 4, 8 рабочих, влияние размера пакета
(chunksize), оценивается доля параллельной части p по закону Амдала.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
)
from functools import partial
from math import isqrt
from pathlib import Path
from statistics import fmean
from typing import NamedTuple

START, COUNT = 10_000_000, 1_500_000
CHUNK_COUNT = 150_000
WORKERS = (1, 2, 4, 8)
CHUNKSIZES = (1, 10, 100, 1_000, 10_000, 37_500)


class Measure(NamedTuple):
    """Одно измерение."""

    kind: str
    workers: int
    chunksize: int
    seconds: float
    primes: int


# ------------------------------------------------------- чистое ядро
def is_prime(n: int) -> bool:
    """Проверка на простоту пробным делением (6k ± 1)."""
    if n < 4:
        return n > 1
    if n % 2 == 0 or n % 3 == 0:
        return False
    return all(n % d and n % (d + 2) for d in range(5, isqrt(n) + 1, 6))


def is_prime_shifted(offset: int, n: int) -> bool:
    """is_prime(n + offset) — функция верхнего уровня для partial."""
    return is_prime(n + offset)


def count_primes(numbers: Iterable[int]) -> int:
    """Число простых среди numbers (последовательно)."""
    return sum(map(is_prime, numbers))


def amdahl(p: float, n: int) -> float:
    """Теоретическое ускорение S(N) = 1 / ((1 − p) + p / N)."""
    return 1.0 / ((1.0 - p) + p / n)


def estimate_p(speedup: float, n: int) -> float:
    """Доля параллельной части из измеренного ускорения (обратный Амдал)."""
    return (1.0 - 1.0 / speedup) / (1.0 - 1.0 / n)


def parallel_count(pool: Executor, numbers: Sequence[int],
                   chunksize: int) -> int:
    """Подсчёт простых в пуле: map + sum (reduce)."""
    return sum(pool.map(is_prime, numbers, chunksize=chunksize))


# ------------------------------------------------------- измерения
def timed(fn: Callable[[], int]) -> tuple[float, int]:
    """Время выполнения fn и её результат."""
    t0 = time.perf_counter()
    result = fn()
    return time.perf_counter() - t0, result


def measure_pool(kind: str, factory: Callable[[int], Executor],
                 numbers: Sequence[int], workers: int,
                 chunksize: int) -> Measure:
    """Время подсчёта в новом пуле (создание пула включено)."""

    def job() -> int:
        with factory(workers) as pool:
            return parallel_count(pool, numbers, chunksize)

    seconds, primes = timed(job)
    return Measure(kind, workers, chunksize, seconds, primes)


def default_chunksize(n: int, workers: int) -> int:
    """Размер пакета: по 4 пакета на рабочего."""
    return max(1, -(-n // (workers * 4)))


def run_benchmarks(numbers: Sequence[int]) -> tuple[Measure, ...]:
    """Все измерения задания 3."""
    seq_t, seq_n = timed(partial(count_primes, numbers))
    rows = [Measure("seq", 1, 0, seq_t, seq_n)]
    for kind, factory in (("thread", ThreadPoolExecutor),
                          ("process", ProcessPoolExecutor)):
        rows += [measure_pool(kind, factory, numbers, w,
                              default_chunksize(len(numbers), w))
                 for w in WORKERS]
    part = numbers[:CHUNK_COUNT]
    rows += [measure_pool("chunk", ProcessPoolExecutor, part, 4, c)
             for c in CHUNKSIZES]
    return tuple(rows)


def lambda_demo(numbers: Sequence[int]) -> tuple[str, int]:
    """Ошибка лямбды в пуле процессов и исправление через partial."""
    with ProcessPoolExecutor(2) as pool:
        try:
            sum(pool.map(lambda n: is_prime(n + 1), numbers))
            error = "ошибки нет"
        except Exception as exc:  # noqa: BLE001 — показываем любую ошибку
            error = f"{type(exc).__name__}: {exc}"
        fixed = sum(pool.map(partial(is_prime_shifted, 1), numbers))
    return error, fixed


def main(json_path: Path | None = None) -> None:
    """Печать таблиц измерений (и сохранение в JSON для графика)."""
    numbers = range(START, START + COUNT)
    rows = run_benchmarks(numbers)
    seq = rows[0]
    print(f"Простых в [{START}, {START + COUNT}): {seq.primes}")
    print(f"последовательно: {seq.seconds:.2f} с\n")
    print("вид      N   время,с  ускорение  простых")
    for r in rows[1:]:
        if r.kind != "chunk":
            print(f"{r.kind:<8}{r.workers:>2}{r.seconds:>9.2f}"
                  f"{seq.seconds / r.seconds:>10.2f}x{r.primes:>9}")
    procs = [r for r in rows if r.kind == "process" and r.workers > 1]
    p = fmean(estimate_p(seq.seconds / r.seconds, r.workers) for r in procs)
    print(f"\nОценка доли параллельной части p = {p:.3f}")
    print("N   измерено  Амдал(p)")
    for r in procs:
        print(f"{r.workers:<4}{seq.seconds / r.seconds:>7.2f}x"
              f"{amdahl(p, r.workers):>9.2f}x")
    print(f"\nВлияние chunksize ({CHUNK_COUNT} чисел, процессы, N = 4):")
    for r in rows:
        if r.kind == "chunk":
            print(f"  chunksize={r.chunksize:<7} {r.seconds:6.2f} с")
    error, fixed = lambda_demo(range(START, START + 1000))
    print(f"\nlambda в ProcessPoolExecutor → {error}")
    print(f"partial(is_prime_shifted, 1) → простых: {fixed}")
    if json_path:
        json_path.write_text(json.dumps(
            {"p": p, "rows": [r._asdict() for r in rows]},
            ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
