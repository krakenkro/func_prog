"""Императивная оболочка: все зависимости внедряются параметрами."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from functools import partial
from pathlib import Path

from gradesapp.pipeline import make_report


def run(load: Callable[[], str], today: Callable[[], date],
        write: Callable[[str], object], show: Callable[[str], object],
        fmt: str = "txt") -> None:
    """Загрузить данные, вывести строки на экран и записать отчёт."""
    result = make_report(load(), today(), fmt)
    for line in result.lines:
        show(line)
    write(result.report)


def read_text(path: Path) -> str:
    """Прочитать файл UTF-8."""
    return path.read_text(encoding="utf-8")


def production(src: Path, dst: Path, fmt: str = "txt") -> Callable[[], None]:
    """«Боевая» конфигурация: файлы, системная дата и print."""
    return partial(run, partial(read_text, src), date.today,
                   partial(Path.write_text, dst, encoding="utf-8"),
                   print, fmt)
