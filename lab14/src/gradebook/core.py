"""Чистое ядро: свёртка журнала (Event Sourcing) и итоговые оценки."""

from __future__ import annotations

from collections.abc import Iterable
from functools import reduce

from pyrsistent import PMap, pmap

from gradebook.model import Final, Mark, Record
from gradebook.scale import Scale, letter_for

Key = tuple[str, str]                    # (группа, студент)
Book = PMap[Key, Record]
EMPTY: Book = pmap()


def apply(book: Book, mark: Mark) -> Book:
    """Новое состояние журнала: последняя оценка по элементу заменяет.

    Ключ — (группа, студент): однофамильцы из разных групп различаются
    (ошибка, найденная тестированием с состоянием).
    """
    key = (mark.group, mark.student)
    old = book.get(key, Record(mark.group))
    return book.set(key, Record(mark.group, old.marks.set(mark.item, mark)))


def replay(marks: Iterable[Mark], book: Book = EMPTY) -> Book:
    """Свёртка последовательности событий в состояние."""
    return reduce(apply, marks, book)


def lab_points(mark: Mark, scale: Scale) -> float:
    """Баллы за лабораторную: доля × максимум (−10 % за опоздание)."""
    per_lab = scale.lab_total / scale.lab_count
    penalty = 1 - scale.late_penalty if mark.late else 1.0
    return mark.value * per_lab * penalty


def labs_total(record: Record, scale: Scale) -> float:
    """Сумма баллов за лабораторные (не более lab_total)."""
    points = sum(lab_points(m, scale) for m in record.marks.values()
                 if m.is_lab and int(m.item[3:]) <= scale.lab_count)
    return round(min(points, scale.lab_total), 2)


def percent_points(record: Record, item: str, weight: float) -> float:
    """Баллы за элемент, оцениваемый в процентах."""
    mark = record.marks.get(item)
    return 0.0 if mark is None else mark.value / 100 * weight


def final(student: str, record: Record, scale: Scale) -> Final:
    """Итоговая оценка студента по шкале силлабуса."""
    labs = labs_total(record, scale)
    rk = round(percent_points(record, "rk1", scale.rk_weight)
               + percent_points(record, "rk2", scale.rk_weight), 2)
    admission = round(labs + rk, 2)
    admitted = admission >= scale.admission
    exam_mark = record.marks.get("exam")
    exam = None if exam_mark is None else exam_mark.value
    total = round(admission
                  + percent_points(record, "exam", scale.exam_weight), 2)
    if not admitted:
        letter, gpa, word, status = ("F", 0.0, "неудовлетворительно",
                                     "не допущен к экзамену")
    elif exam is None:
        letter, gpa, word, status = "-", 0.0, "-", "допущен, ждёт экзамена"
    elif exam < scale.exam_pass:
        letter, gpa, word, status = (*letter_for(min(total, 49.99))[1:],
                                     "экзамен не сдан")
    else:
        letter, gpa, word, status = (*letter_for(total)[1:], "сдано")
    return Final(student, record.group, labs, rk, admission, admitted,
                 exam, total, letter, gpa, word, status)


def finals(book: Book, scale: Scale,
           group: str | None = None) -> tuple[Final, ...]:
    """Итоги всех студентов (по группе и фамилии)."""
    return tuple(sorted(
        (final(s, r, scale) for (g, s), r in book.items()
         if group is None or g == group),
        key=lambda f: (f.group, f.student)))
