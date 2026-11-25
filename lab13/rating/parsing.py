"""Чистые функции разбора журнала группы.

Формат строки: ``студент;работа;балл;максимум`` (``#`` — комментарий).
"""

from __future__ import annotations

from rating.model import Entry


def parse_line(group: str, line: str) -> Entry:
    """Строка журнала → Entry; ValueError с пояснением при ошибке."""
    parts = [p.strip() for p in line.split(";")]
    if len(parts) != 4 or not all(parts):
        raise ValueError(f"ожидалось 4 поля: {line!r}")
    student, task, score_s, max_s = parts
    score, max_score = float(score_s), float(max_s)
    if max_score <= 0 or not 0 <= score <= max_score:
        raise ValueError(f"балл вне диапазона 0..{max_score:g}: {line!r}")
    return Entry(student, group, task, score, max_score)


def parse_journal(group: str, text: str) -> tuple[tuple[Entry, ...],
                                                  tuple[str, ...]]:
    """Разобрать журнал: (записи, сообщения об ошибочных строках)."""
    entries: list[Entry] = []
    errors: list[str] = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            entries.append(parse_line(group, line))
        except ValueError as exc:
            errors.append(f"{group}:{no}: {exc}")
    return tuple(entries), tuple(errors)
