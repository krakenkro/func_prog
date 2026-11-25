"""Оболочка: загрузка, печать рейтинга, замеры производительности."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence

from rating.loader import Fetch, load_groups, load_sequential
from rating.model import RatingReport
from rating.parallel import build_report_parallel
from rating.pipeline import build_report
from rating.source import journal_text, make_fetch

GROUPS = ("ПИ-21", "ПИ-22", "ИС-21", "ИС-22", "ВТ-23", "ВТ-24", "СИБ-23",
          "МТ-22")
DELAYS = {g: 0.15 + 0.1 * (i % 4) for i, g in enumerate(GROUPS)}
DELAYS["МТ-22"] = 2.0                       # слишком медленный сервер
BROKEN = frozenset({"СИБ-23"})              # недоступный сервер


def render(report: RatingReport, top: int = 10) -> tuple[str, ...]:
    """Чистая функция: отчёт → строки для печати."""
    head = ("Место  Студент                Группа    %      Оценка",)
    rows = tuple(f"{r.rank:>5}  {r.student:<22} {r.group:<8} "
                 f"{r.percent:>6.2f}  {r.letter}"
                 for r in report.ranking[:top])
    groups = tuple(f"  {g.group:<7} студентов {g.students:>3}, средний "
                   f"{g.mean:6.2f}, медиана {g.median:6.2f}, лучший "
                   f"{g.best}" for g in report.groups)
    return (*head, *rows, "Сводка по группам:", *groups,
            "Проблемы:", *(f"  {e}" for e in report.errors))


def timed(fn: Callable[[], object]) -> float:
    """Время выполнения fn в секундах."""
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


async def main(fetch: Fetch, groups: Sequence[str] = GROUPS,
               show: Callable[[str], object] = print) -> RatingReport:
    """Загрузить группы, построить и вывести рейтинг, замерить загрузку."""
    t0 = time.perf_counter()
    loaded = await load_groups(groups, fetch, limit=3)
    t_async = time.perf_counter() - t0
    report = build_report(loaded.journals, failed=loaded.failed)
    for line in render(report):
        show(line)
    t0 = time.perf_counter()
    await load_sequential(groups, fetch)
    show(f"\nЗагрузка {len(groups)} групп: асинхронно (limit=3) "
         f"{t_async:.2f} с, последовательно {time.perf_counter() - t0:.2f} с")
    return report


def benchmark(students: int = 4000, show: Callable[[str], object] = print,
              ) -> None:
    """Последовательный и параллельный расчёт на больших журналах."""
    journals = tuple((g, journal_text(g, students)) for g in GROUPS)
    show(f"Расчёт: {len(GROUPS)} групп × {students} студентов "
         f"({sum(t.count(chr(10)) for _, t in journals)} строк)")
    seq = timed(lambda: build_report(journals))
    show(f"  последовательно      {seq:6.2f} с")
    for w in (2, 4, 8):
        t = timed(lambda: build_report_parallel(journals, workers=w))
        show(f"  процессов {w}          {t:6.2f} с  ускорение {seq / t:.2f}x")
    same = build_report(journals) == build_report_parallel(journals)
    show(f"  результаты совпадают: {same}")


def run() -> None:
    """Точка входа «боевой» конфигурации."""
    asyncio.run(main(make_fetch(DELAYS, BROKEN)))
    benchmark()
