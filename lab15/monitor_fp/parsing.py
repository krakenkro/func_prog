"""Чистый разбор журнала метрик."""

from __future__ import annotations

from collections.abc import Iterable

from monitor_fp.model import Metric


def parse_line(line: str, lineno: int) -> Metric | str:
    """Строка журнала → Metric или текст ошибки."""
    parts = line.strip().split(",")
    if len(parts) != 5:
        return f"строка {lineno}: неверное число полей"
    try:
        metric = Metric(int(parts[0]), parts[1].strip(), float(parts[2]),
                        float(parts[3]), float(parts[4]))
    except ValueError:
        return f"строка {lineno}: не число"
    if not metric.server:
        return f"строка {lineno}: пустое имя сервера"
    if not (0 <= metric.cpu <= 100 and 0 <= metric.mem <= 100
            and metric.latency >= 0):
        return f"строка {lineno}: значение вне диапазона"
    return metric


def parse_log(lines: Iterable[str]) -> tuple[tuple[Metric, ...],
                                             tuple[str, ...]]:
    """Все строки → (замеры по возрастанию времени, ошибки)."""
    metrics: list[Metric] = []
    errors: list[str] = []
    for lineno, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        item = parse_line(line, lineno)
        if isinstance(item, str):
            errors.append(item)
        elif metrics and item.ts < metrics[-1].ts:
            errors.append(f"строка {lineno}: нарушен порядок времени")
        else:
            metrics.append(item)
    return tuple(metrics), tuple(errors)
