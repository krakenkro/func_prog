"""Собственный тип Result (ЛР 8): Ok | Err с map, bind, unwrap_or."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Успешный результат."""

    value: T

    def map(self, f: Callable[[T], U]) -> Ok[U]:
        """Применить f к значению."""
        return Ok(f(self.value))

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Цепочка вычислений, каждое из которых может завершиться ошибкой."""
        return f(self.value)

    def unwrap_or(self, default: T) -> T:
        """Значение (default не нужен)."""
        return self.value


@dataclass(frozen=True)
class Err(Generic[E]):
    """Ошибка: дальнейшие шаги пропускаются."""

    error: E

    def map(self, f: Callable[[Any], Any]) -> Err[E]:
        """Ошибка не изменяется."""
        return self

    def bind(self, f: Callable[[Any], Any]) -> Err[E]:
        """Ошибка не изменяется."""
        return self

    def unwrap_or(self, default: T) -> T:
        """Значение по умолчанию."""
        return default


Result = Ok[T] | Err[E]
