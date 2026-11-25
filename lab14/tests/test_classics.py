"""Задание 1. Модульные тесты pytest: параметризация, исключения, фикстуры."""

from pathlib import Path

import pytest

from fpkit.classics import (
    apply_tx,
    clamp,
    fold_balance,
    mean,
    merge,
    merge_sort,
    normalize,
    parse_int,
    print_table,
    rle_decode,
    rle_encode,
    safe_div,
    word_freq,
    write_report,
)
from fpkit.result import Err, Ok


@pytest.fixture
def journal() -> tuple[tuple[str, int], ...]:
    """Неизменяемый тестовый журнал операций."""
    return (("deposit", 100), ("withdraw", 30), ("deposit", 5),
            ("withdraw", 75))


@pytest.fixture
def scores() -> tuple[tuple[str, float], ...]:
    """Неизменяемый набор пар (имя, балл)."""
    return (("Асель", 91.5), ("Бек", 70.0), ("Вера", 64.25))


@pytest.mark.parametrize(("x", "lo", "hi", "expected"), [
    (5, 0, 10, 5), (-1, 0, 10, 0), (11, 0, 10, 10), (0, 0, 0, 0),
    (10, 0, 10, 10), (-5.5, -10, -1, -5.5)])
def test_clamp(x: float, lo: float, hi: float, expected: float) -> None:
    """Значения внутри, на границах и вне отрезка."""
    assert clamp(x, lo, hi) == expected


def test_clamp_empty_interval() -> None:
    """lo > hi — ошибка."""
    with pytest.raises(ValueError, match=r"пустой отрезок \[2, 1\]"):
        clamp(0, 2, 1)


@pytest.mark.parametrize(("xs", "expected"), [
    ([1], 1), ([1, 2], 1.5), ([-1, 1], 0), ([0.1, 0.2, 0.3], 0.2),
    ([10**9, 10**9], 10**9)])
def test_mean(xs: list[float], expected: float) -> None:
    """Среднее, включая одиночный элемент и большие числа."""
    assert mean(xs) == pytest.approx(expected)


def test_mean_empty() -> None:
    """Пустой список — ошибка."""
    with pytest.raises(ValueError, match="пустой"):
        mean([])


@pytest.mark.parametrize(("s", "expected"), [
    ("", ""), ("  ", ""), ("A  b", "a b"), ("\tМир\n", "мир"),
    ("x", "x"), (" Hello   WORLD ", "hello world")])
def test_normalize(s: str, expected: str) -> None:
    """Пустая строка, пробелы, табуляция, регистр."""
    assert normalize(s) == expected


@pytest.mark.parametrize(("text", "expected"), [
    ("", {}), ("а", {"а": 1}), ("А а!", {"а": 2}),
    ("ФП, фп; FP", {"фп": 2, "fp": 1}), ("1 1 2", {"1": 2, "2": 1})])
def test_word_freq(text: str, expected: dict[str, int]) -> None:
    """Регистр и знаки препинания не влияют."""
    assert word_freq(text) == expected


@pytest.mark.parametrize(("s", "code"), [
    ("", ""), ("a", "a1;"), ("aaab", "a3;b1;"), ("11", "12;"),
    (";;", ";2;"), ("a" * 12, "a12;")])
def test_rle_encode(s: str, code: str) -> None:
    """Пустая строка, цифры и разделитель внутри данных, длинные серии."""
    assert rle_encode(s) == code
    assert rle_decode(code) == s


@pytest.mark.parametrize("code", ["a", "a;", "ab;", "a1", "a1;b"])
def test_rle_decode_errors(code: str) -> None:
    """Повреждённый код — ValueError."""
    with pytest.raises(ValueError, match="неверный RLE-код"):
        rle_decode(code)


@pytest.mark.parametrize(("balance", "tx", "expected"), [
    (0, ("deposit", 1), 1), (10, ("withdraw", 10), 0),
    (10, ("withdraw", 1), 9), (5, ("deposit", 10**6), 10**6 + 5),
    (1, ("withdraw", 1), 0)])
