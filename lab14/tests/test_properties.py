"""Задание 2. Свойства функций (hypothesis)."""

from collections import deque

from hypothesis import given
from hypothesis import strategies as st
from pqueue import PQueue

from fpkit.classics import (
    fold_balance,
    merge,
    merge_sort,
    normalize,
    rle_decode,
    rle_encode,
)

ints = st.lists(st.integers())


@given(ints)
def test_sort_oracle(xs: list[int]) -> None:
    """Эталон: совпадает со встроенной sorted."""
    assert merge_sort(xs) == sorted(xs)


@given(ints)
def test_sort_invariant(xs: list[int]) -> None:
    """Инвариант: упорядоченность, та же длина и тот же мультимножество."""
    ys = merge_sort(xs)
    assert all(a <= b for a, b in zip(ys, ys[1:], strict=False))
    assert sorted(map(repr, ys)) == sorted(map(repr, xs))


@given(st.text())
def test_rle_roundtrip(s: str) -> None:
    """Обратимость: decode(encode(s)) == s для любой строки."""
    assert rle_decode(rle_encode(s)) == s


@given(st.text())
def test_normalize_idempotent(s: str) -> None:
    """Идемпотентность: normalize(normalize(s)) == normalize(s)."""
    assert normalize(normalize(s)) == normalize(s)


@given(ints, ints)
def test_merge_invariant_and_oracle(a: list[int], b: list[int]) -> None:
    """Слияние отсортированных: эталон sorted(a + b), длина сохраняется."""
    a, b = sorted(a), sorted(b)
    merged = merge(a, b)
    assert len(merged) == len(a) + len(b)
    assert merged == sorted(a + b)


ops = st.lists(st.one_of(st.tuples(st.just("enq"), st.integers()),
                         st.just(("deq", 0)), st.just(("peek", 0))))


@given(ops)
def test_pqueue_model(commands: list[tuple[str, int]]) -> None:
    """Модельное тестирование: PQueue (ЛР 10) против collections.deque."""
    q, model = PQueue(), deque[int]()
    history: list[tuple[PQueue, list[int]]] = []
    for op, x in commands:
        if op == "enq":
            q = q.enqueue(x)
            model.append(x)
        elif model:
            if op == "deq":
                got, q = q.dequeue()
                assert got == model.popleft()
            else:
                assert q.peek() == model[0]
        else:
            assert q.is_empty()
        assert len(q) == len(model)
        history.append((q, list(model)))
    # персистентность: все прежние версии очереди не изменились
    assert all(list(v) == expected for v, expected in history)


txs = st.lists(st.tuples(st.just("deposit"), st.integers(1, 1000)))


@given(txs, txs, st.integers(0, 10**6))
def test_balance_metamorphic(j1: list[tuple[str, int]],
                             j2: list[tuple[str, int]], start: int) -> None:
    """Объединение журналов: fold(j1 + j2) == fold(j2, fold(j1))."""
    assert fold_balance(j1 + j2, start) == \
        fold_balance(j2, fold_balance(j1, start))


@given(st.lists(st.tuples(st.sampled_from(["deposit", "withdraw"]),
                          st.integers(1, 100))))
def test_balance_never_negative(journal: list[tuple[str, int]]) -> None:
    """Инвариант: если свёртка удалась, баланс неотрицателен."""
    try:
        assert fold_balance(journal) >= 0
    except ValueError as exc:
        assert "недостаточно" in str(exc)
