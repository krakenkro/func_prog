"""Анализатор нечистоты (ast) и метрики (radon)."""

from pathlib import Path

from analyzer.metrics import complexity_table, measure
from analyzer.purity import impurity_findings, mutable_globals, purity_summary

LEGACY = Path(__file__).resolve().parents[1] / "legacy" / "monitor_legacy.py"

IMPERATIVE = '''
totals = {}
def process(orders):
    global totals
    for o in orders:
        totals.setdefault(o["city"], 0)
        totals[o["city"]] += o["sum"]
    orders.sort(key=lambda o: o["sum"])
    print("готово", len(orders))
    return totals
'''

FUNCTIONAL = '''
from itertools import groupby
from operator import itemgetter
def totals_by_city(orders):
    key = itemgetter("city")
    return {c: sum(o["sum"] for o in g)
            for c, g in groupby(sorted(orders, key=key), key=key)}
def by_sum(orders):
    return sorted(orders, key=itemgetter("sum"))
'''


def test_example_from_manual() -> None:
    """Пример методички: 5 признаков + чтение глобального состояния."""
    kinds = [f.kind for f in impurity_findings(IMPERATIVE)]
    assert {"global/nonlocal", "мутирующий метод", "ввод-вывод",
            "присваивание атрибуту/элементу",
            "глобальное изменяемое состояние"} == set(kinds)
    assert purity_summary(FUNCTIONAL).pure == 2
    assert purity_summary(FUNCTIONAL).findings == 0


def test_nested_functions_not_double_counted() -> None:
    """Находка во вложенной функции относится только к ней."""
    src = "def outer():\n    def inner(xs):\n        xs.append(1)\n" \
          "    return inner\n"
    assert [(f.function, f.kind) for f in impurity_findings(src)] == \
        [("inner", "мутирующий метод")]
    assert purity_summary(src).pure == 1


def test_extended_kinds() -> None:
    """del, файлы, time/random, sys.exit."""
    src = ("import time, sys\n"
           "def f(d, fh):\n    del d['k']\n    fh.write('x')\n"
           "    t = time.time()\n    sys.exit(1)\n")
    kinds = {f.kind for f in impurity_findings(src)}
    assert kinds == {"удаление элемента/атрибута", "ввод-вывод",
                     "недетерминизм"}


def test_mutable_globals() -> None:
    """Изменяемые глобальные: литералы и dict()/list()/set()."""
    import ast
    tree = ast.parse("A = {}\nB = []\nC = set()\nD = 1\nE = (1,)\n")
    assert mutable_globals(tree) == {"A", "B", "C"}


def test_legacy_metrics() -> None:
    """Метрики исходного решения фиксируются тестом."""
    m = measure({"legacy": LEGACY.read_text(encoding="utf-8")})
    assert (m.functions, m.pure, m.mutable_globals) == (4, 0, 9)
    assert m.max_cc == 16 and m.worst in ("handle", "main")
    assert complexity_table(LEGACY.read_text(encoding="utf-8"))[0][2] == 16
