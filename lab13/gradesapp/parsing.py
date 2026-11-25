"""Чистые функции разбора: текст CSV → кортеж Grade."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping

from gradesapp.model import Grade


def parse_row(row: Mapping[str, str]) -> Grade:
    """Строка CSV (словарь) → Grade; ValueError при нечисловом балле."""
    return Grade(row["student"], row["group"], int(row["score"]))


def parse_csv(text: str) -> tuple[Grade, ...]:
    """Разобрать текст CSV с заголовком student,group,score."""
    return tuple(map(parse_row, csv.DictReader(io.StringIO(text))))
