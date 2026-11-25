"""Неизменяемая модель данных."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

from pyrsistent import PMap, pmap

ITEM_RE = re.compile(r"lab(0[1-9]|1[0-5])|rk[12]|exam")


@dataclass(frozen=True)
class Mark:
    """Событие журнала: оценка за элемент курса.

    ``value`` — для лабораторной доля качества 0..1 ((А + Т + З) × О),
    для рубежного контроля (rk1, rk2) и экзамена — процент 0..100.
    """

    student: str
    group: str
    item: str
    value: float
    late: bool = False

    @property
    def is_lab(self) -> bool:
        """Лабораторная ли работа."""
        return self.item.startswith("lab")


@dataclass(frozen=True)
class Record:
    """Оценки студента: последняя оценка по каждому элементу."""

    group: str
    marks: PMap[str, Mark] = pmap()


class Final(NamedTuple):
    """Итог студента по дисциплине."""

    student: str
    group: str
    labs: float
    rk: float
    admission: float
    admitted: bool
    exam: float | None
    total: float
    letter: str
    gpa: float
    word: str
    status: str
