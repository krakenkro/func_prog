"""Чистое ядро расчёта рейтинга."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import groupby
from operator import attrgetter
from statistics import fmean, median

from rating.model import (
    DEFAULT_WEIGHTS,
    Entry,
    GroupSummary,
    Ranked,
    StudentScore,
    Weights,
)

KINDS = ("lab", "rk", "exam")
LETTERS = ((90.0, "A"), (75.0, "B"), (60.0, "C"), (50.0, "D"), (0.0, "F"))


def kind_of(task: str) -> str:
    """Вид работы по имени: lab3 → lab, rk1 → rk, exam → exam."""
    kind = task.rstrip("0123456789").lower()
    if kind not in KINDS:
        raise ValueError(f"неизвестный вид работы: {task!r}")
    return kind


def latest(entries: Iterable[Entry]) -> dict[tuple[str, str], Entry]:
    """Последняя запись по паре (студент, работа) — исправления журнала."""
    return {(e.student, e.task): e for e in entries}


def task_max(entries: Iterable[Entry]) -> dict[str, float]:
    """Максимум каждой работы группы (из любой записи о ней)."""
    return {e.task: e.max_score for e in entries}


def student_percent(scores: dict[str, float], maxima: dict[str, float],
                    weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Взвешенный процент: доля набранного по каждому виду работ.

    Несданная работа группы считается нулём; виды работ, которых нет в
    журнале группы, не учитываются (веса нормируются).
    """
    parts = []
    for kind in KINDS:
        tasks = [t for t in maxima if kind_of(t) == kind]
        if tasks:
            got = sum(scores.get(t, 0.0) for t in tasks)
            parts.append((getattr(weights, kind),
                          got / sum(maxima[t] for t in tasks)))
    total_w = sum(w for w, _ in parts)
    if not parts or total_w == 0:
        return 0.0
    return round(100 * sum(w * share for w, share in parts) / total_w, 2)


def score_group(entries: Sequence[Entry],
                weights: Weights = DEFAULT_WEIGHTS,
                ) -> tuple[StudentScore, ...]:
    """Проценты всех студентов одной группы (по алфавиту)."""
    actual = sorted(latest(entries).values(), key=attrgetter("student"))
    maxima = task_max(actual)
    return tuple(
        StudentScore(student, items[0].group,
                     student_percent({e.task: e.score for e in items},
                                     maxima, weights))
        for student, items in (
            (s, list(g)) for s, g in groupby(actual,
                                             key=attrgetter("student")))
    )


def letter(percent: float) -> str:
    """Буквенная оценка по проценту."""
    return next(sym for bound, sym in LETTERS if percent >= bound)


def rank(scores: Iterable[StudentScore]) -> tuple[Ranked, ...]:
    """Общий рейтинг: по убыванию процента; равным — одинаковое место."""
    ordered = sorted(scores, key=lambda s: (-s.percent, s.group, s.student))
    places = {}
    for pos, s in enumerate(ordered, 1):
        places.setdefault(s.percent, pos)
    return tuple(Ranked(places[s.percent], s.student, s.group, s.percent,
                        letter(s.percent)) for s in ordered)


def summarize_group(group: str,
                    scores: Sequence[StudentScore]) -> GroupSummary:
    """Сводка по группе: число студентов, среднее, медиана, лучший."""
    if not scores:
        return GroupSummary(group, 0, 0.0, 0.0, "-")
    values = [s.percent for s in scores]
    best = min(scores, key=lambda s: (-s.percent, s.student)).student
    return GroupSummary(group, len(scores), round(fmean(values), 2),
                        round(median(values), 2), best)
