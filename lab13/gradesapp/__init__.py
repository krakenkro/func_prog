"""Задания 1–2. Отчёт по группам: модель — разбор — ядро — конвейер — оболочка.

Зависимости модулей (стрелка — «импортирует»)::

    shell → pipeline → core → model
                     → parsing → model
                     → formatters → model

Ядро (model, parsing, core, formatters, pipeline) не импортирует shell и
не обращается к файлам, текущей дате и глобальному изменяемому состоянию.
"""

from gradesapp.core import group_stats, status_of
from gradesapp.formatters import FORMATTERS, formatter
from gradesapp.model import Grade, GroupStat, Result
from gradesapp.parsing import parse_csv
from gradesapp.pipeline import console_lines, make_report

__all__ = [
    "FORMATTERS",
    "Grade",
    "GroupStat",
    "Result",
    "console_lines",
    "formatter",
    "group_stats",
    "make_report",
    "parse_csv",
    "status_of",
]