def test_apply_tx(balance: int, tx: tuple[str, int], expected: int) -> None:
    """Пополнение и снятие, включая снятие всего остатка."""
    assert apply_tx(balance, tx) == expected


@pytest.mark.parametrize(("tx", "message"), [
    (("withdraw", 11), "недостаточно средств"),
    (("deposit", 0), "положительной"),
    (("deposit", -5), "положительной"),
    (("refund", 1), "неизвестная операция 'refund'")])
def test_apply_tx_errors(tx: tuple[str, int], message: str) -> None:
    """Ошибочные операции с проверкой текста сообщения."""
    with pytest.raises(ValueError, match=message):
        apply_tx(10, tx)


def test_fold_balance(journal: tuple[tuple[str, int], ...]) -> None:
    """Свёртка журнала; фикстура не изменяется."""
    copy = tuple(journal)
    assert fold_balance(journal) == 0
    assert fold_balance(journal, 50) == 50
    assert fold_balance(()) == 0
    assert journal == copy


def test_fold_balance_overdraft(journal: tuple[tuple[str, int], ...]) -> None:
    """Перерасход в середине журнала."""
    with pytest.raises(ValueError, match="недостаточно"):
        fold_balance((("withdraw", 1), *journal))


@pytest.mark.parametrize(("a", "b", "expected"), [
    ([], [], []), ([1], [], [1]), ([], [2], [2]), ([1, 3], [2], [1, 2, 3]),
    ([1, 1], [1], [1, 1, 1]), ([5], [1, 2], [1, 2, 5])])
def test_merge(a: list[int], b: list[int], expected: list[int]) -> None:
    """Пустые списки, повторы, разные длины."""
    assert merge(a, b) == expected


@pytest.mark.parametrize("xs", [[], [1], [2, 1], [3, 1, 2, 1], [-1, -5, 0],
                                list(range(10, 0, -1))])
def test_merge_sort(xs: list[int]) -> None:
    """Совпадение с sorted, вход не изменяется."""
    before = list(xs)
    assert merge_sort(xs) == sorted(xs)
    assert xs == before


@pytest.mark.parametrize(("s", "expected"), [
    ("42", Ok(42)), (" -7 ", Ok(-7)), ("+0", Ok(0)),
    ("4.2", Err("не целое число: '4.2'")), ("", Err("не целое число: ''")),
    ("x1", Err("не целое число: 'x1'"))])
def test_parse_int(s: str, expected: object) -> None:
    """Result вместо исключения."""
    assert parse_int(s) == expected


@pytest.mark.parametrize(("a", "b", "expected"), [
    (1, 2, Ok(0.5)), (0, 5, Ok(0.0)), (-4, 2, Ok(-2.0)),
    (1, 0, Err("деление на ноль")), (0, 0, Err("деление на ноль"))])
def test_safe_div(a: float, b: float, expected: object) -> None:
    """Деление и деление на ноль."""
    assert safe_div(a, b) == expected


def test_result_chain() -> None:
    """map/bind/unwrap_or собственного Result."""
    assert parse_int("10").bind(lambda x: safe_div(1, x)).map(
        lambda v: v * 2).unwrap_or(-1.0) == 0.2
    assert parse_int("0").bind(lambda x: safe_div(1, x)).map(
        lambda v: v * 2).unwrap_or(-1.0) == -1.0


def test_write_report(tmp_path: Path,
                      scores: tuple[tuple[str, float], ...]) -> None:
    """Функция оболочки пишет файл во временный каталог."""
    path = tmp_path / "report.txt"
    assert write_report(path, scores) == 3
    assert path.read_text(encoding="utf-8").splitlines() == [
        "Асель: 91.50", "Бек: 70.00", "Вера: 64.25"]


def test_print_table(capsys: pytest.CaptureFixture[str],
                     scores: tuple[tuple[str, float], ...]) -> None:
    """Функция оболочки печатает таблицу на экран."""
    print_table(scores)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Асель          91.50"
    assert len(out) == 3
