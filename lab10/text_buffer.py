"""Задание 6 (вариант 4). Текстовый буфер редактора с историей и undo/redo.

Документ — ``pvector`` строк. Все операции редактирования — чистые функции
``PVector -> PVector``: они не меняют исходный документ, а изменение одной
строки копирует лишь путь в дереве pvector (≈ log₃₂ n узлов), разделяя всё
остальное с предыдущей версией.

``Editor`` — неизменяемое состояние редактора:

* ``present`` — текущий документ;
* ``undo`` / ``redo`` — персистентные стеки (``PList``) предыдущих/отменённых
  версий: undo и redo стоят O(1) и не копируют текст;
* ``history`` — полный журнал всех когда-либо созданных версий (включая
  ветки, «потерянные» после undo + новой правки), к любой можно вернуться.
"""

from __future__ import annotations

import random
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field

from plist import NIL, PList, cons, is_empty
from pyrsistent import PVector, pvector

Lines = PVector  # PVector[str]
EditOp = Callable[[Lines], Lines]


# ===================== чистые операции над документом ======================
def from_text(text: str) -> Lines:
    """Документ из строки текста."""
    return pvector(text.split("\n"))


def to_text(lines: Lines) -> str:
    """Текст документа."""
    return "\n".join(lines)


def _check_row(lines: Lines, row: int, allow_end: bool = False) -> None:
    """Проверить номер строки (IndexError при выходе за границы)."""
    hi = len(lines) if allow_end else len(lines) - 1
    if not 0 <= row <= hi:
        raise IndexError(f"строка {row} вне диапазона 0..{hi}")


def _check_col(line: str, col: int) -> None:
    """Проверить позицию в строке."""
    if not 0 <= col <= len(line):
        raise IndexError(f"столбец {col} вне диапазона 0..{len(line)}")


def set_line(row: int, text: str) -> EditOp:
    """Заменить строку ``row`` на ``text``."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row)
        return lines.set(row, text)

    return op


def insert_text(row: int, col: int, text: str) -> EditOp:
    """Вставить ``text`` в позицию (row, col)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row)
        line = lines[row]
        _check_col(line, col)
        return lines.set(row, line[:col] + text + line[col:])

    return op


def delete_text(row: int, col: int, count: int) -> EditOp:
    """Удалить ``count`` символов, начиная с (row, col)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row)
        line = lines[row]
        _check_col(line, col)
        return lines.set(row, line[:col] + line[col + max(count, 0) :])

    return op


def insert_line(row: int, text: str = "") -> EditOp:
    """Вставить новую строку перед строкой ``row`` (row == len — в конец)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row, allow_end=True)
        if row == len(lines):
            return lines.append(text)
        return lines[:row] + pvector([text]) + lines[row:]

    return op


def delete_line(row: int) -> EditOp:
    """Удалить строку ``row`` (в документе всегда остаётся хотя бы одна)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row)
        rest = lines.delete(row)
        return rest if len(rest) else pvector([""])

    return op


def split_line(row: int, col: int) -> EditOp:
    """Разбить строку в позиции col (нажатие Enter)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row)
        line = lines[row]
        _check_col(line, col)
        return insert_line(row + 1, line[col:])(lines.set(row, line[:col]))

    return op


def join_lines(row: int) -> EditOp:
    """Склеить строку ``row`` со следующей (Backspace в начале строки)."""

    def op(lines: Lines) -> Lines:
        _check_row(lines, row + 1)
        merged = lines.set(row, lines[row] + lines[row + 1])
        return merged.delete(row + 1)

    return op


def replace_all(old: str, new: str) -> EditOp:
    """Заменить подстроку во всех строках (неизменённые строки разделяются)."""

    def op(lines: Lines) -> Lines:
        e = lines.evolver()
        for i, line in enumerate(lines):
            if old in line:
                e[i] = line.replace(old, new)
        return e.persistent()

    return op


# ============================== редактор ===================================
@dataclass(frozen=True)
class Version:
    """Запись в полном журнале версий."""

    label: str
    lines: Lines


