"""Задание 6. Мини-проект gradebook: примеры, CLI, свойства, автомат."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
)
from pyrsistent import pmap
from returns.result import Failure, Success

from gradebook.cli import main
from gradebook.core import (
    EMPTY,
    Book,
    apply,
    final,
    finals,
    lab_points,
    replay,
)
from gradebook.model import Mark, Record
from gradebook.parsing import parse_journal, parse_row, to_csv
from gradebook.pipeline import process
from gradebook.report import FORMATS, group_stats, render
from gradebook.scale import LETTERS, Scale, letter_for

S = Scale()
DATA = Path(__file__).resolve().parents[1] / "data"


def full_record(lab: float, rk: float, exam: float | None,
                late: bool = False) -> Record:
    """Запись студента: 15 лабораторных, два РК и экзамен."""
    marks = [Mark("С", "G", f"lab{i:02d}", lab, late) for i in range(1, 16)]
    marks += [Mark("С", "G", f"rk{i}", rk) for i in (1, 2)]
    if exam is not None:
        marks.append(Mark("С", "G", "exam", exam))
    return replay(marks)[("G", "С")]


# ---------------------------------------------------------------- примеры
@pytest.mark.parametrize(("total", "letter"), [
    (100, "A"), (95, "A"), (94.99, "A-"), (90, "A-"), (85, "B+"), (80, "B"),
    (75, "B-"), (70, "C+"), (65, "C"), (60, "C-"), (55, "D+"), (50, "D"),
    (49.99, "FX"), (25, "FX"), (24.99, "F"), (0, "F")])
def test_letter_scale(total: float, letter: str) -> None:
    """Границы буквенной шкалы."""
    assert letter_for(total).letter == letter


@pytest.mark.parametrize("total", [-0.01, 100.01])
def test_letter_out_of_range(total: float) -> None:
    """Итог вне 0..100."""
    with pytest.raises(ValueError, match="вне 0..100"):
        letter_for(total)


def test_lab_points_late_penalty() -> None:
    """Опоздание уменьшает максимум на 10 %."""
    assert lab_points(Mark("a", "g", "lab01", 1.0), S) == 2.0
    assert lab_points(Mark("a", "g", "lab01", 1.0, True), S) == \
        pytest.approx(1.8)


@pytest.mark.parametrize(("lab", "rk", "exam", "letter", "status"), [
    (1.0, 100, 100, "A", "сдано"),
    (0.5, 50, 50, "D", "сдано"),
    (0.5, 50, 49, "FX", "экзамен не сдан"),
    (0.4, 40, 100, "F", "не допущен к экзамену"),
    (0.8, 80, None, "-", "допущен, ждёт экзамена"),
    (0.1, 10, 0, "F", "не допущен к экзамену"),
])
def test_final_cases(lab: float, rk: float, exam: float | None,
                     letter: str, status: str) -> None:
    """Сдал, на границе, не сдал экзамен, не допущен, ждёт экзамена."""
    f = final("С", full_record(lab, rk, exam), S)
    assert (f.letter, f.status) == (letter, status)


def test_final_points() -> None:
    """Баллы: 30·0.5 + 2·15·0.5 + 40·0.5 = 50."""
    f = final("С", full_record(0.5, 50, 50), S)
    assert (f.labs, f.rk, f.admission, f.total) == (15.0, 15.0, 30.0, 50.0)


def test_extra_labs_ignored_and_capped() -> None:
    """Лабораторные сверх lab_count не учитываются."""
    rec = full_record(1.0, 100, 100)
    assert final("С", rec, Scale(lab_count=10, lab_total=30)).labs == 30.0


def test_namesakes_in_different_groups() -> None:
    """Регрессия: однофамильцы из разных групп — разные студенты."""
    book = replay([Mark("Асель", "G", "lab01", 1.0),
                   Mark("Асель", "H", "lab01", 0.0)])
    rows = finals(book, S)
    assert [(f.group, f.labs) for f in rows] == [("G", 2.0), ("H", 0.0)]


def test_correction_replaces_mark() -> None:
    """Повторная оценка заменяет прежнюю (Event Sourcing)."""
    book = replay([Mark("a", "g", "exam", 10), Mark("a", "g", "exam", 90)])
    assert book[("g", "a")].marks["exam"].value == 90
    assert apply(EMPTY, Mark("a", "g", "rk1", 1)) != EMPTY
    assert EMPTY == pmap()


def test_parse_row_results() -> None:
    """returns: Success и Failure с сообщениями."""
    row = {"student": "a", "group": "g", "item": "lab01", "value": "0.5",
           "late": "1"}
    assert parse_row(row) == Success(Mark("a", "g", "lab01", 0.5, True))
    assert parse_row({**row, "late": "да"}) == \
        Failure("late должно быть 0 или 1, а не 'да'")
    assert parse_row({**row, "value": "2"}) == \
        Failure("lab01: значение 2 вне 0..1")
    assert parse_row({**row, "group": ""}) == Failure("нет полей group")


def test_process_sample_journal() -> None:
    """Конвейер на файле data/journal.csv."""
    out = process((DATA / "journal.csv").read_text(encoding="utf-8"), S)
    assert len(out.finals) == 10
    assert len(out.errors) == 4
    statuses = {f.student: f.status for f in out.finals}
    assert statuses["Данияр"] == "не допущен к экзамену"
    assert statuses["Камила"] == "допущен, ждёт экзамена"
    assert statuses["Марат"] == "экзамен не сдан"
    stats = group_stats(out.finals)
    assert [s.group for s in stats] == ["ИС-22", "ПИ-21"]
    assert sum(s.students for s in stats) == 10


def test_render_formats() -> None:
    """Три формата и неизвестный формат."""
    rows = finals(replay([Mark("a", "g", "exam", 90)]), S)
    assert set(FORMATS) == {"txt", "csv", "md"}
    assert render(rows, "csv").startswith("student,group")
    assert "| a | g |" in render(rows, "md")
    with pytest.raises(ValueError, match="неизвестный формат"):
        render(rows, "xls")


def test_cli_commands(tmp_path: Path,
                      capsys: pytest.CaptureFixture[str]) -> None:
    """CLI: report в файл, student, stats, конфигурация и окружение."""
    journal = str(DATA / "journal.csv")
    out_file = tmp_path / "r.md"
    assert main(["--config", str(DATA / "gradebook.toml"), "report",
                 journal, "--group", "ИС-22", "--out", str(out_file)],
                {}) == 0
    assert out_file.read_text(encoding="utf-8").count("ИС-22") == 5
    lines: list[str] = []
    assert main(["student", journal, "Ержан"],
                {"GRADEBOOK_SCALE__LATE_PENALTY": "0.5"}, lines.append) == 0
    assert "88.76" in lines[-1]
    assert main(["student", journal, "Никто"], {}, lines.append) == 1
    assert main(["stats", journal], {}, lines.append) == 0
    assert lines[-1].startswith("ИС-22: студентов 5")
    assert main(["report", journal], {}) == 0
    assert "Студент" in capsys.readouterr().out


# ---------------------------------------------------------------- свойства
names = st.sampled_from(["Асель", "Бек", "Вера", "Гани"])
items = st.sampled_from([f"lab{i:02d}" for i in range(1, 16)]
                        + ["rk1", "rk2", "exam"])


@st.composite
def marks(draw: st.DrawFn) -> Mark:
    """Случайная корректная оценка."""
    item = draw(items)
    limit = 1.0 if item.startswith("lab") else 100.0
    value = draw(st.floats(0, limit, allow_nan=False))
    return Mark(draw(names), draw(st.sampled_from(["G", "H"])), item, value,
                draw(st.booleans()))


journals = st.lists(marks(), max_size=40)


@given(journals)
def test_total_in_range(ms: list[Mark]) -> None:
    """Инвариант: 0 ≤ итог ≤ 100, допуск ≤ 60, лабораторные ≤ 30."""
    for f in finals(replay(ms), S):
        assert 0 <= f.total <= 100
        assert f.admission <= 60 and f.labs <= 30


@given(journals, marks(), st.floats(0, 1))
def test_monotonic(ms: list[Mark], m: Mark, bump: float) -> None:
    """Монотонность: повышение оценки не уменьшает итог."""
    limit = 1.0 if m.item.startswith("lab") else 100.0
    better = Mark(m.student, m.group, m.item,
                  min(limit, m.value + bump * limit), False)
    key = (m.group, m.student)
    before = final(m.student, replay([*ms, m])[key], S).total
    after = final(m.student, replay([*ms, better])[key], S).total
    assert after >= before


@given(st.lists(marks(), max_size=30,
                unique_by=lambda m: (m.group, m.student, m.item)),
       st.randoms())
def test_order_independent(ms: list[Mark], rnd: object) -> None:
    """Без повторов элементов порядок событий не важен."""
    shuffled = list(ms)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert replay(shuffled) == replay(ms)


@given(journals)
def test_replay_idempotent(ms: list[Mark]) -> None:
    """Идемпотентность: повторное применение журнала не меняет состояние."""
    once = replay(ms)
    assert replay(ms, once) == once


@given(journals, journals)
def test_replay_metamorphic(a: list[Mark], b: list[Mark]) -> None:
    """Метаморфное: replay(a + b) == replay(b, replay(a))."""
    assert replay(a + b) == replay(b, replay(a))


@given(st.lists(st.builds(Mark, st.text(st.characters(
    blacklist_categories=("Cs", "Cc", "Zs", "Zl", "Zp")), min_size=1),
    st.just("G"), items, st.floats(0, 1, allow_nan=False),
    st.booleans())))
def test_csv_roundtrip(ms: list[Mark]) -> None:
    """Обратимость: parse_journal(to_csv(ms)) == ms."""
    assert parse_journal(to_csv(ms)) == (tuple(ms), ())


@given(st.floats(0, 100))
def test_letter_total_function(total: float) -> None:
    """Каждому итогу соответствует ровно одна буква; шкала монотонна."""
    matching = [x for x in LETTERS if x.bound <= total]
    assert letter_for(total) == matching[0]
    assert [x.bound for x in LETTERS] == sorted(
        (x.bound for x in LETTERS), reverse=True)


@given(journals)
def test_passed_means_d_or_better(ms: list[Mark]) -> None:
    """Статус «сдано» ⇔ итог ≥ 50 и буква не FX/F/-."""
    for f in finals(replay(ms), S):
        if f.status == "сдано":
            assert f.total >= 50 and f.letter not in ("FX", "F", "-")


# ------------------------------------------- тестирование с состоянием
def flatten(book: Book) -> dict[tuple[str, str, str], Mark]:
    """Журнал → словарь (группа, студент, элемент) → оценка."""
    return {(g, s, i): m for (g, s), r in book.items()
            for i, m in r.marks.items()}


class GradebookMachine(RuleBasedStateMachine):
    """Случайные последовательности операций и инварианты журнала."""

    def __init__(self) -> None:
        """Начальное состояние: пустой журнал и модель-словарь."""
        super().__init__()
        self.book = EMPTY
        self.model: dict[tuple[str, str, str], Mark] = {}
        self.versions: list[tuple[Book, dict[tuple[str, str, str], Mark]]] = []

    @rule(m=marks())
    def add(self, m: Mark) -> None:
        """Добавить или исправить оценку."""
        self.versions.append((self.book, dict(self.model)))
        self.book = apply(self.book, m)
        self.model[(m.group, m.student, m.item)] = m

    @precondition(lambda self: self.model)
    @rule(data=st.data())
    def correct_to_zero(self, data: st.DataObject) -> None:
        """Исправить существующую оценку на ноль."""
        key = data.draw(st.sampled_from(sorted(self.model)))
        old = self.model[key]
        self.add(Mark(old.student, old.group, old.item, 0.0))

    @invariant()
    def matches_model(self) -> None:
        """Состояние совпадает с моделью «последняя оценка по элементу»."""
        assert flatten(self.book) == self.model

    @invariant()
    def totals_valid(self) -> None:
        """Итоги в диапазоне и пересчёт с нуля даёт то же."""
        rows = finals(self.book, S)
        assert all(0 <= f.total <= 100 for f in rows)
        assert rows == finals(replay(self.model.values()), S)

    @invariant()
    def old_versions_intact(self) -> None:
        """Персистентность: старые версии не изменились."""
        for book, model in self.versions[-3:]:
            assert flatten(book) == model


TestGradebookMachine = GradebookMachine.TestCase
