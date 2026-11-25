"""Задания 1–2: ядро, внедрение зависимостей, реестр форматов."""

import runpy
import shutil
from datetime import date
from pathlib import Path

import pytest
from gradesapp import (
    FORMATTERS,
    Grade,
    formatter,
    group_stats,
    make_report,
    parse_csv,
    status_of,
)
from gradesapp.shell import production, run

DATA = Path(__file__).resolve().parents[1] / "data" / "grades.csv"
CSV = "student,group,score\nА,G2,60\nБ,G1,80\nВ,G1,70\nГ,G2,70\n"
DAY = date(2026, 11, 25)


def test_parse_csv() -> None:
    """Разбор CSV в кортеж Grade."""
    assert parse_csv(CSV)[0] == Grade("А", "G2", 60)
    assert parse_csv("student,group,score\n") == ()


def test_parse_csv_bad_score() -> None:
    """Нечисловой балл — ValueError."""
    with pytest.raises(ValueError, match="invalid literal"):
        parse_csv("student,group,score\nА,G,много\n")


@pytest.mark.parametrize(("avg", "expected"),
                         [(70.0, "ОК"), (69.9, "РИСК"), (100, "ОК"),
                          (0, "РИСК")])
def test_status_threshold(avg: float, expected: str) -> None:
    """Граница порога 70 включительно."""
    assert status_of(avg) == expected


def test_group_stats_sorted_and_pure() -> None:
    """Группы по алфавиту, средние верны, вход не изменён."""
    grades = parse_csv(CSV)
    stats = group_stats(grades)
    assert [s.group for s in stats] == ["G1", "G2"]
    assert stats[0].average == 75 and stats[0].status == "ОК"
    assert stats[1].average == 65 and stats[1].status == "РИСК"
    assert grades == parse_csv(CSV)


def test_make_report_formats() -> None:
    """Три формата отчёта из реестра."""
    assert set(FORMATTERS) >= {"txt", "csv", "md"}
    assert make_report(CSV, DAY).report == "Отчёт от 2026-11-25: групп 2\n"
    assert "2026-11-25,G1,75.0,ОК" in make_report(CSV, DAY, "csv").report
    assert "| G2 | 65.0 | РИСК |" in make_report(CSV, DAY, "md").report
    with pytest.raises(ValueError, match="неизвестный формат"):
        make_report(CSV, DAY, "pdf")


def test_formatter_duplicate_rejected() -> None:
    """Повторная регистрация формата запрещена."""
    with pytest.raises(ValueError, match="уже зарегистрирован"):
        formatter("txt")(lambda stats, today: "")


def test_shell_with_fake_dependencies() -> None:
    """Оболочка с «фальшивыми» зависимостями: список, дата, запись в список."""
    shown: list[str] = []
    written: list[str] = []
    run(lambda: CSV, lambda: DAY, written.append, shown.append, "md")
    assert shown == ["2026-11-25 G1: средний 75.0 [ОК]",
                     "2026-11-25 G2: средний 65.0 [РИСК]"]
    assert written[0].startswith("# Отчёт от 2026-11-25")


def test_same_behaviour_as_legacy(tmp_path: Path, monkeypatch:
                                  pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    """Вывод и файл отчёта совпадают с исходной монолитной программой."""
    shutil.copy(DATA, tmp_path / "grades.csv")
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(DATA.parents[1] / "legacy_grades.py"))
    legacy_out = capsys.readouterr().out
    legacy_report = (tmp_path / "report.txt").read_text(encoding="utf-8")
    (tmp_path / "report.txt").unlink()
    production(Path("grades.csv"), Path("report.txt"))()
    assert capsys.readouterr().out == legacy_out
    assert (tmp_path / "report.txt").read_text(encoding="utf-8") == \
        legacy_report
