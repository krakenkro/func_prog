"""Задание 3. Сравнение подходов к неизменяемости словаря.

Словарь из ``N`` записей «изменяется» ``K`` раз, причём сохраняются *все*
версии. Три способа:

(а) ``copy.deepcopy`` перед каждым изменением;
(б) поверхностная копия ``{**d, k: v}``;
(в) ``pyrsistent.pmap.set`` — структурное разделение (HAMT).

Время измеряется отдельным прогоном без tracemalloc (трассировка памяти
сильно замедляет код), память — по tracemalloc для набора всех версий.
"""

from __future__ import annotations

import copy
import sys
import time
import tracemalloc
from collections.abc import Callable
from typing import Any

from pyrsistent import pmap

Strategy = Callable[[Any, int, int], Any]


def build_versions(initial: Any, update: Strategy, changes: int) -> list[Any]:
    """Применить ``changes`` изменений, сохранив все версии в списке."""
    versions = [initial]
    for i in range(changes):
        versions.append(update(versions[-1], i % 10_000, -i))
    return versions


def deepcopy_update(d: dict[int, int], k: int, v: int) -> dict[int, int]:
    """(а) Полная глубокая копия, затем изменение копии."""
    new = copy.deepcopy(d)
    new[k] = v
    return new


def spread_update(d: dict[int, int], k: int, v: int) -> dict[int, int]:
    """(б) Поверхностная копия через распаковку."""
    return {**d, k: v}


def pmap_update(d: Any, k: int, v: int) -> Any:
    """(в) Персистентный словарь: новая версия разделяет почти всё."""
    return d.set(k, v)


STRATEGIES: tuple[
    tuple[str, Callable[[dict[int, int]], Any], Strategy], ...
] = (
    ("copy.deepcopy", dict, deepcopy_update),
    ("{**d, k: v}", dict, spread_update),
    ("pmap.set", pmap, pmap_update),
)


def measure(n: int, changes: int) -> list[tuple[str, float, float]]:
    """Вернуть строки (способ, время в с, пиковая память в МБ)."""
    base = {i: i for i in range(n)}
    rows = []
    for name, make, update in STRATEGIES:
        initial = make(base)
        start = time.perf_counter()
        build_versions(initial, update, changes)
        elapsed = time.perf_counter() - start

        tracemalloc.start()
        versions = build_versions(make(base), update, changes)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del versions
        rows.append((name, elapsed, peak / 2**20))
    return rows


def format_table(rows: list[tuple[str, float, float]]) -> str:
    """Отформатировать результаты как текстовую таблицу."""
    lines = [f"{'Способ':<16}{'Время, с':>10}{'Память, МБ':>13}", "-" * 39]
    lines += [f"{name:<16}{t:>10.3f}{m:>13.1f}" for name, t, m in rows]
    return "\n".join(lines)


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 1_000
    print(f"Словарь из {N} записей, {K} изменений, все версии сохраняются\n")
    print(format_table(measure(N, K)))