@dataclass(frozen=True)
class Editor:
    """Неизменяемое состояние редактора с undo/redo и полной историей."""

    present: Lines = field(default_factory=lambda: pvector([""]))
    undo_stack: PList = NIL  # PList[Version] — что можно отменить
    redo_stack: PList = NIL  # PList[Version] — что можно вернуть
    history: PVector = field(
        default_factory=lambda: pvector([Version("создание", pvector([""]))])
    )

    @staticmethod
    def open(text: str) -> Editor:
        """Редактор с начальным текстом."""
        doc = from_text(text)
        return Editor(doc, NIL, NIL, pvector([Version("открытие", doc)]))

    @property
    def text(self) -> str:
        """Текущий текст."""
        return to_text(self.present)

    def apply(self, label: str, op: EditOp) -> Editor:
        """Выполнить правку; стек redo очищается (новая ветка истории)."""
        new = op(self.present)
        return Editor(
            new,
            cons(Version(label, self.present), self.undo_stack),
            NIL,
            self.history.append(Version(label, new)),
        )

    def can_undo(self) -> bool:
        """Есть ли что отменять."""
        return not is_empty(self.undo_stack)

    def can_redo(self) -> bool:
        """Есть ли что возвращать."""
        return not is_empty(self.redo_stack)

    def undo(self) -> Editor:
        """Отменить последнюю правку (если нечего — вернуть себя же)."""
        if not self.can_undo():
            return self
        prev: Version = self.undo_stack.head
        return Editor(
            prev.lines,
            self.undo_stack.tail,
            cons(Version(prev.label, self.present), self.redo_stack),
            self.history.append(Version(f"undo «{prev.label}»", prev.lines)),
        )

    def redo(self) -> Editor:
        """Повторить отменённую правку."""
        if not self.can_redo():
            return self
        nxt: Version = self.redo_stack.head
        return Editor(
            nxt.lines,
            cons(Version(nxt.label, self.present), self.undo_stack),
            self.redo_stack.tail,
            self.history.append(Version(f"redo «{nxt.label}»", nxt.lines)),
        )


# ====================== сравнение с наивным копированием ===================
def naive_edits(
    lines: list[str], edits: tuple[tuple[int, str], ...]
) -> list[list[str]]:
    """Наивная история: копия всего списка строк перед каждой правкой."""
    versions = [lines]
    for row, text in edits:
        new = list(versions[-1])
        new[row] = text
        versions.append(new)
    return versions


def persistent_edits(
    lines: Lines, edits: tuple[tuple[int, str], ...]
) -> Editor:
    """Те же правки через Editor (pvector + персистентные стеки)."""
    ed = Editor(lines, NIL, NIL, pvector([Version("start", lines)]))
    for row, text in edits:
        ed = ed.apply("edit", set_line(row, text))
    return ed


def benchmark(n_lines: int, n_edits: int) -> list[tuple[str, float, float]]:
    """Время (с) и пиковая память (МБ) для двух подходов."""
    rng = random.Random(4)
    base = [f"строка {i}: " + "x" * 40 for i in range(n_lines)]
    edits = tuple(
        (rng.randrange(n_lines), f"правка {i}") for i in range(n_edits)
    )
    cases = (
        ("наивное копирование list", lambda: naive_edits(base, edits)),
        ("pvector + Editor", lambda: persistent_edits(pvector(base), edits)),
    )
    rows = []
    for name, run in cases:
        start = time.perf_counter()
        run()
        elapsed = time.perf_counter() - start
        tracemalloc.start()
        result = run()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        del result
        rows.append((name, elapsed, peak / 2**20))
    return rows


if __name__ == "__main__":
    ed = Editor.open("def hello():\n    print('hi')")
    steps: tuple[tuple[str, EditOp], ...] = (
        ("переименование", insert_text(0, 9, "_world")),
        ("новая строка", insert_line(2, "hello_world()")),
        ("текст print", set_line(1, "    print('Привет, ФП!')")),
        ("Enter", split_line(2, 5)),
    )
    for label, op in steps:
        ed = ed.apply(label, op)
        print(f"--- после «{label}» ---\n{ed.text}")

    ed_undo = ed.undo().undo()
    print("\n--- после двух undo ---\n" + ed_undo.text)
    ed_redo = ed_undo.redo()
    print("--- после redo ---\n" + ed_redo.text)
    ed_branch = ed_undo.apply(
        "ветка: комментарий", insert_line(0, "# новая ветка")
    )
    print(
        "--- новая правка после undo (redo очищен:",
        not ed_branch.can_redo(),
        ") ---\n" + ed_branch.text,
    )

    print("\nПолная история версий:")
    for i, v in enumerate(ed_branch.history):
        print(f"  v{i:<2} {v.label:<30} {len(v.lines)} стр.")
    print(
        "исходная версия v0 не изменилась:",
        to_text(ed_branch.history[0].lines),
    )
    print("версия v4 доступна и после undo и новой ветки:")
    print(to_text(ed_branch.history[4].lines))

    n_lines = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    n_edits = int(sys.argv[2]) if len(sys.argv) > 2 else 2_000
    print(
        f"\nПроизводительность: {n_lines} строк, {n_edits} правок, "
        "все версии сохраняются"
    )
    print(f"{'Подход':<28}{'Время, с':>10}{'Память, МБ':>13}")
    for name, t, m in benchmark(n_lines, n_edits):
        print(f"{name:<28}{t:>10.3f}{m:>13.1f}")
