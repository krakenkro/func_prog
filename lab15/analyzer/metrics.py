"""Метрики качества кода: radon (SLOC, сложность, MI) + анализатор ast."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

from analyzer.purity import impurity_findings, purity_summary


class Metrics(NamedTuple):
    """Метрики набора файлов."""

    files: int
    sloc: int
    functions: int
    avg_cc: float
    max_cc: int
    worst: str
    mi: float
    pure: int
    state_changes: int
    io_sites: int
    mutable_globals: int


def measure(sources: dict[str, str]) -> Metrics:
    """Чистая функция: метрики по текстам модулей {имя: исходный код}."""
    blocks = [b for src in sources.values() for b in cc_visit(src)]
    sums = [purity_summary(src) for src in sources.values()]
    worst = max(blocks, key=lambda b: b.complexity, default=None)
    sloc = {n: analyze(s).sloc for n, s in sources.items()}
    total = sum(sloc.values()) or 1
    return Metrics(
        files=len(sources),
        sloc=sum(sloc.values()),
        functions=sum(s.functions for s in sums),
        avg_cc=round(sum(b.complexity for b in blocks) / max(len(blocks), 1),
                     2),
        max_cc=worst.complexity if worst else 0,
        worst=worst.name if worst else "-",
        mi=round(sum(mi_visit(s, multi=True) * sloc[n]
                     for n, s in sources.items()) / total, 1),
        pure=sum(s.pure for s in sums),
        state_changes=sum(s.state_changes for s in sums),
        io_sites=sum(s.io_sites for s in sums),
        mutable_globals=sum(s.mutable_globals for s in sums),
    )


def read_sources(paths: Iterable[Path]) -> dict[str, str]:
    """Оболочка: прочитать файлы."""
    return {p.name: p.read_text(encoding="utf-8") for p in paths}


def complexity_table(source: str) -> tuple[tuple[str, int, int], ...]:
    """(функция, строка, цикломатическая сложность) по убыванию сложности."""
    return tuple(sorted(((b.name, b.lineno, b.complexity)
                         for b in cc_visit(source)),
                        key=lambda t: (-t[2], t[1])))


def main(paths: list[Path]) -> None:
    """Печать метрик и находок анализатора для указанных файлов."""
    sources = read_sources(paths)
    print(measure(sources))
    for name, src in sources.items():
        print(f"\n{name}: сложность функций (radon cc)")
        for fn, line, cc in complexity_table(src):
            print(f"  {fn:<24} строка {line:>4}  CC = {cc}")
        print(f"{name}: признаки нечистоты (ast)")
        for f in impurity_findings(src):
            print(f"  {f.function:<16}{f.line:>5}  {f.kind}: {f.detail}")


if __name__ == "__main__":
    main([Path(p) for p in sys.argv[1:]])
