"""Функции из прежних лабораторных работ (ЛР 2, 4, 6, 8) для тестирования.

Чистые функции и две функции оболочки (запись файла, печать таблицы).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from functools import reduce
from pathlib import Path
from typing import TypeVar

from fpkit.result import Err, Ok, Result

T = TypeVar("T")
Tx = tuple[str, int]


# ------------------------------------------------------------ ЛР 2
def clamp(x: float, lo: float, hi: float) -> float:
    """Ограничить x отрезком [lo, hi]."""
    if lo > hi:
        raise ValueError(f"пустой отрезок [{lo}, {hi}]")
    return max(lo, min(x, hi))


def mean(xs: Sequence[float]) -> float:
    """Среднее арифметическое непустой последовательности."""
    if not xs:
        raise ValueError("среднее пустой последовательности")
    return sum(xs) / len(xs)


def normalize(s: str) -> str:
    """Убрать лишние пробелы и привести к нижнему регистру."""
    return " ".join(s.split()).lower()


def word_freq(text: str) -> dict[str, int]:
    """Частоты слов (без учёта регистра и знаков препинания)."""
    return dict(Counter(re.findall(r"\w+", text.lower())))


# ------------------------------------------------------------ ЛР 4
def rle_encode(s: str) -> str:
    """'aaab' → 'a3;b1;' — символ, число повторов, разделитель ';'.

    Первый символ группы всегда литерал, поэтому цифры и ';' в исходной
    строке не нарушают обратимость (исправление ошибки из задания 3).
    """
    groups: list[list[object]] = []
    for ch in s:
        if groups and groups[-1][0] == ch:
            groups[-1][1] = int(str(groups[-1][1])) + 1
        else:
            groups.append([ch, 1])
    return "".join(f"{ch}{n};" for ch, n in groups)


def rle_decode(code: str) -> str:
    """Обратная к rle_encode функция; ValueError для неверного кода."""
    out, i = [], 0
    while i < len(code):
        end = code.find(";", i + 1)
        count = code[i + 1:end]
        if end < 0 or not count.isdigit():
            raise ValueError(f"неверный RLE-код в позиции {i}")
        out.append(code[i] * int(count))
        i = end + 1
    return "".join(out)


def apply_tx(balance: int, tx: Tx) -> int:
    """Применить операцию ('deposit' | 'withdraw', сумма) к балансу."""
    kind, amount = tx
    if amount <= 0:
        raise ValueError("сумма операции должна быть положительной")
    if kind == "deposit":
        return balance + amount
    if kind == "withdraw":
        if amount > balance:
            raise ValueError("недостаточно средств")
        return balance - amount
    raise ValueError(f"неизвестная операция {kind!r}")


def fold_balance(journal: Iterable[Tx], start: int = 0) -> int:
    """Свёртка журнала операций в итоговый баланс."""
    return reduce(apply_tx, journal, start)


# ------------------------------------------------------------ ЛР 6
def merge(a: Sequence[T], b: Sequence[T]) -> list[T]:
    """Слить два отсортированных списка (устойчиво)."""
    out: list[T] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if b[j] < a[i]:  # type: ignore[operator]
            out.append(b[j])
            j += 1
        else:
            out.append(a[i])
            i += 1
    return [*out, *a[i:], *b[j:]]


def merge_sort(xs: Sequence[T]) -> list[T]:
    """Сортировка слиянием (новый список, вход не изменяется)."""
    if len(xs) <= 1:
        return list(xs)
    mid = len(xs) // 2
    return merge(merge_sort(xs[:mid]), merge_sort(xs[mid:]))


# ------------------------------------------------------------ ЛР 8
def parse_int(s: str) -> Result[int, str]:
    """Строка → Ok(int) | Err(сообщение)."""
    s = s.strip()
    if re.fullmatch(r"[+-]?\d+", s):
        return Ok(int(s))
    return Err(f"не целое число: {s!r}")


def safe_div(a: float, b: float) -> Result[float, str]:
    """Деление без исключения."""
    return Err("деление на ноль") if b == 0 else Ok(a / b)


# ------------------------------------------------------ оболочка
def write_report(path: Path, rows: Iterable[tuple[str, float]]) -> int:
    """Записать отчёт «имя: значение» в файл; вернуть число строк."""
    lines = [f"{name}: {value:.2f}" for name, value in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def print_table(rows: Iterable[tuple[str, float]]) -> None:
    """Напечатать таблицу с выравниванием."""
    for name, value in rows:
        print(f"{name:<12}{value:>8.2f}")
