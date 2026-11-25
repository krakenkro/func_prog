"""Дополнительное задание. Универсальный параллельный конвейер.

``parallel_pipeline(steps, data, combine, initial, workers)`` делит данные
на части, каждый процесс применяет к своей части весь конвейер ``steps``
(композицию чистых функций), частичные результаты объединяются
ассоциативной функцией ``combine``. Результат совпадает с
последовательным, если конвейер — гомоморфизм:
``pipe(xs + ys) == combine(pipe(xs), pipe(ys))``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from functools import partial, reduce
from typing import Any

Step = Callable[[Any], Any]


def run_steps(steps: Sequence[Step], chunk: Any) -> Any:
    """Применить шаги по порядку (функция верхнего уровня — для pickle)."""
    return reduce(lambda acc, f: f(acc), steps, chunk)


def split_at(data: Sequence[Any], cuts: Iterable[int]) -> list[Sequence[Any]]:
    """Разбить последовательность по точкам разреза."""
    bounds = [0, *sorted({c for c in cuts if 0 < c < len(data)}), len(data)]
    return [data[a:b] for a, b in zip(bounds, bounds[1:], strict=False)]


def even_cuts(n: int, parts: int) -> range:
    """Точки разреза на ``parts`` примерно равных частей."""
    size = max(1, -(-n // max(1, parts)))
    return range(size, n, size)


def parallel_pipeline(steps: Sequence[Step], data: Sequence[Any],
                      combine: Callable[[Any, Any], Any], initial: Any,
                      workers: int = 4, cuts: Iterable[int] | None = None,
                      pool: Executor | None = None) -> Any:
    """Выполнить конвейер над частями данных в пуле процессов."""
    chunks = split_at(data, even_cuts(len(data), workers)
                      if cuts is None else cuts)
    job = partial(run_steps, tuple(steps))
    if pool is not None:
        return reduce(combine, pool.map(job, chunks), initial)
    with ProcessPoolExecutor(workers) as own:
        return reduce(combine, own.map(job, chunks), initial)


def sequential(steps: Sequence[Step], data: Sequence[Any],
               combine: Callable[[Any, Any], Any], initial: Any) -> Any:
    """Эталон: тот же конвейер над всеми данными сразу."""
    return combine(initial, run_steps(steps, data))


# ------------------------------- примеры конвейеров (верхний уровень)
def parse_ints(lines: Iterable[str]) -> list[int]:
    """Строки → целые, нечисловые строки пропускаются."""
    return [int(s) for s in lines if s.strip().lstrip("-").isdigit()]


def keep_even(xs: Iterable[int]) -> list[int]:
    """Только чётные."""
    return [x for x in xs if x % 2 == 0]


def squares(xs: Iterable[int]) -> list[int]:
    """Квадраты."""
    return [x * x for x in xs]


def words(lines: Iterable[str]) -> list[str]:
    """Слова в нижнем регистре."""
    return [w.lower() for line in lines for w in line.split()]


def add(a: int, b: int) -> int:
    """Ассоциативное сложение."""
    return a + b


def merge_counts(a: Counter[str], b: Counter[str]) -> Counter[str]:
    """Ассоциативное объединение частот."""
    return a + b


SUM_OF_EVEN_SQUARES: tuple[Step, ...] = (parse_ints, keep_even, squares, sum)
WORD_COUNT: tuple[Step, ...] = (words, Counter)


if __name__ == "__main__":
    data = [str(i) if i % 7 else "шум" for i in range(1, 200_001)]
    par = parallel_pipeline(SUM_OF_EVEN_SQUARES, data, add, 0, workers=4)
    seq = sequential(SUM_OF_EVEN_SQUARES, data, add, 0)
    print(f"сумма квадратов чётных: {par} (последовательно {seq})")
    text = ["мама мыла раму", "Раму мыла мама", "ФП это просто"] * 1000
    wc = parallel_pipeline(WORD_COUNT, text, merge_counts, Counter())
    print("частоты слов:", wc.most_common(3))
