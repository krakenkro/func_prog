"""Оболочка: интерфейс командной строки (argparse), файлы, печать."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from gradebook.config import load_config
from gradebook.pipeline import process
from gradebook.report import FORMATS, group_stats, render, render_stats
from gradebook.scale import scale_from_config


def build_parser() -> argparse.ArgumentParser:
    """Описание команд."""
    parser = argparse.ArgumentParser(
        prog="gradebook", description="Учёт успеваемости по шкале силлабуса")
    parser.add_argument("--config", type=Path, help="файл TOML")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="итоговая ведомость")
    rep.add_argument("journal", type=Path)
    rep.add_argument("--format", choices=sorted(FORMATS))
    rep.add_argument("--group")
    rep.add_argument("--out", type=Path, help="файл для отчёта")
    st = sub.add_parser("student", help="итог одного студента")
    st.add_argument("journal", type=Path)
    st.add_argument("name")
    stats = sub.add_parser("stats", help="сводка по группам")
    stats.add_argument("journal", type=Path)
    return parser


def main(argv: Sequence[str], env: Mapping[str, str],
         out: Callable[[str], object] = print) -> int:
    """Выполнить команду; вернуть код завершения."""
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config.read_text(encoding="utf-8")
                      if args.config else None, env)
    outcome = process(args.journal.read_text(encoding="utf-8"),
                      scale_from_config(cfg), getattr(args, "group", None))
    for error in outcome.errors:
        out(f"предупреждение: {error}")
    if args.command == "report":
        text = render(outcome.finals, args.format or cfg["report"]["format"])
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            out(f"отчёт записан: {args.out}")
        else:
            out(text.rstrip("\n"))
    elif args.command == "student":
        found = [f for f in outcome.finals if f.student == args.name]
        if not found:
            out(f"студент {args.name!r} не найден")
            return 1
        out(render(found, "txt").rstrip("\n"))
    else:
        out(render_stats(group_stats(outcome.finals)).rstrip("\n"))
    return 0
