"""Неизменяемые типы предметной области."""

from __future__ import annotations

from typing import NamedTuple


class Grade(NamedTuple):
    """Оценка одного студента."""

    student: str
    group: str
    score: int


class GroupStat(NamedTuple):
    """Итог по группе: средний балл и статус."""

    group: str
    average: float
    status: str


class Result(NamedTuple):
    """Результат конвейера: строки для экрана и текст файла-отчёта."""

    lines: tuple[str, ...]
    report: str
