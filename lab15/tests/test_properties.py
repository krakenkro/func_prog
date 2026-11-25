"""Задание 3. Свойства функционального ядра (hypothesis)."""

import contextlib
import io
import runpy
import sys
import tempfile
from itertools import accumulate
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from monitor_fp.core import detect, ordered
from monitor_fp.model import DEFAULT, Metric
from monitor_fp.parsing import parse_log
from monitor_fp.report import render, summarize
from monitor_fp.streams import detect_reactive

LEGACY = Path(__file__).resolve().parents[1] / "legacy" / "monitor_legacy.py"
SERVERS = ("a", "b", "c")

samples = st.tuples(st.integers(0, 45), st.sampled_from(SERVERS),
                    st.floats(0, 100).map(lambda x: round(x, 1)),
                    st.floats(0, 100).map(lambda x: round(x, 1)),
                    st.integers(0, 1000))


@st.composite
def journals(draw: st.DrawFn) -> tuple[Metric, ...]:
    """Журнал с неубывающим временем и паузами до 45 с."""
    rows = draw(st.lists(samples, max_size=60))
    times = accumulate(r[0] for r in rows)
    return tuple(Metric(t, s, c, m, float(lat))
                 for t, (_, s, c, m, lat) in zip(times, rows, strict=True))


def to_csv(ms: tuple[Metric, ...]) -> str:
    """Журнал → текст CSV."""
    return "".join(f"{m.ts},{m.server},{m.cpu},{m.mem},{m.latency}\n"
                   for m in ms)


def run_legacy(text: str) -> list[str]:
    """Вывод исходной программы на тексте журнала."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.csv"
        path.write_text(text, encoding="utf-8")
        buf, argv = io.StringIO(), sys.argv
        sys.argv = ["legacy", str(path)]
        try:
            with contextlib.redirect_stdout(buf), \
                    contextlib.suppress(SystemExit):
                runpy.run_path(str(LEGACY), run_name="__main__")
        finally:
            sys.argv = argv
        return buf.getvalue().splitlines()


@settings(max_examples=60, deadline=None)
@given(journals())
def test_differential_with_legacy(ms: tuple[Metric, ...]) -> None:
    """Эталон: вывод функциональной версии совпадает с исходной."""
    text = to_csv(ms)
    metrics, errors = parse_log(text.splitlines(keepends=True))
    alerts = detect_reactive(metrics)
    assert list(render(errors, alerts, summarize(metrics, alerts))) == \
        run_legacy(text)


@settings(max_examples=150, deadline=None)
@given(journals())
def test_reactive_equals_batch(ms: tuple[Metric, ...]) -> None:
    """RxPY-компонент и пакетный конвейер дают одинаковые оповещения."""
    assert detect_reactive(ms) == detect(ms)


@given(journals(), st.integers(0, 10**6))
def test_time_shift(ms: tuple[Metric, ...], k: int) -> None:
    """Метаморфное: сдвиг всех времён на k сдвигает оповещения на k."""
    shifted = tuple(m._replace(ts=m.ts + k) for m in ms)
    assert detect(shifted) == tuple(a._replace(ts=a.ts + k)
                                    for a in detect(ms))


@given(journals(), st.permutations(SERVERS))
def test_rename_servers(ms: tuple[Metric, ...], names: list[str]) -> None:
    """Метаморфное: переименование серверов переименовывает оповещения."""
    rename = dict(zip(SERVERS, names, strict=True))
    renamed = tuple(m._replace(server=rename[m.server]) for m in ms)
    assert detect(renamed) == ordered(
        a._replace(server=rename[a.server]) for a in detect(ms))


@given(journals())
def test_alternation_invariants(ms: tuple[Metric, ...]) -> None:
    """DOWN/UP и CPU_HIGH/CPU_OK чередуются; MEM_HIGH не чаще cooldown."""
    alerts = detect(ms)
    for s in SERVERS:
        own = [a for a in alerts if a.server == s]
        for pair, first in ((("DOWN", "UP"), "DOWN"),
                            (("CPU_HIGH", "CPU_OK"), "CPU_HIGH")):
            codes = [a.code for a in own if a.code in pair]
            assert all(c == pair[i % 2] for i, c in enumerate(codes))
            assert not codes or codes[0] == first
        mem = [a.ts for a in own if a.code == "MEM_HIGH"]
        assert all(b - a >= DEFAULT.mem_cooldown
                   for a, b in zip(mem, mem[1:], strict=False))


@given(journals())
def test_quiet_journal_no_alerts(ms: tuple[Metric, ...]) -> None:
    """Нормальные значения без пауз > 30 с не дают оповещений."""
    calm = tuple(m._replace(ts=i // 3 * 10, server=SERVERS[i % 3],
                            cpu=min(m.cpu, 70.0), mem=min(m.mem, 90.0),
                            latency=min(m.latency, 500.0))
                 for i, m in enumerate(ms))
    assert detect(calm) == ()
