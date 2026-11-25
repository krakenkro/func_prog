"""Задание 1. Персистентный (неизменяемый) односвязный список ``PList``.

Каждая операция возвращает *новый* список, старые версии не меняются.
Новые версии переиспользуют хвосты старых — это структурное разделение:
``cons`` за O(1) создаёт один узел и ссылается на весь старый список.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import reduce
from itertools import islice
from typing import Any


@dataclass(frozen=True, eq=False, repr=False)
class PList:
    """Узел неизменяемого списка с полями ``head`` и ``tail``.

    Пустой список — единственный узел ``NIL`` (у него ``tail is None``);
    у непустого узла ``tail`` — всегда ``PList``.
    """

    head: Any = None
    tail: PList | None = None

    def __iter__(self) -> Iterator[Any]:
        """Обходит элементы от головы к концу (обход не меняет список)."""
        node = self
        while node.tail is not None:
            yield node.head
            node = node.tail

    def __len__(self) -> int:
        """Длина за O(n) — в узлах хранятся только head и tail."""
        return length(self)

    def __bool__(self) -> bool:
        """Непустой ли список (O(1), без подсчёта длины)."""
        return not is_empty(self)

    def __eq__(self, other: object) -> bool:
        """Поэлементное сравнение; общий хвост сравнивается мгновенно (is)."""
        if not isinstance(other, PList):
            return NotImplemented
        a, b = self, other
        while a is not b:
            if a.tail is None or b.tail is None:
                return a.tail is None and b.tail is None
            if a.head != b.head:
                return False
            a, b = a.tail, b.tail
        return True

    def __hash__(self) -> int:
        """Хеш по содержимому (нужен, т. к. переопределён ``__eq__``).

        Без него экземпляр считался бы изменяемым, и ``NIL`` нельзя было бы
        использовать как значение по умолчанию поля dataclass.
        """
        return hash(tuple(self))

    def __repr__(self) -> str:
        """Читаемое представление ``PList([1, 2, 3])``."""
        return f"PList({list(self)!r})"


NIL: PList = PList()
"""Единственный пустой список (разделяется всеми списками как «дно»)."""


# --- конструирование и преобразование в Python-коллекции ------------------
def cons(x: Any, lst: PList) -> PList:
    """Добавить ``x`` в начало ``lst`` за O(1); ``lst`` разделяется целиком."""
    return PList(x, lst)


def from_iterable(items: Iterable[Any]) -> PList:
    """Построить ``PList`` из итерируемого объекта (порядок сохраняется)."""
    return reduce(lambda acc, x: cons(x, acc), reversed(tuple(items)), NIL)


def to_list(lst: PList) -> list[Any]:
    """Преобразовать в обычный изменяемый ``list`` (копия)."""
    return list(lst)


def is_empty(lst: PList) -> bool:
    """Пуст ли список (O(1))."""
    return lst.tail is None


def length(lst: PList) -> int:
    """Количество элементов (свёртка, O(n))."""
    return fold_left(lambda n, _: n + 1, 0, lst)


# --- доступ ---------------------------------------------------------------
def head(lst: PList) -> Any:
    """Первый элемент; ``IndexError`` для пустого списка."""
    if is_empty(lst):
        raise IndexError("head от пустого списка")
    return lst.head


def tail(lst: PList) -> PList:
    """Список без первого элемента (сам хвост, без копирования)."""
    if is_empty(lst):
        raise IndexError("tail от пустого списка")
    return lst.tail  # type: ignore[return-value]


def drop(lst: PList, n: int) -> PList:
    """Отбросить ``n`` первых элементов. Результат — общий суффикс (O(n))."""
    return reduce(
        lambda node, _: node if is_empty(node) else node.tail,
        range(max(n, 0)),
        lst,
    )


def take(lst: PList, n: int) -> PList:
    """Первые ``n`` элементов (новые узлы — префикс нельзя разделить)."""
    return from_iterable(islice(lst, max(n, 0)))


def nth(lst: PList, n: int) -> Any:
    """Элемент с индексом ``n`` (с нуля); ``IndexError`` вне диапазона."""
    rest = drop(lst, n)
    if n < 0 or is_empty(rest):
        raise IndexError(f"индекс {n} вне диапазона")
    return head(rest)


# --- свёртки и функции высшего порядка ------------------------------------
def fold_left(f: Callable[[Any, Any], Any], acc: Any, lst: PList) -> Any:
    """Левая свёртка: f(...f(f(acc, x0), x1)..., xn)."""
    return reduce(f, lst, acc)


def reverse(lst: PList) -> PList:
    """Обращение за O(n) одной левой свёрткой с ``cons``."""
    return fold_left(lambda acc, x: cons(x, acc), NIL, lst)


def fold_right(f: Callable[[Any, Any], Any], acc: Any, lst: PList) -> Any:
    """Правая свёртка: f(x0, f(x1, ... f(xn, acc))).

    Реализована через левую свёртку обращённого списка — без глубокой
    рекурсии, поэтому работает и для списков длиннее лимита стека.
    """
    return fold_left(lambda a, x: f(x, a), acc, reverse(lst))


def map_(f: Callable[[Any], Any], lst: PList) -> PList:
    """Отображение: новый список ``[f(x) for x in lst]``."""
    return fold_right(lambda x, acc: cons(f(x), acc), NIL, lst)


def filter_(pred: Callable[[Any], bool], lst: PList) -> PList:
    """Фильтрация с сохранением порядка."""
    return fold_right(
        lambda x, acc: cons(x, acc) if pred(x) else acc, NIL, lst
    )


def append(a: PList, b: PList) -> PList:
    """Конкатенация ``a ++ b``.

    Список ``b`` разделяется целиком, а все узлы ``a`` копируются: последний
    узел ``a`` ссылается на ``NIL``, и чтобы он ссылался на ``b``, его нужно
    создать заново — а значит, заново и всех его предшественников.
    """
    return fold_right(cons, b, a)


if __name__ == "__main__":
    base = from_iterable([3, 4, 5])
    xs = cons(2, base)
    ys = cons(20, base)
    print("base =", base, "| xs =", xs, "| ys =", ys)
    print("xs и ys разделяют хвост base:", tail(xs) is tail(ys) is base)

    nums = from_iterable(range(1, 11))
    print("map x²:", map_(lambda x: x * x, nums))
    print("filter чётные:", filter_(lambda x: x % 2 == 0, nums))
    print("fold_left (+):", fold_left(lambda a, x: a + x, 0, nums))
    print(
        "fold_right (строка):",
        fold_right(lambda x, a: f"({x} {a})", "nil", take(nums, 3)),
    )
    print("reverse:", reverse(nums))
    print("take 3 / drop 7:", take(nums, 3), drop(nums, 7))
    print("nth 4:", nth(nums, 4), "| length:", length(nums))
    joined = append(take(nums, 2), base)
    print("append:", joined, "| хвост b разделён:", drop(joined, 2) is base)
    print("исходный nums не изменился:", to_list(nums))
