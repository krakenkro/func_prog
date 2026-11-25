"""Задание 2. Реестр форматов отчёта, заполняемый декоратором @formatter.

Словарь ``_registry`` изменяется только при импорте модуля (декоратором);
наружу отдаётся неизменяемое представление ``FORMATTERS``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import MappingProxyType

from gradesapp.model import GroupStat

Formatter = Callable[[tuple[GroupStat, ...], date], str]
_registry: dict[str, Formatter] = {}
FORMATTERS = MappingProxyType(_registry)


def formatter(name: str) -> Callable[[Formatter], Formatter]:
    """Декоратор: зарегистрировать функцию форматирования под именем."""

    def register(fn: Formatter) -> Formatter:
        if name in _registry:
            raise ValueError(f"формат {name!r} уже зарегистрирован")
        _registry[name] = fn
        return fn

    return register


@formatter("txt")
def as_text(stats: tuple[GroupStat, ...], today: date) -> str:
    """Исходный формат: одна строка с датой и числом групп."""
    return f"Отчёт от {today}: групп {len(stats)}\n"


@formatter("csv")
def as_csv(stats: tuple[GroupStat, ...], today: date) -> str:
    """CSV: дата, группа, средний балл, статус."""
    rows = (f"{today},{s.group},{s.average:.1f},{s.status}" for s in stats)
    return "\n".join(("date,group,average,status", *rows)) + "\n"


@formatter("md")
def as_markdown(stats: tuple[GroupStat, ...], today: date) -> str:
    """Таблица Markdown."""
    head = (f"# Отчёт от {today}", "", "| Группа | Средний | Статус |",
            "|---|---:|---|")
    rows = (f"| {s.group} | {s.average:.1f} | {s.status} |" for s in stats)
    return "\n".join((*head, *rows)) + "\n"
