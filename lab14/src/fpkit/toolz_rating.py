"""Задание 4а. Конвейер рейтинга ЛР 13 на toolz (pipe + curried).

Тот же расчёт, что ``rating.pipeline.build_report`` (ЛР 13): разбор
журнала, последняя запись по паре (студент, работа), взвешенный процент,
общий рейтинг. Дополнительно — динамика по лабораторным через
``sliding_window``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from toolz import curried as tc
from toolz import pipe

WEIGHTS = {"lab": 0.3, "rk": 0.3, "exam": 0.4}


def parse(group: str, text: str) -> list[dict[str, Any]]:
    """Текст журнала → записи-словари (ошибочные строки отбрасываются)."""
    def to_row(parts: list[str]) -> dict[str, Any] | None:
        if len(parts) != 4 or not all(parts):
            return None
        try:
            score, mx = float(parts[2]), float(parts[3])
        except ValueError:
            return None
        if mx <= 0 or not 0 <= score <= mx:
            return None
        return {"student": parts[0], "group": group, "task": parts[1],
                "score": score, "max": mx}

    return pipe(text.splitlines(),
                tc.map(lambda s: s.split("#", 1)[0].strip()),
                tc.filter(None),
                tc.map(lambda s: [p.strip() for p in s.split(";")]),
                tc.map(to_row),
                tc.filter(None),
                list)


def kind(task: str) -> str:
    """Вид работы по имени."""
    return task.rstrip("0123456789").lower()


def percent(rows: Sequence[dict[str, Any]],
            maxima: Mapping[str, float]) -> float:
    """Взвешенный процент студента (как в ЛР 13)."""
    got = {r["task"]: r["score"] for r in rows}
    by_kind = pipe(maxima.keys(), tc.filter(lambda t: kind(t) in WEIGHTS),
                   tc.groupby(kind))
    parts = [(WEIGHTS[k], sum(got.get(t, 0.0) for t in ts)
              / sum(maxima[t] for t in ts)) for k, ts in by_kind.items()]
    total_w = sum(w for w, _ in parts)
    if not total_w:
        return 0.0
    return round(100 * sum(w * s for w, s in parts) / total_w, 2)


def score_group(group: str, text: str) -> list[tuple[str, str, float]]:
    """(студент, группа, процент) для одной группы."""
    rows = pipe(parse(group, text),
                tc.reduceby(lambda r: (r["student"], r["task"]),
                            lambda _, r: r, init=None),
                dict.values, list)
    maxima = {r["task"]: r["max"] for r in rows}
    return pipe(rows, tc.groupby("student"),
                tc.valmap(lambda rs: percent(rs, maxima)),
                dict.items, sorted,
                tc.map(lambda kv: (kv[0], group, kv[1])), list)


def ranking(journals: Iterable[tuple[str, str]],
            ) -> list[tuple[int, str, str, float]]:
    """Общий рейтинг: (место, студент, группа, процент)."""
    ordered = pipe(journals, tc.mapcat(lambda gj: score_group(*gj)),
                   lambda xs: sorted(xs, key=lambda s: (-s[2], s[1], s[0])),
                   list)
    places = pipe(enumerate(ordered, 1), tc.groupby(lambda p: p[1][2]),
                  tc.valmap(lambda ps: ps[0][0]))
    return [(places[p], s, g, p) for s, g, p in ordered]


def lab_trend(rows: Sequence[dict[str, Any]]) -> float:
    """Средний прирост доли балла между соседними лабораторными."""
    labs = sorted((int(r["task"][3:]), r["score"] / r["max"])
                  for r in rows if kind(r["task"]) == "lab")
    deltas = pipe(labs, tc.sliding_window(2),
                  tc.map(lambda w: w[1][1] - w[0][1]), list)
    return round(sum(deltas) / len(deltas), 4) if deltas else 0.0
