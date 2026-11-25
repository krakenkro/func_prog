"""Реактивные ячейки (как в электронной таблице).

``Cell(value)`` — ячейка-источник, ``Cell.formula(f, *deps)`` — вычисляемая.
При ``set`` пересчитываются все зависимые ячейки в *топологическом порядке*
(по рангу — длине самого длинного пути от источников), каждая не более одного
раза за изменение. Поэтому в «ромбе» A → B, A → C, (B, C) → D ячейка D
пересчитывается один раз и никогда не видит «полуобновлённых» значений
(нет «глитчей»).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .core import Disposable, Observable
from .operators import start_with
from .subjects import Subject


class Cell:
    """Реактивная ячейка."""

    def __init__(
        self,
        value: Any = None,
        formula: Callable[..., Any] | None = None,
        deps: tuple[Cell, ...] = (),
        name: str = "",
    ) -> None:
        """Создать ячейку; для формулы значение вычисляется сразу."""
        self.name = name
        self._formula = formula
        self._deps = deps
        self._dependents: list[Cell] = []
        self._changes = Subject()
        self.rank = 1 + max((d.rank for d in deps), default=-1)
        self.recompute_count = 0
        for d in deps:
            d._dependents.append(self)
        self._value = formula(*(d.value for d in deps)) if formula else value

    @classmethod
    def formula(
        cls, f: Callable[..., Any], *deps: Cell, name: str = ""
    ) -> Cell:
        """Вычисляемая ячейка f(*значения deps)."""
        return cls(None, f, deps, name)

    @property
    def value(self) -> Any:
        """Текущее значение."""
        return self._value

    @property
    def is_source(self) -> bool:
        """Является ли ячейка источником (а не формулой)."""
        return self._formula is None

    def set(self, value: Any) -> None:
        """Изменить ячейку-источник и распространить изменение."""
        transaction((self, value))

    def subscribe(self, on_change: Callable[[Any], None]) -> Disposable:
        """Подписаться на изменения значения."""
        return self._changes.subscribe(on_change)

    def observe(self) -> Observable:
        """Поток значений: текущее, затем все изменения."""
        return self._changes.pipe(start_with(self._value))

    def _recompute(self) -> bool:
        """Пересчитать формулу; True, если значение изменилось."""
        assert self._formula is not None
        self.recompute_count += 1
        new = self._formula(*(d.value for d in self._deps))
        changed = new != self._value
        self._value = new
        return changed

    def __repr__(self) -> str:
        """Cell(name=value)."""
        return f"Cell({self.name or '?'}={self._value!r})"


def _affected(roots: tuple[Cell, ...]) -> list[Cell]:
    """Все транзитивно зависимые ячейки (без повторов)."""
    seen: dict[int, Cell] = {}
    stack = [d for r in roots for d in r._dependents]
    while stack:
        c = stack.pop()
        if id(c) not in seen:
            seen[id(c)] = c
            stack.extend(c._dependents)
    return sorted(seen.values(), key=lambda c: c.rank)


def transaction(*assignments: tuple[Cell, Any]) -> None:
    """Атомарно изменить несколько источников и пересчитать один раз."""
    for cell, _ in assignments:
        if not cell.is_source:
            raise TypeError(f"{cell!r} — формула, её нельзя задать напрямую")
    changed = {id(c) for c, v in assignments if v != c.value}
    roots = tuple(c for c, _ in assignments if id(c) in changed)
    for cell, value in assignments:
        cell._value = value
    notify = list(roots)
    for cell in _affected(roots):
        if any(id(d) in changed for d in cell._deps) and cell._recompute():
            changed.add(id(cell))
            notify.append(cell)
    for cell in notify:  # уведомления — после пересчёта
        cell._changes.on_next(cell.value)
