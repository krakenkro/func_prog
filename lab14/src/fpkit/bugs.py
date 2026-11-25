"""Задание 3. Функции с ошибками (как в задании) и исправленные версии."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


# ---------------------------------------------- исходные (с ошибками)
def median_buggy(xs: Sequence[float]) -> float:
    """Медиана непустого списка чисел."""
    return sorted(xs)[len(xs) // 2]


def chunks_buggy(xs: Sequence[T], n: int) -> list[Sequence[T]]:
    """Разбить список на части длины n (последняя может быть короче)."""
    return [xs[i:i + n] for i in range(0, len(xs) - n, n)]


def rle_encode_buggy(s: str) -> str:
    """'aaab' -> 'a3b1'."""
    if not s:
        return ""
    out, prev, count = [], s[0], 1
    for ch in s[1:]:
        if ch == prev:
            count += 1
        else:
            out.append(f"{prev}{count}")
            prev, count = ch, 1
    out.append(f"{prev}{count}")
    return "".join(out)


def rle_decode_buggy(code: str) -> str:
    """Обратная функция к rle_encode_buggy."""
    return "".join(ch * int(num)
                   for ch, num in re.findall(r"(\D)(\d+)", code))


# ---------------------------------------------- исправленные
def median(xs: Sequence[float]) -> float:
    """Медиана: для чётной длины — среднее двух центральных."""
    if not xs:
        raise ValueError("медиана пустого списка")
    s, mid = sorted(xs), len(xs) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def chunks(xs: Sequence[T], n: int) -> list[Sequence[T]]:
    """Части длины n; последняя может быть короче; ничего не теряется."""
    if n <= 0:
        raise ValueError("размер части должен быть положительным")
    return [xs[i:i + n] for i in range(0, len(xs), n)]
