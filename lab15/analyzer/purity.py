"""Эвристический анализатор нечистоты функций на основе модуля ast.

Расширение примера из методических указаний:

* чтение и изменение глобального изменяемого состояния модуля;
* ``del`` элементов и атрибутов, ``+=`` к элементам;
* ввод-вывод: print/input/open, методы файлов (write, read, close),
  sys.exit, а также обращения к time и random;
* вложенные функции анализируются отдельно, без двойного счёта.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterator
from typing import NamedTuple

MUTATING_METHODS = frozenset({
    "append", "extend", "insert", "remove", "pop", "popleft", "clear",
    "sort", "reverse", "update", "setdefault", "add", "discard",
    "appendleft"})
IO_CALLS = frozenset({"print", "input", "open"})
IO_METHODS = frozenset({"write", "read", "readline", "readlines", "close",
                        "write_text", "read_text", "exit"})
NONDET_MODULES = frozenset({"time", "random", "datetime"})
STATE_KINDS = frozenset({"global/nonlocal", "присваивание атрибуту/элементу",
                         "удаление элемента/атрибута", "мутирующий метод"})

Func = ast.FunctionDef | ast.AsyncFunctionDef


class Finding(NamedTuple):
    """Признак нечистоты в функции."""

    function: str
    line: int
    kind: str
    detail: str


class Summary(NamedTuple):
    """Сводка по модулю."""

    functions: int
    pure: int
    findings: int
    state_changes: int
    io_sites: int
    mutable_globals: int


def mutable_globals(tree: ast.Module) -> frozenset[str]:
    """Имена глобальных переменных, инициализированных изменяемым значением."""
    mutable = (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp,
               ast.SetComp)
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and (
                isinstance(node.value, mutable)
                or (isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in ("dict", "list", "set"))):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return frozenset(names)


def own_nodes(func: Func) -> Iterator[ast.AST]:
    """Узлы тела функции без вложенных функций и классов."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    stack: list[ast.AST] = [n for n in func.body
                            if not isinstance(n, nested)]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(child for child in ast.iter_child_nodes(node)
                     if not isinstance(child, nested))


def classify(node: ast.AST, globals_: frozenset[str]) -> tuple[str, str]:
    """Вид нечистоты узла ('' — узел чистый)."""
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return "global/nonlocal", ", ".join(node.names)
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) \
            else [node.target]
        if any(isinstance(t, (ast.Attribute, ast.Subscript))
               for t in targets):
            return "присваивание атрибуту/элементу", ast.unparse(targets[0])
    if isinstance(node, ast.Delete) and any(
            isinstance(t, (ast.Attribute, ast.Subscript))
            for t in node.targets):
        return "удаление элемента/атрибута", ast.unparse(node.targets[0])
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id in IO_CALLS:
            return "ввод-вывод", f"{f.id}()"
        if isinstance(f, ast.Attribute):
            base = f.value.id if isinstance(f.value, ast.Name) else ""
            if base in NONDET_MODULES:
                return "недетерминизм", f"{base}.{f.attr}()"
            if f.attr in IO_METHODS:
                return "ввод-вывод", f".{f.attr}()"
            if f.attr in MUTATING_METHODS:
                return "мутирующий метод", f".{f.attr}()"
    if isinstance(node, ast.Name) and node.id in globals_:
        return "глобальное изменяемое состояние", node.id
    return "", ""


def impurity_findings(source: str) -> tuple[Finding, ...]:
    """Чистая функция: признаки нечистоты по функциям модуля."""
    tree = ast.parse(source)
    globals_ = mutable_globals(tree)
    found = []
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in own_nodes(func):
                kind, detail = classify(node, globals_)
                if kind:
                    found.append(Finding(func.name, getattr(node, "lineno",
                                                            func.lineno),
                                         kind, detail))
    return tuple(sorted(set(found), key=lambda f: (f.function, f.line,
                                                   f.kind, f.detail)))


def function_names(source: str) -> tuple[str, ...]:
    """Имена всех функций модуля."""
    return tuple(n.name for n in ast.walk(ast.parse(source))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))


def purity_summary(source: str) -> Summary:
    """Сводные показатели чистоты модуля."""
    findings = impurity_findings(source)
    names = function_names(source)
    impure = {f.function for f in findings}
    kinds = Counter(f.kind for f in findings)
    return Summary(
        functions=len(names),
        pure=sum(1 for n in names if n not in impure),
        findings=len(findings),
        state_changes=sum(kinds[k] for k in STATE_KINDS),
        io_sites=kinds["ввод-вывод"],
        mutable_globals=len(mutable_globals(ast.parse(source))),
    )
