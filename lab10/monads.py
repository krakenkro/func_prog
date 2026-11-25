"""Задание 5. Монадические контейнеры Maybe, ListM, Writer и их законы.

Монада: ``unit`` (поместить значение в контейнер) и ``bind`` (применить
функцию ``a -> M b`` и «сплющить» результат). Законы:

* левая единица:   ``unit(a).bind(f) == f(a)``;
* правая единица:  ``m.bind(unit) == m``;
* ассоциативность: ``m.bind(f).bind(g) == m.bind(lambda x: f(x).bind(g))``.

Законы функтора: ``m.map(id) == m`` и ``m.map(g∘f) == m.map(f).map(g)``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


# --- Maybe: вычисление, которое может не дать результата -------------------
@dataclass(frozen=True)
class Maybe:
    """Just(value) или Nothing — значения может не быть, без проверок None."""

    value: Any = None
    is_just: bool = False

    @staticmethod
    def unit(x: Any) -> Maybe:
        """Just(x)."""
        return Maybe(x, True)

    def map(self, f: Callable[[Any], Any]) -> Maybe:
        """Применить f к значению внутри Just; Nothing остаётся Nothing."""
        return Maybe(f(self.value), True) if self.is_just else NOTHING

    def bind(self, f: Callable[[Any], Maybe]) -> Maybe:
        """Цепочка вычислений, прерывающаяся на первом Nothing."""
        return f(self.value) if self.is_just else NOTHING

    def __repr__(self) -> str:
        """Just(x) / Nothing."""
        return f"Just({self.value!r})" if self.is_just else "Nothing"


NOTHING = Maybe()


# --- ListM: недетерминированные вычисления ---------------------------------
@dataclass(frozen=True)
class ListM:
    """Набор всех возможных результатов вычисления."""

    values: tuple[Any, ...] = ()

    @staticmethod
    def unit(x: Any) -> ListM:
        """Ровно один вариант."""
        return ListM((x,))

    def map(self, f: Callable[[Any], Any]) -> ListM:
        """Применить f к каждому варианту."""
        return ListM(tuple(f(x) for x in self.values))

    def bind(self, f: Callable[[Any], ListM]) -> ListM:
        """Для каждого варианта получить варианты f и объединить (flat_map)."""
        return ListM(tuple(y for x in self.values for y in f(x).values))


def choose(items: Iterable[Any]) -> ListM:
    """Недетерминированный выбор одного из элементов."""
    return ListM(tuple(items))


def guard(cond: bool) -> ListM:
    """Продолжить ветвь вычисления только если ``cond`` истинно."""
    return ListM((None,)) if cond else ListM()


# --- Writer: значение + журнал --------------------------------------------
@dataclass(frozen=True)
class Writer:
    """Значение вместе с журналом сообщений (журнал — неизменяемый кортеж)."""

    value: Any
    log: tuple[str, ...] = ()

    @staticmethod
    def unit(x: Any) -> Writer:
        """Значение с пустым журналом."""
        return Writer(x, ())

    def map(self, f: Callable[[Any], Any]) -> Writer:
        """Преобразовать значение, журнал не трогать."""
        return Writer(f(self.value), self.log)

    def bind(self, f: Callable[[Any], Writer]) -> Writer:
        """Применить f и дописать её журнал к текущему."""
        w = f(self.value)
        return Writer(w.value, self.log + w.log)


def tell(message: str) -> Writer:
    """Writer, который только пишет сообщение в журнал."""
    return Writer(None, (message,))


# --- проверка законов -------------------------------------------------------
def _compose(
    f: Callable[[Any], Any], g: Callable[[Any], Any]
) -> Callable[[Any], Any]:
    """G ∘ f."""
    return lambda x: g(f(x))


def check_laws(
    unit: Callable[[Any], Any],
    values: Iterable[Any],
    funcs: Iterable[Callable[[Any], Any]],
    plain_funcs: tuple[Callable[[Any], Any], ...] = (
        lambda x: x + 1,
        lambda x: x * 2,
    ),
) -> dict[str, bool]:
    """Проверить 3 закона монады и 2 закона функтора.

    ``unit`` — конструктор контейнера, ``values`` — проверяемые значения,
    ``funcs`` — монадические функции ``a -> M b``, ``plain_funcs`` —
    обычные функции для законов функтора.
    """
    vals, fs = tuple(values), tuple(funcs)
    ms = tuple(unit(a) for a in vals) + tuple(f(a) for a in vals for f in fs)

    def identity(x: Any) -> Any:
        return x

    return {
        "левая единица": all(
            unit(a).bind(f) == f(a) for a in vals for f in fs
        ),
        "правая единица": all(m.bind(unit) == m for m in ms),
        "ассоциативность": all(
            m.bind(f).bind(g) == m.bind(lambda x, f=f, g=g: f(x).bind(g))
            for m in ms
            for f in fs
            for g in fs
        ),
        "функтор: тождество": all(m.map(identity) == m for m in ms),
        "функтор: композиция": all(
            m.map(_compose(f, g)) == m.map(f).map(g)
            for m in ms
            for f in plain_funcs
            for g in plain_funcs
        ),
    }


# --- прикладные задачи -----------------------------------------------------
def pythagorean_triples(n: int) -> tuple[tuple[int, int, int], ...]:
    """Все тройки a ≤ b ≤ c ≤ n с a² + b² = c² — только через bind."""
    return (
        choose(range(1, n + 1))
        .bind(
            lambda a: choose(range(a, n + 1)).bind(
                lambda b: choose(range(b, n + 1)).bind(
                    lambda c: guard(a * a + b * b == c * c).bind(
                        lambda _: ListM.unit((a, b, c))
                    )
                )
            )
        )
        .values
    )


def factorial_w(n: int) -> Writer:
    """Факториал, журналирующий каждый шаг (без побочных эффектов)."""
    if n <= 1:
        return tell(f"{n}! = 1 (базовый случай)").bind(
            lambda _: Writer.unit(1)
        )
    return factorial_w(n - 1).bind(
        lambda r: tell(f"{n}! = {n} × {r} = {n * r}").bind(
            lambda _: Writer.unit(n * r)
        )
    )


def safe_div(a: float, b: float) -> Maybe:
    """Деление, возвращающее Nothing при делении на ноль."""
    return NOTHING if b == 0 else Maybe.unit(a / b)


if __name__ == "__main__":
    maybe_funcs = (
        lambda x: safe_div(100, x),
        lambda x: Maybe.unit(x - 1) if x > 0 else NOTHING,
    )
    list_funcs = (lambda x: ListM((x, -x)), lambda x: ListM((x,) * (x % 3)))
    writer_funcs = (
        lambda x: Writer(x + 1, (f"+1 к {x}",)),
        lambda x: Writer(x * 3, (f"×3 к {x}",)),
    )
    for name, unit, fs in (
        ("Maybe", Maybe.unit, maybe_funcs),
        ("ListM", ListM.unit, list_funcs),
        ("Writer", Writer.unit, writer_funcs),
    ):
        print(f"{name:7}", check_laws(unit, (0, 1, 2, 5, 10), fs))

    print(
        "\nMaybe-цепочка:",
        Maybe.unit(10)
        .bind(lambda x: safe_div(x, 2))
        .bind(lambda x: safe_div(x, 0))
        .map(lambda x: x + 1),
        "| без нуля:",
        Maybe.unit(10).bind(lambda x: safe_div(x, 2)).map(lambda x: x + 1),
    )

    print("\nПифагоровы тройки до 20:", pythagorean_triples(20))

    w = factorial_w(6)
    print("\nWriter: 6! =", w.value)
    print("\n".join("  " + line for line in w.log))
