"""Задание 4. toolz, pyrsistent (конфигурация), returns."""

import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pyrsistent import PMap, freeze

from fpkit import toolz_rating as tr
from fpkit.validation import Row, as_pair, parse_own, parse_returns
from gradebook.config import DEFAULTS, deep_merge, env_overrides, load_config
from gradebook.scale import Scale, scale_from_config

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lab13"))
from rating import build_report  # noqa: E402  (ЛР 13)
from rating.source import journal_text  # noqa: E402


def test_toolz_pipeline_equals_lab13() -> None:
    """Конвейер на toolz даёт тот же рейтинг, что версия ЛР 13."""
    journals = tuple((g, journal_text(g, 40)) for g in ("A", "B", "C"))
    expected = [(r.rank, r.student, r.group, r.percent)
                for r in build_report(journals).ranking]
    assert tr.ranking(journals) == expected


def test_toolz_parse_skips_bad_lines() -> None:
    """Ошибочные строки и комментарии отбрасываются."""
    rows = tr.parse("G", "# к\nА;lab1;5;5\nА;lab1;9;5\nплохо\nБ;rk1;x;100\n")
    assert [r["student"] for r in rows] == ["А"]


def test_lab_trend_sliding_window() -> None:
    """Динамика по соседним лабораторным (sliding_window)."""
    rows = [{"task": f"lab{i}", "score": s, "max": 5.0}
            for i, s in ((1, 2), (2, 3), (3, 5))]
    assert tr.lab_trend(rows) == 0.3
    assert tr.lab_trend(rows[:1]) == 0.0
    assert tr.percent([], {}) == 0.0


def test_config_merge_order() -> None:
    """Умолчания ← файл ← окружение; результат неизменяем."""
    cfg = load_config('[scale]\nexam_weight = 30\nlab_total = 40\n'
                      '[report]\nformat = "md"\n',
                      {"GRADEBOOK_REPORT__FORMAT": "csv",
                       "GRADEBOOK_SCALE__LATE_PENALTY": "0.2",
                       "HOME": "/tmp"})
    assert isinstance(cfg, PMap)
    assert cfg["report"]["format"] == "csv"
    assert cfg["scale"]["exam_weight"] == 30
    assert cfg["scale"]["late_penalty"] == 0.2
    assert cfg["scale"]["rk_weight"] == 15.0
    assert DEFAULTS["report"]["format"] == "txt"          # не изменились
    with pytest.raises(TypeError):
        cfg["scale"]["exam_weight"] = 1  # type: ignore[index]


def test_env_overrides_types() -> None:
    """Значения окружения разбираются как скаляры TOML."""
    assert env_overrides({"GRADEBOOK_A__B": "1", "GRADEBOOK_C": "x y",
                          "GRADEBOOK_D": "true"}) == \
        {"a": {"b": 1}, "c": "x y", "d": True}


def test_deep_merge_replaces_scalars() -> None:
    """Вложенные словари сливаются, скаляры заменяются."""
    base = freeze({"a": {"x": 1, "y": 2}, "b": 1})
    assert deep_merge(base, {"a": {"y": 3}, "b": {"z": 0}}) == \
        freeze({"a": {"x": 1, "y": 3}, "b": {"z": 0}})


def test_scale_from_config_validation() -> None:
    """Шкала из конфигурации: проверки суммы весов и лишних ключей."""
    assert scale_from_config(DEFAULTS) == Scale()
    with pytest.raises(ValueError, match="сумма весов"):
        scale_from_config(load_config("[scale]\nexam_weight = 50\n", {}))
    with pytest.raises(ValueError, match="неизвестные параметры"):
        scale_from_config({"scale": {"bonus": 1}})
    with pytest.raises(ValueError, match="не меньше 50"):
        scale_from_config({"scale": {"admission": 10, "exam_pass": 50}})


@pytest.mark.parametrize(("line", "ok"), [
    ("А;lab1;4;5", True), ("А;lab1;6;5", False), ("А;lab1;x;5", False),
    ("А;lab1;4", False), ("А;lab1;1;0", False), (";lab1;1;5", False)])
def test_validation_examples(line: str, ok: bool) -> None:
    """Обе реализации: успех и ошибки."""
    assert as_pair(parse_own(line))[0] is ok
    assert as_pair(parse_returns(line))[0] is ok


def test_validation_success_value() -> None:
    """Значение успешного разбора."""
    assert as_pair(parse_returns("А; lab1 ;4;5")) == \
        (True, Row("А", "lab1", 4.0, 5.0))


@given(st.lists(st.sampled_from(["А", "lab1", "4", "5", "x", "-1", "",
                                 "1e3", "0"]), max_size=5).map(";".join))
def test_own_result_equals_returns(line: str) -> None:
    """Свой Result и returns дают одинаковый результат на любых строках."""
    assert as_pair(parse_own(line)) == as_pair(parse_returns(line))
