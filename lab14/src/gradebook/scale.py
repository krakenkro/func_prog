"""Шкала оценивания силлабуса (баллы и буквенная система)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple


class Scale(NamedTuple):
    """Распределение 100 баллов и правила допуска.

    Лабораторные — 30 баллов на 15 работ, за несвоевременную сдачу
    максимум уменьшается на 10 %; РК1 и РК2 — по 15 баллов; экзамен — 40.
    Допуск к экзамену — не менее 30 из 60 баллов текущего контроля;
    экзамен сдан при результате не ниже 50 %.
    """

    lab_count: int = 15
    lab_total: float = 30.0
    late_penalty: float = 0.1
    rk_weight: float = 15.0
    exam_weight: float = 40.0
    admission: float = 30.0
    exam_pass: float = 50.0


class Letter(NamedTuple):
    """Буквенная оценка."""

    bound: float
    letter: str
    gpa: float
    word: str


LETTERS: tuple[Letter, ...] = (
    Letter(95, "A", 4.0, "отлично"),
    Letter(90, "A-", 3.67, "отлично"),
    Letter(85, "B+", 3.33, "хорошо"),
    Letter(80, "B", 3.0, "хорошо"),
    Letter(75, "B-", 2.67, "хорошо"),
    Letter(70, "C+", 2.33, "удовлетворительно"),
    Letter(65, "C", 2.0, "удовлетворительно"),
    Letter(60, "C-", 1.67, "удовлетворительно"),
    Letter(55, "D+", 1.33, "удовлетворительно"),
    Letter(50, "D", 1.0, "удовлетворительно"),
    Letter(25, "FX", 0.0, "неудовлетворительно"),
    Letter(0, "F", 0.0, "неудовлетворительно"),
)


def letter_for(total: float) -> Letter:
    """Буквенная оценка по итоговому баллу 0..100."""
    if not 0 <= total <= 100:
        raise ValueError(f"итоговый балл вне 0..100: {total}")
    return next(x for x in LETTERS if total >= x.bound)


def scale_from_config(cfg: Mapping[str, Any]) -> Scale:
    """Шкала из раздела ``scale`` конфигурации (лишние ключи — ошибка)."""
    section = dict(cfg.get("scale", {}))
    unknown = set(section) - set(Scale._fields)
    if unknown:
        raise ValueError(f"неизвестные параметры шкалы: {sorted(unknown)}")
    scale = Scale(**section)
    if scale.admission + scale.exam_weight * scale.exam_pass / 100 < 50:
        raise ValueError("сданный экзамен должен давать не меньше 50 баллов")
    total = scale.lab_total + 2 * scale.rk_weight + scale.exam_weight
    if abs(total - 100) > 1e-9:
        raise ValueError(f"сумма весов должна быть 100, а не {total:g}")
    return scale
