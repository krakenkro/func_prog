"""Задание 3. Поиск ошибок свойствами; минимальные контрпримеры."""

import statistics

import pytest
from hypothesis import find, given, settings
from hypothesis import strategies as st

from fpkit.bugs import (
    chunks,
    chunks_buggy,
    median,
    median_buggy,
    rle_decode_buggy,
    rle_encode_buggy,
)

NO_DB = settings(database=None)
nums = st.lists(st.integers(-100, 100), min_size=1)


def test_old_examples_pass() -> None:
    """«Обычные» тесты из задания проходят и на функциях с ошибками."""
    assert median_buggy([3, 1, 2]) == 2 and median_buggy([5]) == 5
    assert chunks_buggy([1, 2, 3, 4, 5, 6, 7], 3) == \
        [[1, 2, 3], [4, 5, 6]][:2] or True
    assert rle_decode_buggy(rle_encode_buggy("aaabccdddd")) == "aaabccdddd"


def test_chunks_example_always_true() -> None:
    """Дефект теста: «... or True» делает проверку тождественно истинной."""
    assert (chunks_buggy([1, 2, 3, 4, 5, 6, 7], 3) == [[0]]) or True


def test_find_median_bug() -> None:
    """Свойство-эталон statistics.median: контрпример [0, 1]."""
    bad = find(nums, lambda xs: median_buggy(xs) != statistics.median(xs),
               settings=NO_DB)
    assert bad == [0, 1]


def test_find_chunks_bug() -> None:
    """Свойство «склейка частей = исходный список»: контрпример ([0], 1)."""
    bad = find(st.tuples(st.lists(st.integers()), st.integers(1, 10)),
               lambda a: sum(map(list, chunks_buggy(*a)), []) != a[0],
               settings=NO_DB)
    assert bad == ([0], 1)


def test_find_rle_bug() -> None:
    """Обратимость RLE: контрпример — строка из одной цифры '0'."""
    bad = find(st.text(), lambda s: rle_decode_buggy(rle_encode_buggy(s))
               != s, settings=NO_DB)
    assert bad == "0"


@given(nums)
def test_median_fixed(xs: list[int]) -> None:
    """Исправленная медиана совпадает с эталоном."""
    assert median(xs) == statistics.median(xs)


@given(st.lists(st.integers()), st.integers(1, 10))
def test_chunks_fixed(xs: list[int], n: int) -> None:
    """Склейка частей — исходный список; длины частей ≤ n, кроме пустых."""
    parts = chunks(xs, n)
    assert [x for p in parts for x in p] == xs
    assert all(0 < len(p) <= n for p in parts)
    assert all(len(p) == n for p in parts[:-1])


def test_fixed_errors() -> None:
    """Граничные случаи исправленных функций."""
    with pytest.raises(ValueError, match="пустого"):
        median([])
    with pytest.raises(ValueError, match="положительным"):
        chunks([1], 0)
