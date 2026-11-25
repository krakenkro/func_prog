"""Задание 6 (вариант 4): ядро рейтинга, загрузчик, параллельный расчёт."""

import asyncio

import pytest
from rating import (
    DEFAULT_WEIGHTS,
    Entry,
    StudentScore,
    Weights,
    build_report,
    letter,
    parse_journal,
    parse_line,
    rank,
    score_group,
    summarize_group,
)
from rating.core import kind_of, student_percent
from rating.loader import load_groups, load_sequential, split_results
from rating.parallel import build_report_parallel
from rating.shell import main, render
from rating.source import journal_text, make_fetch

JOURNAL = """# тест
Асель;lab1;5;5
Асель;lab2;4;5
Асель;rk1;80;100
Асель;exam;90;100
Бек;lab1;3;5
Бек;rk1;60;100
Бек;exam;50;100
"""


def entries() -> tuple[Entry, ...]:
    """Записи тестового журнала."""
    return parse_journal("G", JOURNAL)[0]


def test_parse_line_ok() -> None:
    """Корректная строка."""
    assert parse_line("G", "Асель; lab1 ; 4.5 ;5") == \
        Entry("Асель", "G", "lab1", 4.5, 5.0)


@pytest.mark.parametrize("line", ["Асель;lab1;4", "Асель;lab1;6;5",
                                  "Асель;lab1;-1;5", ";lab1;1;5",
                                  "Асель;lab1;1;0"])
def test_parse_line_errors(line: str) -> None:
    """Неверное число полей, диапазон балла, пустые поля."""
    with pytest.raises(ValueError, match="ожидалось 4 поля|вне диапазона"):
        parse_line("G", line)


def test_parse_journal_collects_errors() -> None:
    """Ошибочные строки не прерывают разбор, номер строки сохраняется."""
    good, errors = parse_journal("G", JOURNAL + "плохо\n")
    assert len(good) == 7
    assert errors == ("G:9: ожидалось 4 поля: 'плохо'",)


def test_kind_of() -> None:
    """Вид работы по имени."""
    assert [kind_of(t) for t in ("lab12", "rk2", "exam")] == \
        ["lab", "rk", "exam"]
    with pytest.raises(ValueError, match="неизвестный вид"):
        kind_of("quiz1")


def test_student_percent_weights() -> None:
    """Взвешенный процент: 0.3·0.9 + 0.3·0.8 + 0.4·0.9 = 87 %."""
    maxima = {"lab1": 5.0, "lab2": 5.0, "rk1": 100.0, "exam": 100.0}
    scores = {"lab1": 5, "lab2": 4, "rk1": 80, "exam": 90}
    assert student_percent(scores, maxima) == 87.0


def test_missing_work_counts_as_zero() -> None:
    """Несданная lab2 у Бека — ноль: 0.3·0.3 + 0.3·0.6 + 0.4·0.5 = 47 %."""
    scores = dict((s.student, s.percent) for s in score_group(entries()))
    assert scores == {"Асель": 87.0, "Бек": 47.0}


def test_weights_normalized_when_kind_absent() -> None:
    """Если в группе нет экзамена, веса lab и rk нормируются."""
    maxima = {"lab1": 5.0, "rk1": 100.0}
    assert student_percent({"lab1": 5, "rk1": 50}, maxima) == 75.0
    assert student_percent({}, {}) == 0.0
    assert student_percent({"lab1": 5}, {"lab1": 5.0},
                           Weights(0, 0, 1)) == 0.0


def test_correction_last_entry_wins() -> None:
    """Повторная запись (исправление) заменяет предыдущую."""
    fixed = (*entries(), Entry("Бек", "G", "exam", 100, 100))
    assert dict((s.student, s.percent)
                for s in score_group(fixed))["Бек"] == 67.0


def test_rank_ties_share_place() -> None:
    """Равные проценты — одно место, следующее место пропускается."""
    scores = [StudentScore("В", "G", 80), StudentScore("А", "G", 90),
              StudentScore("Б", "H", 80), StudentScore("Г", "H", 10)]
    assert [(r.rank, r.student) for r in rank(scores)] == \
        [(1, "А"), (2, "В"), (2, "Б"), (4, "Г")]


@pytest.mark.parametrize(("p", "sym"), [(100, "A"), (90, "A"), (89.99, "B"),
                                        (75, "B"), (60, "C"), (50, "D"),
                                        (49.9, "F"), (0, "F")])
def test_letter_bounds(p: float, sym: str) -> None:
    """Границы буквенной шкалы."""
    assert letter(p) == sym


def test_summarize_group() -> None:
    """Сводка по группе и пустая группа."""
    s = summarize_group("G", score_group(entries()))
    assert (s.students, s.mean, s.median, s.best) == (2, 67.0, 67.0, "Асель")
    assert summarize_group("E", ()).students == 0


def test_build_report_and_purity() -> None:
    """Конвейер: рейтинг по всем группам, ошибки и сбои загрузки."""
    journals = (("G", JOURNAL), ("H", "Ян;exam;95;100\nплохо\n"))
    report = build_report(journals, failed=("X: сбой",))
    assert [r.student for r in report.ranking] == ["Ян", "Асель", "Бек"]
    assert report.errors == ("X: сбой", "H:2: ожидалось 4 поля: 'плохо'")
    assert build_report(journals, failed=("X: сбой",)) == report
    assert "Место" in render(report)[0]


def test_parallel_equals_sequential() -> None:
    """Расчёт в пуле процессов совпадает с последовательным."""
    journals = tuple((g, journal_text(g, 30)) for g in ("A", "B", "C"))
    assert build_report_parallel(journals, workers=2) == \
        build_report(journals, DEFAULT_WEIGHTS)


def test_split_results() -> None:
    """Разделение успешных загрузок и ошибок."""
    loaded = split_results(("A", "B", "C"),
                           ("текст", ConnectionError("нет"), TimeoutError()))
    assert loaded.journals == (("A", "текст"),)
    assert loaded.failed == ("B: ConnectionError: нет",
                             "C: TimeoutError: превышено время ожидания")


def test_async_loader_limit_and_timeout() -> None:
    """Не более limit одновременных загрузок; медленная — тайм-аут."""
    active, peak = [0], [0]

    async def fetch(group: str) -> str:
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.2 if group == "slow" else 0.01)
        active[0] -= 1
        return group

    groups = ("a", "b", "c", "d", "e", "slow")
    loaded = asyncio.run(load_groups(groups, fetch, limit=2, timeout=0.1))
    assert peak[0] <= 2
    assert [g for g, _ in loaded.journals] == ["a", "b", "c", "d", "e"]
    assert loaded.failed[0].startswith("slow: TimeoutError")
    seq = asyncio.run(load_sequential(groups, fetch, timeout=0.1))
    assert seq == loaded


def test_shell_main_with_fake_fetch() -> None:
    """Оболочка с внедрённым мгновенным источником и выводом в список."""

    async def no_wait(_: float) -> None:
        return None

    lines: list[str] = []
    fetch = make_fetch({}, frozenset({"B"}), students=5, sleep=no_wait)
    report = asyncio.run(main(fetch, ("A", "B"), lines.append))
    assert {g.group for g in report.groups} == {"A"}
    assert any("B: ConnectionError" in line for line in lines)
