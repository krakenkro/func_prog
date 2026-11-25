"""Разбор журнала CSV с обработкой ошибок на returns (Result, flow, bind).

Формат: ``student,group,item,value,late`` (late: 1/0/пусто).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping

from returns.pipeline import flow
from returns.pointfree import bind
from returns.result import Failure, Result, Success, safe

from gradebook.model import ITEM_RE, Mark

HEADER = ("student", "group", "item", "value", "late")
Row = Mapping[str, str | None]
Fields = tuple[str, str, str, str, str]


def fields(row: Row) -> Result[Fields, str]:
    """Обязательные поля присутствуют и не пусты."""
    values = tuple((row.get(k) or "").strip() for k in HEADER)
    missing = [k for k, v in zip(HEADER[:4], values, strict=False) if not v]
    if missing:
        return Failure(f"нет полей {', '.join(missing)}")
    return Success((values[0], values[1], values[2], values[3], values[4]))


def check_item(f: Fields) -> Result[Fields, str]:
    """Элемент курса: lab01..lab15, rk1, rk2, exam."""
    if ITEM_RE.fullmatch(f[2]):
        return Success(f)
    return Failure(f"неизвестный элемент {f[2]!r}")


@safe
def _number(text: str) -> float:
    return float(text)


def to_mark(f: Fields) -> Result[Mark, str]:
    """Число в допустимом диапазоне и флаг опоздания."""
    if f[4] not in ("", "0", "1"):
        return Failure(f"late должно быть 0 или 1, а не {f[4]!r}")
    limit = 1.0 if f[2].startswith("lab") else 100.0
    return (_number(f[3])
            .alt(lambda _: f"не число: {f[3]!r}")
            .bind(lambda v: Success(Mark(f[0], f[1], f[2], v, f[4] == "1"))
                  if 0 <= v <= limit
                  else Failure(f"{f[2]}: значение {v:g} вне 0..{limit:g}")))


def parse_row(row: Row) -> Result[Mark, str]:
    """Строка CSV → Success(Mark) | Failure(сообщение)."""
    return flow(row, fields, bind(check_item), bind(to_mark))


def parse_journal(text: str) -> tuple[tuple[Mark, ...], tuple[str, ...]]:
    """Текст журнала → (оценки, ошибки с номерами строк)."""
    marks: list[Mark] = []
    errors: list[str] = []
    for no, row in enumerate(csv.DictReader(io.StringIO(text)), 2):
        match parse_row(row):
            case Success(mark):
                marks.append(mark)
            case Failure(message):
                errors.append(f"строка {no}: {message}")
    return tuple(marks), tuple(errors)


def to_csv(marks: Iterable[Mark]) -> str:
    """Обратная операция: оценки → текст CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows((m.student, m.group, m.item, repr(m.value),
                      "1" if m.late else "0") for m in marks)
    return buf.getvalue()
