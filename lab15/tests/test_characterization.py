"""Задание 2. Характеризационные тесты: поведение исходной программы.

Каждый тест выполняется для обеих реализаций — исходной (legacy) и
функциональной (``python -m monitor_fp``); вывод должен совпадать.
"""

import runpy
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "monitor_legacy.py"
GOLDEN = Path(__file__).parent / "golden" / "metrics_output.txt"
IMPLS = ("legacy", "functional")
Log = Callable[..., str]


def run(impl: str, args: list[str], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    """Запустить реализацию как программу; (код возврата, строки вывода)."""
    monkeypatch.setattr(sys, "argv", ["monitor", *args])
    try:
        if impl == "legacy":
            runpy.run_path(str(LEGACY), run_name="__main__")
        else:
            runpy.run_module("monitor_fp", run_name="__main__",
                             alter_sys=True)
        code = 0
    except SystemExit as exc:
        code = int(exc.code or 0)
    return code, capsys.readouterr().out.splitlines()


@pytest.fixture
def log(tmp_path: Path) -> Log:
    """Фабрика файлов журнала во временном каталоге."""

    def make(*lines: str) -> str:
        path = tmp_path / "m.csv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    return make


def alerts(out: list[str]) -> list[str]:
    """Только строки оповещений."""
    return [line for line in out if line.startswith("[")]


@pytest.fixture(params=IMPLS)
def impl(request: pytest.FixtureRequest) -> str:
    """Реализация под тестом."""
    return str(request.param)


def test_golden_sample(impl: str, monkeypatch: pytest.MonkeyPatch,
                       capsys: pytest.CaptureFixture[str]) -> None:
    """Полный вывод на эталонном журнале совпадает с сохранённым."""
    code, out = run(impl, [str(ROOT / "data" / "metrics.csv")],
                    monkeypatch, capsys)
    assert code == 0
    assert out == GOLDEN.read_text(encoding="utf-8").splitlines()


def test_usage(impl: str, monkeypatch: pytest.MonkeyPatch,
               capsys: pytest.CaptureFixture[str]) -> None:
    """Без аргументов — подсказка и код 1."""
    code, out = run(impl, [], monkeypatch, capsys)
    assert code == 1
    assert out[0].startswith("использование:")


def test_empty_log(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Пустой журнал: только итоги."""
    _, out = run(impl, [log("# пусто", "")], monkeypatch, capsys)
    assert out == ["=== Итоги ===",
                   "Всего оповещений: 0, ошибок разбора: 0"]


def test_parse_errors(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Ошибки разбора с номерами строк (комментарии тоже нумеруются)."""
    _, out = run(impl, [log("# c", "1,a,1,1", "2,a,x,1,1", "3, ,1,1,1",
                            "4,a,101,1,1", "5,a,1,1,-1", "6,a,1,1,1")],
                 monkeypatch, capsys)
    assert out[:5] == [
        "ПРЕДУПРЕЖДЕНИЕ: строка 2: неверное число полей",
        "ПРЕДУПРЕЖДЕНИЕ: строка 3: не число",
        "ПРЕДУПРЕЖДЕНИЕ: строка 4: пустое имя сервера",
        "ПРЕДУПРЕЖДЕНИЕ: строка 5: значение вне диапазона",
        "ПРЕДУПРЕЖДЕНИЕ: строка 6: значение вне диапазона"]
    assert out[-1] == "Всего оповещений: 0, ошибок разбора: 5"


def test_time_order(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Строка с меньшим временем отбрасывается."""
    _, out = run(impl, [log("10,a,1,1,1", "5,a,1,1,1", "10,a,1,1,1")],
                 monkeypatch, capsys)
    assert out[0] == "ПРЕДУПРЕЖДЕНИЕ: строка 2: нарушен порядок времени"
    assert "a: замеров 2, CPU max 1.0%, задержка ср. 1.0 мс, " \
           "оповещений 0" in out


def test_cpu_hysteresis(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """CPU: тревога при среднем > 85, отбой при < 70, между — без изменений."""
    cpu = (90, 90, 80, 95, 99, 80, 75, 60, 50, 90, 90, 90)
    lines = [f"{i * 5},s,{c},1,1" for i, c in enumerate(cpu)]
    _, out = run(impl, [log(*lines)], monkeypatch, capsys)
    assert alerts(out) == [
        "[    10] CRIT s: CPU 86.7% (среднее за 3 замера)",
        "[    40] INFO s: CPU 61.7%, нагрузка снизилась",
        "[    55] CRIT s: CPU 90.0% (среднее за 3 замера)"]


def test_cpu_needs_three_samples(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Окно из трёх замеров считается отдельно для каждого сервера."""
    _, out = run(impl, [log("0,a,99,1,1", "1,b,99,1,1", "2,a,99,1,1",
                            "3,b,10,1,1", "4,a,99,1,1")],
                 monkeypatch, capsys)
    assert alerts(out) == ["[     4] CRIT a: CPU 99.0% (среднее за 3 замера)"]


def test_memory_cooldown(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Память: не чаще одного оповещения за 60 с."""
    lines = [f"{t},db,1,{m},1" for t, m in
             ((0, 95), (20, 96), (40, 97), (59, 97), (60, 91), (80, 50),
              (100, 92), (120, 90.5))]
    _, out = run(impl, [log(*lines)], monkeypatch, capsys)
    assert alerts(out) == ["[     0] WARN db: память 95.0%",
                           "[    60] WARN db: память 91.0%",
                           "[   120] WARN db: память 90.5%"]


def test_slow_two_in_a_row(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Задержка: оповещение на втором подряд замере, затем сброс серии."""
    lat = (600, 100, 600, 700, 800, 100, 501, 502)
    lines = [f"{i},w,1,1,{v}" for i, v in enumerate(lat)]
    _, out = run(impl, [log(*lines)], monkeypatch, capsys)
    assert alerts(out) == [
        "[     3] WARN w: задержка 700 мс два замера подряд",
        "[     7] WARN w: задержка 502 мс два замера подряд"]


def test_down_and_up(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Молчание > 30 с: DOWN в момент last + 30, затем UP; ровно 30 — норма."""
    lines = ["0,a,1,1,1", "0,b,1,1,1", "30,a,1,1,1", "40,b,1,1,1",
             "61,a,1,1,1", "75,b,1,1,1"]
    _, out = run(impl, [log(*lines)], monkeypatch, capsys)
    assert alerts(out) == ["[    30] CRIT b: нет данных более 30 с",
                           "[    40] INFO b: данные снова поступают",
                           "[    60] CRIT a: нет данных более 30 с",
                           "[    61] INFO a: данные снова поступают",
                           "[    70] CRIT b: нет данных более 30 с",
                           "[    75] INFO b: данные снова поступают"]


def test_down_at_end_of_log(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Сервер замолчал до конца журнала — DOWN без UP."""
    _, out = run(impl, [log("0,a,1,1,1", "0,b,1,1,1", "20,b,1,1,1",
                            "40,b,1,1,1")], monkeypatch, capsys)
    assert alerts(out) == ["[    30] CRIT a: нет данных более 30 с"]
    assert "a: замеров 1, CPU max 1.0%, задержка ср. 1.0 мс, " \
           "оповещений 1" in out


def test_same_time_ordering(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Оповещения одного момента упорядочены по серверу и коду."""
    lines = ["0,b,99,99,900", "0,a,99,99,900", "1,b,99,95,900",
             "1,a,99,95,900", "2,b,99,1,1", "2,a,99,1,1"]
    _, out = run(impl, [log(*lines)], monkeypatch, capsys)
    assert alerts(out) == [
        "[     0] WARN a: память 99.0%",
        "[     0] WARN b: память 99.0%",
        "[     1] WARN a: задержка 900 мс два замера подряд",
        "[     1] WARN b: задержка 900 мс два замера подряд",
        "[     2] CRIT a: CPU 99.0% (среднее за 3 замера)",
        "[     2] CRIT b: CPU 99.0% (среднее за 3 замера)"]


def test_report_file(impl: str, log: Log, tmp_path: Path,
                     monkeypatch: pytest.MonkeyPatch,
                     capsys: pytest.CaptureFixture[str]) -> None:
    """Файл отчёта: число оповещений по кодам."""
    report = tmp_path / f"{impl}.csv"
    _, out = run(impl, [log("0,a,99,99,1", "40,b,1,1,1"), str(report)],
                 monkeypatch, capsys)
    assert out[-1] == f"отчёт: {report}"
    assert report.read_text(encoding="utf-8") == \
        "code,count\nDOWN,1\nMEM_HIGH,1\n"


def test_summary_lines(
        impl: str, log: Log, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """Итоги по серверам в алфавитном порядке."""
    _, out = run(impl, [log("0,z,10,1,100", "1,a,20,1,200", "2,z,30,1,300")],
                 monkeypatch, capsys)
    assert out[-3:] == [
        "a: замеров 1, CPU max 20.0%, задержка ср. 200.0 мс, оповещений 0",
        "z: замеров 2, CPU max 30.0%, задержка ср. 200.0 мс, оповещений 0",
        "Всего оповещений: 0, ошибок разбора: 0"]
