"""Параллельный расчёт: каждая группа — в своём процессе."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor

from rating.model import DEFAULT_WEIGHTS, RatingReport, Weights
from rating.pipeline import build_report


def build_report_parallel(journals: Sequence[tuple[str, str]],
                          weights: Weights = DEFAULT_WEIGHTS,
                          workers: int = 4,
                          failed: Sequence[str] = ()) -> RatingReport:
    """Тот же конвейер, что build_report, но mapper — pool.map."""
    with ProcessPoolExecutor(workers) as pool:
        return build_report(journals, weights, pool.map, failed)
