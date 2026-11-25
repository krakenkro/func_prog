"""Задание 2. Персистентная очередь на двух персистентных стеках.

Очередь хранит «переднюю» часть ``front`` (голова — первый в очереди) и
«заднюю» ``back`` в обратном порядке (голова — последний добавленный).
``enqueue`` кладёт элемент на ``back`` за O(1); ``dequeue`` снимает с
``front``, а когда ``front`` опустел — переворачивает ``back`` за O(n).
Каждый элемент переворачивается не более одного раза, поэтому при
однопоточном (эфемерном) использовании амортизированная сложность — O(1).
"""

from __future__ import annotations

import random
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from plist import NIL, PList, cons, is_empty, reverse


@dataclass(frozen=True)
class PQueue:
    """Неизменяемая очередь (FIFO). Инвариант: front пуст ⇒ очередь пуста.

    ``length`` хранится в самой очереди, чтобы ``len`` работал за O(1)
    (в узлах PList длины нет).
    """

    front: PList = NIL
    back: PList = NIL
    length: int = 0

    def enqueue(self, x: Any) -> PQueue:
        """Новая очередь с ``x`` в конце."""
        return _make(self.front, cons(x, self.back), self.length + 1)

    def dequeue(self) -> tuple[Any, PQueue]:
        """Пара (первый элемент, остаток очереди); IndexError, если пусто."""
        if self.is_empty():
            raise IndexError("dequeue из пустой очереди")
        return self.front.head, _make(
            self.front.tail, self.back, self.length - 1
        )

    def peek(self) -> Any:
        """Первый элемент без удаления."""
        if self.is_empty():
            raise IndexError("peek пустой очереди")
        return self.front.head

    def is_empty(self) -> bool:
        """Пуста ли очередь (O(1) благодаря инварианту)."""
        return is_empty(self.front)

    def __len__(self) -> int:
        """Количество элементов за O(1)."""
        return self.length

    def __iter__(self) -> Iterator[Any]:
        """Элементы в порядке извлечения."""
        yield from self.front
        yield from reverse(self.back)


def _make(front: PList, back: PList, length: int) -> PQueue:
    """«Умный конструктор»: восстанавливает инвариант, переворачивая back."""
    if is_empty(front):
        return PQueue(reverse(back), NIL, length)
    return PQueue(front, back, length)


EMPTY_QUEUE = PQueue()


def from_iterable(items: Any) -> PQueue:
    """Очередь из элементов итерируемого объекта."""
    q = EMPTY_QUEUE
    for x in items:
        q = q.enqueue(x)
    return q


def random_ops(n: int, seed: int) -> tuple[tuple[str, int], ...]:
    """Детерминированная последовательность операций enqueue/dequeue."""
    rng = random.Random(seed)
    return tuple(
        ("enq", rng.randint(0, 999)) if rng.random() < 0.6 else ("deq", 0)
        for _ in range(n)
    )


def run_ops(ops: tuple[tuple[str, int], ...]) -> tuple[list[Any], PQueue]:
    """Выполнить операции на PQueue; вернуть извлечённые значения и очередь."""
    q, out = EMPTY_QUEUE, []
    for op, v in ops:
        if op == "enq":
            q = q.enqueue(v)
        elif not q.is_empty():
            x, q = q.dequeue()
            out.append(x)
    return out, q


def run_ops_deque(ops: tuple[tuple[str, int], ...]) -> list[Any]:
    """Эталон: те же операции на collections.deque."""
    d: deque[Any] = deque()
    out = []
    for op, v in ops:
        if op == "enq":
            d.append(v)
        elif d:
            out.append(d.popleft())
    return out


def time_ops(n: int) -> float:
    """Время (с) выполнения n случайных операций над PQueue."""
    ops = random_ops(n, seed=1)
    start = time.perf_counter()
    run_ops(ops)
    return time.perf_counter() - start


if __name__ == "__main__":
    q1 = from_iterable([1, 2, 3])
    q2 = q1.enqueue(4)
    x, q3 = q2.dequeue()
    print(
        "q1 =",
        list(q1),
        "| q2 =",
        list(q2),
        "| dequeue ->",
        x,
        "| q3 =",
        list(q3),
    )
    print("старые версии сохранены:", list(q1) == [1, 2, 3])

    ops = random_ops(10_000, seed=42)
    print(
        "FIFO совпадает с deque на 10 000 операций:",
        run_ops(ops)[0] == run_ops_deque(ops),
    )

    print("\nАмортизированная сложность (время должно расти линейно):")
    for n in (10_000, 20_000, 50_000, 100_000):
        t = time_ops(n)
        print(
            f"  n = {n:>7}: {t * 1000:7.1f} мс, "
            f"на операцию {t / n * 1e6:5.2f} мкс"
        )
