"""Задание 4. Библиотека pyrsistent.

* конфигурация приложения: freeze → set_in / transform → thaw;
* evolver() для пакетного обновления pvector против последовательных set;
* типизированная запись «Студент» (PRecord) с инвариантами полей;
* неизменяемый граф ``pmap{вершина → pset соседей}`` и поиск в ширину.
"""

from __future__ import annotations

import timeit
from typing import Any

from pyrsistent import (
    InvariantException,
    PMap,
    PRecord,
    PSet,
    PVector,
    field,
    freeze,
    ny,
    pmap,
    pset,
    pvector,
    thaw,
)


# --- 1. Конфигурация -------------------------------------------------------
def raw_config() -> dict[str, Any]:
    """Исходная конфигурация (каждый вызов — новый словарь)."""
    return {
        "app": {"name": "alga", "debug": False},
        "db": {"host": "localhost", "port": 5432},
        "services": [
            {"name": "api", "replicas": 2},
            {"name": "web", "replicas": 1},
        ],
    }


def set_in(structure: PMap, path: list[Any], value: Any) -> PMap:
    """Установить значение по вложенному пути.

    В pyrsistent нет метода ``set_in`` у ``PMap`` (только ``get_in``),
    поэтому он выражен через ``transform``: если вместо функции передать
    значение, transform просто записывает его по пути.
    """
    return structure.transform(path, value)


def update_config(config: PMap) -> PMap:
    """Чистое преобразование конфигурации (исходная версия не меняется)."""
    return set_in(
        set_in(config, ["db", "port"], 6543), ["app", "debug"], True
    ).transform(["services", ny, "replicas"], lambda r: r * 2)


# --- 2. evolver ------------------------------------------------------------
def batch_with_set(v: PVector, n: int) -> PVector:
    """N последовательных ``set`` — n промежуточных версий."""
    for i in range(n):
        v = v.set(i, -i)
    return v


def batch_with_evolver(v: PVector, n: int) -> PVector:
    """Те же n изменений через evolver: одна итоговая версия."""
    e = v.evolver()
    for i in range(n):
        e[i] = -i
    return e.persistent()


# --- 3. PRecord ------------------------------------------------------------
class Student(PRecord):
    """Неизменяемая типизированная запись «Студент» с инвариантами полей."""

    name = field(
        type=str,
        mandatory=True,
        invariant=lambda s: (len(s.strip()) > 0, "имя не пустое"),
    )
    course = field(
        type=int,
        mandatory=True,
        invariant=lambda c: (1 <= c <= 4, "курс от 1 до 4"),
    )
    gpa = field(
        type=float,
        mandatory=True,
        invariant=lambda g: (0.0 <= g <= 4.0, "GPA от 0 до 4"),
    )


# --- 4. Граф ---------------------------------------------------------------
Graph = PMap


def add_edge(g: Graph, u: str, v: str) -> Graph:
    """Новый граф с неориентированным ребром u—v."""
    return g.set(u, g.get(u, pset()).add(v)).set(v, g.get(v, pset()).add(u))


def graph_from_edges(edges: list[tuple[str, str]]) -> Graph:
    """Построить граф из списка рёбер свёрткой."""
    g: Graph = pmap()
    for u, v in edges:
        g = add_edge(g, u, v)
    return g


def bfs(g: Graph, start: str) -> tuple[str, ...]:
    """Порядок обхода в ширину (по уровням, соседи — по алфавиту)."""

    def level(
        frontier: tuple[str, ...], seen: PSet, order: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not frontier:
            return order
        nxt = tuple(
            sorted({n for v in frontier for n in g.get(v, pset())} - set(seen))
        )
        return level(nxt, seen.update(nxt), order + nxt)

    return level((start,), pset([start]), (start,))


if __name__ == "__main__":
    print("=== 1. freeze / set_in / transform / thaw ===")
    cfg = freeze(raw_config())
    cfg2 = update_config(cfg)
    print(
        "тип после freeze:", type(cfg).__name__, type(cfg["services"]).__name__
    )
    print("старая версия:", thaw(cfg))
    print("новая версия: ", thaw(cfg2))
    print(
        "неизменённая ветка 'app.name' разделяется:",
        cfg["app"]["name"] is cfg2["app"]["name"],
    )

    print("\n=== 2. evolver против set (1000 изменений pvector) ===")
    vec = pvector(range(100_000))
    t_set = timeit.timeit(lambda: batch_with_set(vec, 1000), number=20) / 20
    t_evo = (
        timeit.timeit(lambda: batch_with_evolver(vec, 1000), number=20) / 20
    )
    print(f"последовательные set: {t_set * 1000:.2f} мс")
    print(
        f"evolver:              {t_evo * 1000:.2f} мс "
        f"(в {t_set / t_evo:.1f} раза быстрее)"
    )
    print(
        "результаты равны:",
        batch_with_set(vec, 1000) == batch_with_evolver(vec, 1000),
    )
    print("исходный вектор не изменён:", vec[0] == 0 and vec[999] == 999)

    print("\n=== 3. PRecord «Студент» ===")
    s = Student(name="Аружан", course=2, gpa=3.67)
    print("создан:", s)
    print("set возвращает новую запись:", s.set(course=3), "| старая:", s)
    for bad in (
        {"name": "", "course": 1, "gpa": 3.0},
        {"name": "Ерлан", "course": 7, "gpa": 3.0},
        {"name": "Дана", "course": 1, "gpa": 5.0},
    ):
        try:
            Student(**bad)
        except InvariantException as e:
            print("отказ:", bad, "->", e.invariant_errors)

    print("\n=== 4. Неизменяемый граф ===")
    g1 = graph_from_edges(
        [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E")]
    )
    g2 = add_edge(g1, "E", "F")
    print("BFS g1 из A:", bfs(g1, "A"))
    print("BFS g2 из A:", bfs(g2, "A"))
    print("g1 не изменился:", "F" not in g1)
