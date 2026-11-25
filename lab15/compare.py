"""Задание 4. Сравнение исходной и функциональной версий.

Метрики кода (radon + анализатор ast), время и пиковая память
(timeit-подобный замер perf_counter, tracemalloc) на трёх размерах журнала.
"""

from __future__ import annotations

import contextlib
import io
import runpy
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "data"))

from analyzer.metrics import measure, read_sources  # noqa: E402
from make_metrics import generate  # noqa: E402
from monitor_fp.core import detect  # noqa: E402
from monitor_fp.shell import main, read_lines  # noqa: E402
from monitor_fp.streams import detect_reactive  # noqa: E402

SIZES = (("малый", 400), ("средний", 4_000), ("большой", 40_000))


def run_legacy(path: str) -> None:
    """Исходная программа (вывод отбрасывается)."""
    argv = sys.argv
    sys.argv = ["legacy", path]
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.suppress(SystemExit):
            runpy.run_path(str(HERE / "legacy" / "monitor_legacy.py"),
                           run_name="__main__")
    finally:
        sys.argv = argv


def run_fp(path: str, detector: Callable[..., object]) -> None:
    """Функциональная версия (вывод отбрасывается)."""
    main([path], read_lines, lambda *_: None, lambda _: None,
         detector=detector)  # type: ignore[arg-type]


def timed(fn: Callable[[], None], repeat: int = 3) -> float:
    """Лучшее время из repeat запусков."""
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def peak_mb(fn: Callable[[], None]) -> float:
    """Пиковая память по tracemalloc, МБ."""
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 2**20


def code_metrics() -> None:
    """Таблица метрик кода."""
    legacy = measure(read_sources([HERE / "legacy" / "monitor_legacy.py"]))
    fp = measure(read_sources(sorted((HERE / "monitor_fp").glob("*.py"))))
    print(f"{'Метрика':<34}{'исходная':>10}{'функц.':>10}")
    for title, a, b in (
            ("файлов", legacy.files, fp.files),
            ("строк кода (radon sloc)", legacy.sloc, fp.sloc),
            ("функций", legacy.functions, fp.functions),
            ("чистых функций (ast)", legacy.pure, fp.pure),
            ("доля чистых, %", round(100 * legacy.pure / legacy.functions),
             round(100 * fp.pure / fp.functions)),
            ("средняя сложность CC", legacy.avg_cc, fp.avg_cc),
            ("максимальная сложность CC", legacy.max_cc, fp.max_cc),
            ("индекс сопровождаемости MI", legacy.mi, fp.mi),
            ("мест изменения состояния", legacy.state_changes,
             fp.state_changes),
            ("мест ввода-вывода", legacy.io_sites, fp.io_sites),
            ("изменяемых глобальных", legacy.mutable_globals,
             fp.mutable_globals)):
        print(f"{title:<34}{a:>10}{b:>10}")
    print(f"самая сложная функция: исходная — {legacy.worst}, "
          f"функциональная — {fp.worst}")


def performance() -> None:
    """Время и пиковая память на трёх размерах журнала."""
    print(f"\n{'Размер':<9}{'строк':>8} | {'время, с':^26} | "
          f"{'пик памяти, МБ':^26}")
    print(f"{'':<17} | {'legacy':>8}{'batch':>9}{'rx':>9} | "
          f"{'legacy':>8}{'batch':>9}{'rx':>9}")
    with tempfile.TemporaryDirectory() as tmp:
        for title, steps in SIZES:
            path = Path(tmp) / f"{steps}.csv"
            path.write_text(generate(steps), encoding="utf-8")
            lines = sum(1 for _ in path.open(encoding="utf-8"))
            jobs = (lambda: run_legacy(str(path)),
                    lambda: run_fp(str(path), detect),
                    lambda: run_fp(str(path), detect_reactive))
            times = [timed(j, 3 if steps < 40_000 else 1) for j in jobs]
            peaks = [peak_mb(j) for j in jobs]
            print(f"{title:<9}{lines:>8} | "
                  + "".join(f"{t:>9.3f}" for t in times).lstrip()
                  .rjust(26) + " | "
                  + "".join(f"{p:>9.2f}" for p in peaks).lstrip()
                  .rjust(26))


if __name__ == "__main__":
    code_metrics()
    performance()
