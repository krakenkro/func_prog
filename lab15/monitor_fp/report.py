"""Чистые функции итоговой статистики и форматирования вывода."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import groupby
from operator import attrgetter
from typing import NamedTuple

from monitor_fp.model import Alert, Metric


class ServerStats(NamedTuple):
    """Итоги по серверу."""

    server: str
    samples: int
    cpu_max: float
    latency_avg: float
    alerts: int


def summarize(metrics: Sequence[Metric],
              alerts: Sequence[Alert]) -> tuple[ServerStats, ...]:
    """Статистика по серверам в алфавитном порядке."""
    per_alert = Counter(a.server for a in alerts)
    by_server = groupby(sorted(metrics, key=attrgetter("server")),
                        key=attrgetter("server"))
    return tuple(
        ServerStats(s, len(ms), max(m.cpu for m in ms),
                    sum(m.latency for m in ms) / len(ms), per_alert[s])
        for s, ms in ((s, tuple(g)) for s, g in by_server))


def alert_line(a: Alert) -> str:
    """Строка оповещения."""
    return f"[{a.ts:6d}] {a.level:<4} {a.server}: {a.message}"


def stats_line(s: ServerStats) -> str:
    """Строка итогов сервера."""
    return (f"{s.server}: замеров {s.samples}, CPU max {s.cpu_max:.1f}%, "
            f"задержка ср. {s.latency_avg:.1f} мс, оповещений {s.alerts}")


def render(errors: Sequence[str], alerts: Sequence[Alert],
           stats: Sequence[ServerStats]) -> tuple[str, ...]:
    """Все строки вывода программы."""
    return (*(f"ПРЕДУПРЕЖДЕНИЕ: {e}" for e in errors),
            *map(alert_line, alerts),
            "=== Итоги ===",
            *map(stats_line, stats),
            f"Всего оповещений: {len(alerts)}, ошибок разбора: "
            f"{len(errors)}")


def counts_csv(alerts: Sequence[Alert]) -> str:
    """Отчёт: число оповещений по кодам."""
    counts = sorted(Counter(a.code for a in alerts).items())
    return "code,count\n" + "".join(f"{c},{n}\n" for c, n in counts)
