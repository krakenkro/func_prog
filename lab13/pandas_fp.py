"""Задание 5. Анализ успеваемости в Pandas в функциональном стиле.

Шаги ``DataFrame -> DataFrame`` соединяются через ``df.pipe``; ни один шаг
не изменяет входную таблицу (assign/query/loc возвращают новые таблицы).
Соответствие операциям ФП: assign/apply — map, query/loc[mask] — filter,
groupby().agg() — reduce.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

GROUPS = ("ПИ-21", "ПИ-22", "ИС-21", "ИС-22", "ВТ-23", "ВТ-24")
SUBJECTS = ("ФП", "БД", "ОС", "Сети", "Матан")
KEYS = ["group", "subject"]


def generate(n: int, seed: int = 4) -> pd.DataFrame:
    """Синтетический журнал: пропуски, мусор в названиях, выбросы."""
    rng = np.random.default_rng(seed)
    score = rng.normal(68, 15, n).round(1)
    score[rng.random(n) < 0.03] = np.nan            # пропуски
    score[rng.random(n) < 0.01] = 150.0             # выбросы
    group = rng.choice(GROUPS, n)
    noisy = rng.random(n) < 0.1                     # « пи-21 » и т. п.
    group = np.where(noisy, np.char.add(" ", np.char.lower(group)), group)
    return pd.DataFrame({
        "student": rng.integers(1, 600, n),
        "group": group,
        "subject": rng.choice(SUBJECTS, n),
        "score": score,
        "hours": rng.integers(-2, 40, n),
    })


# ---------------------------------------------------- функции-шаги
def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Нормализовать названия групп, убрать пропуски баллов."""
    return (df.assign(group=df["group"].str.strip().str.upper())
              .dropna(subset=["score"]))


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Новые столбцы (map): зачёт и баллы за час подготовки."""
    return df.assign(
        passed=df["score"] >= 50,
        per_hour=lambda d: d["score"] / d["hours"].clip(lower=1),
    )


def filter_valid(df: pd.DataFrame) -> pd.DataFrame:
    """Отбор корректных строк (filter)."""
    return df.query("0 <= score <= 100 and hours >= 0")


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Свёртка по группе и предмету (reduce)."""
    return (df.groupby(KEYS, as_index=False)
              .agg(mean_score=("score", "mean"), n=("score", "size"),
                   pass_rate=("passed", "mean"))
              .round(3))


STEPS: tuple[Callable[[pd.DataFrame], pd.DataFrame], ...] = (
    clean, add_features, filter_valid)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Конвейер подготовки данных через pipe."""
    return df.pipe(clean).pipe(add_features).pipe(filter_valid)


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """Полный конвейер: подготовка и агрегирование."""
    return df.pipe(prepare).pipe(aggregate)


# ---------------------------------- параллельное агрегирование
def partial_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Map-фаза: суммы и количества (ассоциативно объединяемые)."""
    return (df.pipe(prepare)
              .groupby(KEYS, as_index=False)
              .agg(total=("score", "sum"), n=("score", "size"),
                   passed=("passed", "sum")))


def combine_partials(parts: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Reduce-фаза: concat + повторная агрегация + итоговые средние."""
    s = pd.concat(parts).groupby(KEYS, as_index=False).sum()
    return (s.assign(mean_score=s["total"] / s["n"],
                     pass_rate=s["passed"] / s["n"])
             [[*KEYS, "mean_score", "n", "pass_rate"]]
             .round(3))


def split(df: pd.DataFrame, parts: int) -> list[pd.DataFrame]:
    """Разбить таблицу на части по строкам."""
    size = -(-len(df) // parts)
    return [df.iloc[i:i + size] for i in range(0, len(df), size)]


def parallel_analyze(df: pd.DataFrame, workers: int = 4) -> pd.DataFrame:
    """Агрегирование частей таблицы в пуле процессов."""
    with ProcessPoolExecutor(workers) as pool:
        return combine_partials(list(pool.map(partial_aggregate,
                                              split(df, workers))))


def unchanged(step: Callable[[pd.DataFrame], pd.DataFrame],
              df: pd.DataFrame) -> bool:
    """Проверка: шаг не изменил входную таблицу."""
    before = df.copy(deep=True)
    step(df)
    return df.equals(before)


def check_steps(df: pd.DataFrame) -> dict[str, bool]:
    """Каждый шаг конвейера проверяется на своём фактическом входе."""
    result = {}
    for step in (*STEPS, aggregate):
        result[step.__name__] = unchanged(step, df)
        df = step(df)
    return result


def timed(fn: Callable[[], pd.DataFrame]) -> tuple[float, pd.DataFrame]:
    """Время и результат."""
    t0 = time.perf_counter()
    res = fn()
    return time.perf_counter() - t0, res


if __name__ == "__main__":
    pd.set_option("display.width", 100)
    raw = generate(20_000)
    print(f"исходных строк: {len(raw)}, после подготовки: "
          f"{len(prepare(raw))}")
    print("шаги не изменяют вход:", check_steps(raw))
    print(analyze(raw).head(10).to_string(index=False))
    for n in (20_000, 1_000_000, 4_000_000):
        df = generate(n)
        t_seq, a = timed(lambda: analyze(df))
        t_par, b = timed(lambda: parallel_analyze(df))
        pd.testing.assert_frame_equal(a, b, check_dtype=False)
        print(f"n={n:>9}: последовательно {t_seq:.3f} с, "
              f"4 процесса {t_par:.3f} с, результаты совпадают")
