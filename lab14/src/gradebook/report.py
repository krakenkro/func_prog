"""Форматы отчёта и сводная статистика (чистые функции)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from statistics import fmean
from types import MappingProxyType
from typing import NamedTuple

from gradebook.model import Final


class GroupStats(NamedTuple):
    """Сводка по группе."""

    group: str
    students: int
    mean_total: float
    passed: int
    letters: dict[str, int]


def group_stats(rows: Sequence[Final]) -> tuple[GroupStats, ...]:
    """Статистика по группам."""
    groups = sorted({r.group for r in rows})
    return tuple(
        GroupStats(g, len(rs), round(fmean(r.total for r in rs), 2),
                   sum(r.status == "сдано" for r in rs),
                   dict(sorted(Counter(r.letter for r in rs).items())))
        for g in groups
        for rs in ([r for r in rows if r.group == g],))


def _exam(f: Final) -> str:
    return "-" if f.exam is None else f"{f.exam:g}"


def as_txt(rows: Sequence[Final]) -> str:
    """Текстовая таблица."""
    head = (f"{'Студент':<12}{'Группа':<8}{'Лаб':>6}{'РК':>7}{'Допуск':>8}"
            f"{'Экз,%':>7}{'Итог':>8}  Оценка  Статус")
    lines = [f"{f.student:<12}{f.group:<8}{f.labs:>6.2f}{f.rk:>7.2f}"
             f"{f.admission:>8.2f}{_exam(f):>7}{f.total:>8.2f}  "
             f"{f.letter:<6}  {f.status}" for f in rows]
    return "\n".join((head, *lines)) + "\n"


def as_csv(rows: Sequence[Final]) -> str:
    """CSV для электронных таблиц."""
    lines = [f"{f.student},{f.group},{f.labs},{f.rk},{f.admission},"
             f"{_exam(f)},{f.total},{f.letter},{f.gpa},{f.status}"
             for f in rows]
    return "\n".join(("student,group,labs,rk,admission,exam,total,letter,"
                      "gpa,status", *lines)) + "\n"


def as_md(rows: Sequence[Final]) -> str:
    """Таблица Markdown."""
    lines = [f"| {f.student} | {f.group} | {f.total:.2f} | {f.letter} | "
             f"{f.word} | {f.status} |" for f in rows]
    return "\n".join(("| Студент | Группа | Итог | Буква | Оценка | Статус |",
                      "|---|---|---:|---|---|---|", *lines)) + "\n"


FORMATS: MappingProxyType[str, Callable[[Sequence[Final]], str]] = \
    MappingProxyType({"txt": as_txt, "csv": as_csv, "md": as_md})


def render(rows: Sequence[Final], fmt: str) -> str:
    """Отчёт в выбранном формате."""
    if fmt not in FORMATS:
        raise ValueError(f"неизвестный формат {fmt!r}")
    return FORMATS[fmt](rows)


def render_stats(stats: Sequence[GroupStats]) -> str:
    """Сводка по группам."""
    return "\n".join(
        f"{s.group}: студентов {s.students}, средний итог {s.mean_total}, "
        f"сдали {s.passed}, оценки {s.letters}" for s in stats) + "\n"
