"""Задание 6 (вариант 4). Рейтинг студентов по журналам нескольких групп.

Журналы групп «загружаются» асинхронно (loader), разбираются и
оцениваются чистым ядром (parsing, core) — последовательно или в пуле
процессов (parallel), конвейер собирает итоговый рейтинг (pipeline),
оболочка (shell) выполняет ввод-вывод и замеры.

Зависимости: shell → loader, parallel, pipeline, source;
parallel → pipeline; pipeline → core, parsing; core, parsing → model.
"""

from rating.core import letter, rank, score_group, summarize_group
from rating.model import (
    DEFAULT_WEIGHTS,
    Entry,
    GroupResult,
    GroupSummary,
    Ranked,
    RatingReport,
    StudentScore,
    Weights,
)
from rating.parsing import parse_journal, parse_line
from rating.pipeline import analyze_group, build_report

__all__ = [
    "DEFAULT_WEIGHTS",
    "Entry",
    "GroupResult",
    "GroupSummary",
    "Ranked",
    "RatingReport",
    "StudentScore",
    "Weights",
    "analyze_group",
    "build_report",
    "letter",
    "parse_journal",
    "parse_line",
    "rank",
    "score_group",
    "summarize_group",
]
