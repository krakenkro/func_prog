"""Оболочка: аргументы, файлы, печать (зависимости внедряются)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from monitor_fp.model import DEFAULT, Config, Metric
from monitor_fp.parsing import parse_log
from monitor_fp.report import counts_csv, render, summarize
from monitor_fp.rules import Alerts
from monitor_fp.streams import detect_reactive

USAGE = "использование: monitor_legacy.py metrics.csv [report.csv]"
Out = Callable[[str], object]
Detector = Callable[[Sequence[Metric], Config], Alerts]


def main(argv: Sequence[str], read_lines: Callable[[str], Iterable[str]],
         write: Callable[[str, str], object], out: Out = print,
         cfg: Config = DEFAULT, detector: Detector = detect_reactive) -> int:
    """Разобрать журнал, вывести оповещения и итоги, записать отчёт.

    ``detector`` — реактивный компонент (по умолчанию) или пакетный
    ``core.detect``: оба построены на одном редьюсере ``core.step``.
    """
    if not argv:
        out(USAGE)
        return 1
    metrics, errors = parse_log(read_lines(argv[0]))
    alerts = detector(metrics, cfg)
    for line in render(errors, alerts, summarize(metrics, alerts)):
        out(line)
    if len(argv) > 1:
        write(argv[1], counts_csv(alerts))
        out(f"отчёт: {argv[1]}")
    return 0


def read_lines(path: str) -> list[str]:
    """Прочитать строки файла."""
    return Path(path).read_text(encoding="utf-8").splitlines(keepends=True)


def write_text(path: str, text: str) -> None:
    """Записать файл."""
    Path(path).write_text(text, encoding="utf-8")


def run_cli() -> int:
    """«Боевая» конфигурация: sys.argv, файловая система, print."""
    return main(sys.argv[1:], read_lines, write_text, print)
