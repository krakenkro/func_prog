"""Конвейер: журналы групп → общий рейтинг. Без ввода-вывода."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from functools import partial
from itertools import chain

from rating.core import rank, score_group, summarize_group
from rating.model import DEFAULT_WEIGHTS, GroupResult, RatingReport, Weights
from rating.parsing import parse_journal

Mapper = Callable[..., Iterable[GroupResult]]


def analyze_group(item: tuple[str, str],
                  weights: Weights = DEFAULT_WEIGHTS) -> GroupResult:
    """(группа, текст журнала) → GroupResult. Единица параллельной работы."""
    group, text = item
    entries, errors = parse_journal(group, text)
    return GroupResult(group, score_group(entries, weights), errors)


def build_report(journals: Sequence[tuple[str, str]],
                 weights: Weights = DEFAULT_WEIGHTS,
                 mapper: Mapper = map,
                 failed: Sequence[str] = ()) -> RatingReport:
    """Собрать отчёт; ``mapper`` — map или pool.map (внедрение)."""
    results = tuple(mapper(partial(analyze_group, weights=weights),
                           journals))
    return RatingReport(
        rank(chain.from_iterable(r.scores for r in results)),
        tuple(summarize_group(r.group, r.scores) for r in results),
        (*failed, *chain.from_iterable(r.errors for r in results)),
    )
