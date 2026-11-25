"""Неизменяемые типы предметной области рейтинга."""

from __future__ import annotations

from typing import NamedTuple


class Entry(NamedTuple):
    """Запись журнала: балл студента за работу."""

    student: str
    group: str
    task: str
    score: float
    max_score: float


class Weights(NamedTuple):
    """Веса видов работ в рейтинге (сериализуемы для процессов)."""

    lab: float = 0.3
    rk: float = 0.3
    exam: float = 0.4


DEFAULT_WEIGHTS = Weights()


class StudentScore(NamedTuple):
    """Рейтинговый процент студента."""

    student: str
    group: str
    percent: float


class GroupResult(NamedTuple):
    """Результат обработки журнала одной группы."""

    group: str
    scores: tuple[StudentScore, ...]
    errors: tuple[str, ...]


class Ranked(NamedTuple):
    """Строка общего рейтинга."""

    rank: int
    student: str
    group: str
    percent: float
    letter: str


class GroupSummary(NamedTuple):
    """Сводка по группе."""

    group: str
    students: int
    mean: float
    median: float
    best: str


class RatingReport(NamedTuple):
    """Итог конвейера."""

    ranking: tuple[Ranked, ...]
    groups: tuple[GroupSummary, ...]
    errors: tuple[str, ...]
