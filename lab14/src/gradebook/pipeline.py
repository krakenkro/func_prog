"""Конвейер: текст журнала → итоги (без ввода-вывода)."""

from __future__ import annotations

from typing import NamedTuple

from gradebook.core import finals, replay
from gradebook.model import Final
from gradebook.parsing import parse_journal
from gradebook.scale import Scale


class Outcome(NamedTuple):
    """Итоги и ошибки разбора."""

    finals: tuple[Final, ...]
    errors: tuple[str, ...]


def process(text: str, scale: Scale, group: str | None = None) -> Outcome:
    """Разобрать журнал, свернуть события, рассчитать итоги."""
    marks, errors = parse_journal(text)
    return Outcome(finals(replay(marks), scale, group), errors)
