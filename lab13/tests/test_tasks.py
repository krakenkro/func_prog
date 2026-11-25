"""Задания 3–5 и дополнительное задание."""

import asyncio
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import async_fetch as af
import cpu_parallel as cp
import pandas as pd
import pandas_fp as pf
import parallel_pipeline as pp
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ------------------------------ Задание 3 ---------------------------------
@pytest.mark.parametrize(("n", "prime"), [(0, False), (1, False), (2, True),
                                          (3, True), (4, False), (25, False),
                                          (97, True), (7919, True)])
def test_is_prime(n: int, prime: bool) -> None:
    """Простота на граничных значениях."""
    assert cp.is_prime(n) is prime


def test_parallel_count_matches_sequential() -> None:
    """Потоки и процессы дают тот же результат, partial вместо lambda."""
    nums = range(1, 5000)
    expected = cp.count_primes(nums)
    assert expected == 669
    m = cp.measure_pool("process", ProcessPoolExecutor, nums, 2, 500)
    assert m.primes == expected
    with ProcessPoolExecutor(2) as pool:
        assert sum(pool.map(partial(cp.is_prime_shifted, 1), nums)) == \
            cp.count_primes(range(2, 5001))


def test_lambda_cannot_be_pickled() -> None:
    """Лямбда в пуле процессов → ошибка сериализации."""
    error, fixed = cp.lambda_demo(range(10))
    assert "pickle" in error
    assert fixed == 4                      # 2, 3, 5, 7 среди 1..10


def test_amdahl_roundtrip() -> None:
    """estimate_p обратна amdahl."""
    for n in (2, 4, 8):
        assert cp.estimate_p(cp.amdahl(0.9, n), n) == pytest.approx(0.9)
    assert cp.amdahl(1.0, 8) == pytest.approx(8)


# ------------------------------ Задание 4 ---------------------------------
def test_async_fetch_semaphore_timeout_errors() -> None:
    """gather(return_exceptions) + Semaphore + wait_for, ядро aggregate."""
    sources = af.plan_sources(20, scale=0.05)
    active, peak = [0], [0]

    async def spy(source: af.Source) -> int:
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        try:
            return await af.fetch(source)
        finally:
            active[0] -= 1

    res = asyncio.run(af.fetch_all(sources, 5, 0.025, spy))
    assert peak[0] == 5
    summary = af.aggregate(sources, res)
    assert summary.ok + sum(summary.errors.values()) == 20
    assert set(summary.errors) == {"ConnectionError", "TimeoutError"}
    seq = asyncio.run(af.fetch_sequential(sources, 0.025))
    assert af.aggregate(sources, seq) == summary


def test_aggregate_empty() -> None:
    """Все источники с ошибками."""
    s = af.aggregate([af.Source("a", 0, True, 1)], [ValueError("x")])
    assert s == af.Summary(0, {"ValueError": 1}, 0, "-")


# ------------------------------ Задание 5 ---------------------------------
@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    """Сгенерированный набор 10 000 строк."""
    return pf.generate(10_000)


def test_steps_do_not_mutate(raw: pd.DataFrame) -> None:
    """Ни один шаг не изменяет входную таблицу."""
    assert all(pf.check_steps(raw).values())


def test_pipeline_results(raw: pd.DataFrame) -> None:
    """После подготовки нет пропусков и выбросов, группы нормализованы."""
    ready = pf.prepare(raw)
    assert ready["score"].between(0, 100).all()
    assert (ready["hours"] >= 0).all()
    assert set(ready["group"]) == set(pf.GROUPS)
    agg = pf.analyze(raw)
    assert agg["n"].sum() == len(ready)
    assert len(agg) == len(pf.GROUPS) * len(pf.SUBJECTS)


def test_parallel_aggregation_equal(raw: pd.DataFrame) -> None:
    """Concat частей + повторная агрегация = агрегирование целиком."""
    parts = [pf.partial_aggregate(p) for p in pf.split(raw, 3)]
    pd.testing.assert_frame_equal(pf.combine_partials(parts),
                                  pf.analyze(raw), check_dtype=False)
    pd.testing.assert_frame_equal(pf.parallel_analyze(raw, 2),
                                  pf.analyze(raw), check_dtype=False)


# -------------------------- Дополнительное задание ------------------------
@pytest.fixture(scope="module")
def pool() -> ProcessPoolExecutor:
    """Общий пул процессов для тестов на основе свойств."""
    with ProcessPoolExecutor(2) as executor:
        yield executor


LINES = st.integers(-1000, 1000).map(str) | st.sampled_from(["x", ""])


@settings(max_examples=40, deadline=None)
@given(st.lists(LINES),
       st.lists(st.integers(0, 60)))
def test_pipeline_any_partition_sum(pool: ProcessPoolExecutor,
                                    data: list[str], cuts: list[int]) -> None:
    """Сумма квадратов чётных: любое разбиение = последовательно."""
    assert pp.parallel_pipeline(pp.SUM_OF_EVEN_SQUARES, data, pp.add, 0,
                                cuts=cuts, pool=pool) == \
        pp.sequential(pp.SUM_OF_EVEN_SQUARES, data, pp.add, 0)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.text(alphabet="аб В", max_size=8)),
       st.lists(st.integers(0, 30)))
def test_pipeline_any_partition_wordcount(pool: ProcessPoolExecutor,
                                          data: list[str],
                                          cuts: list[int]) -> None:
    """Частоты слов: любое разбиение = последовательно."""
    assert pp.parallel_pipeline(pp.WORD_COUNT, data, pp.merge_counts,
                                Counter(), cuts=cuts, pool=pool) == \
        pp.sequential(pp.WORD_COUNT, data, pp.merge_counts, Counter())


@given(st.lists(st.integers()), st.lists(st.integers(-5, 50)))
def test_split_at_preserves_data(data: list[int], cuts: list[int]) -> None:
    """Разбиение не теряет и не переставляет элементы."""
    assert [x for part in pp.split_at(data, cuts) for x in part] == data


def test_parallel_pipeline_own_pool() -> None:
    """Без внешнего пула создаётся собственный."""
    assert pp.parallel_pipeline(pp.SUM_OF_EVEN_SQUARES, ["2", "3", "4"],
                                pp.add, 0, workers=2) == 20
