"""Задание 4а: объём кода и время конвейера ЛР 13 и его версии на toolz."""

import sys
import timeit
from functools import partial
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "src"), str(HERE.parent / "lab13")]

from radon.raw import analyze  # noqa: E402
from rating import build_report  # noqa: E402
from rating.source import journal_text  # noqa: E402

from fpkit import toolz_rating as tr  # noqa: E402


def sloc(*paths: Path) -> int:
    """Логические строки кода без комментариев и docstring (radon raw)."""
    return sum(analyze(p.read_text(encoding="utf-8")).sloc for p in paths)


if __name__ == "__main__":
    lab13 = HERE.parent / "lab13" / "rating"
    print("SLOC: ЛР 13 (parsing + core + pipeline):",
          sloc(lab13 / "parsing.py", lab13 / "core.py",
               lab13 / "pipeline.py"),
          "| toolz_rating.py:", sloc(HERE / "src/fpkit/toolz_rating.py"))
    for students in (100, 1000, 4000):
        journals = tuple((g, journal_text(g, students))
                         for g in ("A", "B", "C", "D"))
        same = tr.ranking(journals) == [
            (r.rank, r.student, r.group, r.percent)
            for r in build_report(journals).ranking]
        t1 = min(timeit.repeat(partial(build_report, journals), number=1,
                               repeat=3))
        t2 = min(timeit.repeat(partial(tr.ranking, journals), number=1,
                               repeat=3))
        print(f"{students * 4:>6} студентов: ЛР 13 {t1:.3f} с, toolz "
              f"{t2:.3f} с ({t2 / t1:.2f}x), результаты совпадают: {same}")
