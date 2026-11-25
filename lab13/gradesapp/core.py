"""Чистые функции бизнес-логики."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import groupby
from operator import attrgetter
from statistics import fmean

from gradesapp.model import Grade, GroupStat

THRESHOLD = 70.0


def status_of(average: float, threshold: float = THRESHOLD) -> str:
    """«ОК», если средний балл не ниже порога, иначе «РИСК»."""
    return "ОК" if average >= threshold else "РИСК"


def scores_by_group(grades: Iterable[Grade]) -> dict[str, tuple[int, ...]]:
    """Сгруппировать баллы по группам (ключи — в алфавитном порядке)."""
    by_group = attrgetter("group")
    return {
        g: tuple(x.score for x in items)
        for g, items in groupby(sorted(grades, key=by_group), key=by_group)
    }


def group_stats(
    grades: Iterable[Grade], threshold: float = THRESHOLD
) -> tuple[GroupStat, ...]:
    """Средний балл и статус каждой группы, по алфавиту групп."""
    return tuple(
        GroupStat(g, avg, status_of(avg, threshold))
        for g, avg in (
            (g, fmean(s)) for g, s in scores_by_group(grades).items()
        )
    )
