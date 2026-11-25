"""Задание 4в. Разбор строки журнала ЛР 13: свой Result против returns.

Исходный ``rating.parsing.parse_line`` (ЛР 13) сообщал об ошибке
исключением. Здесь та же проверка выражена двумя способами:
собственным Result (ЛР 8) и библиотекой returns (Result, @safe, flow, bind).
"""

from __future__ import annotations

from typing import NamedTuple

from returns.pipeline import flow
from returns.pointfree import bind
from returns.result import Failure, Success
from returns.result import Result as RResult
from returns.result import safe as rsafe

from fpkit.result import Err, Ok, Result


class Row(NamedTuple):
    """Разобранная строка журнала."""

    student: str
    task: str
    score: float
    max_score: float


Fields = tuple[str, str, str, str]
Numbers = tuple[str, str, float, float]


# ------------------------------------------------ собственный Result
def split_own(line: str) -> Result[Fields, str]:
    """Ровно 4 непустых поля."""
    parts = tuple(p.strip() for p in line.split(";"))
    if len(parts) != 4 or not all(parts):
        return Err(f"ожидалось 4 поля: {line!r}")
    return Ok((parts[0], parts[1], parts[2], parts[3]))


def numbers_own(f: Fields) -> Result[Numbers, str]:
    """Числовые поля."""
    try:
        return Ok((f[0], f[1], float(f[2]), float(f[3])))
    except ValueError:
        return Err(f"не число: {f[2]!r} или {f[3]!r}")


def range_own(n: Numbers) -> Result[Row, str]:
    """Балл в диапазоне 0..максимум."""
    if n[3] <= 0 or not 0 <= n[2] <= n[3]:
        return Err(f"балл вне диапазона: {n[2]:g}/{n[3]:g}")
    return Ok(Row(*n))


def parse_own(line: str) -> Result[Row, str]:
    """Цепочка bind на собственном Result."""
    return split_own(line).bind(numbers_own).bind(range_own)


# ------------------------------------------------ библиотека returns
def split_r(line: str) -> RResult[Fields, str]:
    """Ровно 4 непустых поля."""
    parts = tuple(p.strip() for p in line.split(";"))
    if len(parts) != 4 or not all(parts):
        return Failure(f"ожидалось 4 поля: {line!r}")
    return Success((parts[0], parts[1], parts[2], parts[3]))


@rsafe
def _to_numbers(f: Fields) -> Numbers:
    return (f[0], f[1], float(f[2]), float(f[3]))


def numbers_r(f: Fields) -> RResult[Numbers, str]:
    """@safe превращает исключение в Failure; сообщение уточняем."""
    return _to_numbers(f).alt(lambda _: f"не число: {f[2]!r} или {f[3]!r}")


def range_r(n: Numbers) -> RResult[Row, str]:
    """Балл в диапазоне 0..максимум."""
    if n[3] <= 0 or not 0 <= n[2] <= n[3]:
        return Failure(f"балл вне диапазона: {n[2]:g}/{n[3]:g}")
    return Success(Row(*n))


def parse_returns(line: str) -> RResult[Row, str]:
    """Конвейер flow + bind из returns."""
    return flow(line, split_r, bind(numbers_r), bind(range_r))


def as_pair(r: Result[Row, str] | RResult[Row, str]) -> tuple[bool, object]:
    """Привести оба вида Result к паре (успех?, значение/ошибка)."""
    if isinstance(r, Ok):
        return True, r.value
    if isinstance(r, Err):
        return False, r.error
    if isinstance(r, Success):
        return True, r.unwrap()
    return False, r.failure()
