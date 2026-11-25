"""Сборка конвейера из функций ядра (по-прежнему без ввода-вывода)."""

from __future__ import annotations

from datetime import date

from gradesapp.core import THRESHOLD, group_stats
from gradesapp.formatters import FORMATTERS
from gradesapp.model import GroupStat, Result
from gradesapp.parsing import parse_csv


def console_lines(
    stats: tuple[GroupStat, ...], today: date
) -> tuple[str, ...]:
    """Строки для экрана в формате исходной программы."""
    return tuple(
        f"{today} {s.group}: средний {s.average:.1f} [{s.status}]"
        for s in stats
    )


def make_report(
    csv_text: str, today: date, fmt: str = "txt",
    threshold: float = THRESHOLD,
) -> Result:
    """Текст CSV → строки для экрана и отчёт в выбранном формате."""
    if fmt not in FORMATTERS:
        raise ValueError(f"неизвестный формат {fmt!r}: {sorted(FORMATTERS)}")
    stats = group_stats(parse_csv(csv_text), threshold)
    return Result(console_lines(stats, today), FORMATTERS[fmt](stats, today))
