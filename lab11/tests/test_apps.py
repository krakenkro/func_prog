"""Тесты заданий 1, 4, 5, 6 и дополнительного задания ЛР 11."""

from pathlib import Path
from types import MappingProxyType

import chat_app as chat
import observer_classic as oc
import pytest
import server_monitor as sm
import spreadsheet as ss
from rx_mini import Cell, Observable, Subject, map_, take, transaction
from rx_mini.scheduler import (
    VirtualScheduler,
    debounce,
    delay,
    interval,
    record,
    throttle_first,
    timed_hot,
)
from rx_mini.testing import marble, materialize, values


# ------------------------------ Задание 1 ---------------------------------
def test_classic_and_reactive_agree() -> None:
    """EventSource и Observable дают одинаковый результат."""
    assert oc.classic_demo(oc.READINGS) == oc.reactive_demo(oc.READINGS)


def test_event_source_unsubscribe() -> None:
    """Функция отписки EventSource работает."""
    src, got = oc.EventSource(), []
    unsub = src.subscribe(got.append)
    src.emit(1)
    unsub()
    src.emit(2)
    assert got == [1]


# ------------------------------ Задание 4 ---------------------------------
def test_diamond_recomputes_once() -> None:
    """Ромб A→B, A→C, (B,C)→D: D пересчитывается один раз."""
    a = Cell(1, name="a")
    b = Cell.formula(lambda x: x + 1, a)
    c = Cell.formula(lambda x: x * 2, a)
    seen = []
    d = Cell.formula(lambda x, y: (x, y), b, c)
    d.subscribe(seen.append)
    a.set(5)
    assert d.value == (6, 10) and d.recompute_count == 1
    assert seen == [(6, 10)]  # ни одного «полуобновлённого»


def test_no_change_no_recompute() -> None:
    """Если зависимость не изменилась, формула не пересчитывается."""
    a = Cell(1)
    b = Cell.formula(lambda x: x % 2, a)
    c = Cell.formula(lambda x: x * 100, b)
    a.set(3)  # b не изменилась → c не трогаем
    assert b.recompute_count == 1 and c.recompute_count == 0


def test_sheet_and_transaction() -> None:
    """Модель таблицы и атомарная транзакция."""
    sheet = ss.build_sheet()
    totals = []
    sheet["total"].subscribe(totals.append)
    sheet["qty"].set(3)
    transaction((sheet["price"], 1000.0), (sheet["discount"], 0.5))
    assert totals == [5040.0, 1680.0]
    assert sheet["total"].recompute_count == 2
    with pytest.raises(TypeError):
        sheet["total"].set(0)


def test_cell_observe_stream() -> None:
    """observe() выдаёт текущее значение и изменения."""
    a = Cell(1)
    got = []
    a.observe().subscribe(got.append)
    a.set(2)
    assert got == [1, 2]


# ------------------------------ Задание 5 ---------------------------------
def test_monitoring_alerts_marbles() -> None:
    """Оповещения мониторинга (мраморные диаграммы)."""

    def alerts(cpu: Observable, mem: Observable) -> Observable:
        return sm.monitoring(cpu, mem, Subject()).alerts.pipe(
            map_(lambda s: "A" if s.startswith("ТРЕВОГА") else "n")
        )

    v = {"L": 50.0, "H": 95.0}
    #                   cpu          mem
    assert marble(alerts, "L-H--H-L", "H-H-H-L-", values=v) == "--A---n"
    # повторное «перегружено» не дублирует оповещение
    assert marble(alerts, "HHHH", "HHHH", values=v) == "A"


def test_moving_average() -> None:
    """Скользящее среднее за 5 событий."""
    req = Subject()
    out = []
    sm.monitoring(Subject(), Subject(), req).moving_avg.subscribe(out.append)
    for r in (10, 20, 30, 40, 50, 60):
        req.on_next(r)
    assert out == [30.0, 40.0]


# ------------------------------ Задание 6 ---------------------------------
M = chat.Message
CHAT = MappingProxyType(
    {
        "a": M("#g", "ann", "привет"),
        "b": M("#s", "bob", "купи спам"),
        "c": M("#s", "bob", "КАЗИНО тут"),
        "d": M("#g", "ann", "ok"),
        "s": M("#g", "ann", chat.STOP_COMMAND),
        "e": M("#g", "ann", ""),
    }
)


def test_censor_and_banned() -> None:
    """Цензура и поиск запрещённых слов по основам."""
    assert chat.censor("Это СПАМ и казино!") == "Это **** и ******!"
    assert chat.banned_words("не будь дураком") == ("дураком",)
    assert chat.banned_words("всё хорошо") == ()


def test_inc_is_pure() -> None:
    """Счётчик inc не меняет исходную версию."""
    c1 = (("x", 1),)
    c2 = chat.inc(c1, "y")
    assert c1 == (("x", 1),) and c2 == (("x", 1), ("y", 1))
    assert chat.leader((("a", 2), ("b", 3), ("c", 3))) == "b"


def test_feed_stops_on_command_and_skips_empty() -> None:
    """Лента: пустые пропускаются, /stop завершает."""

    def feed(g: Observable, s: Observable) -> Observable:
        return chat.chat_pipeline(g, s).feed.pipe(map_(lambda t: "m"))

    assert marble(feed, "-a-e-s-d|", "--b----c|", values=CHAT) == "-mm--|"


def test_duplicates_suppressed() -> None:
    """Подряд идущие дубликаты подавляются."""

    def users(g: Observable) -> Observable:
        return chat.chat_pipeline(g).feed.pipe(take(10), map_(lambda t: "x"))

    assert marble(users, "-a-a-d-a|", values=CHAT) == "-x---x-x|"


def test_violations_and_warning() -> None:
    """Подсчёт нарушений и одно предупреждение."""

    def warn(s: Observable) -> Observable:
        return chat.chat_pipeline(s).warnings.pipe(map_(lambda t: "W"))

    assert marble(warn, "-b-c-b|", values=CHAT) == "---W--|"

    def viol(s: Observable) -> Observable:
        return chat.chat_pipeline(s).violations.pipe(
            map_(lambda uv: str(uv[1]))
        )

    assert marble(viol, "-b-c-a|", values=CHAT) == "-1-2--|"


def test_channel_activity_and_leader() -> None:
    """Счётчики каналов и смена лидера активности."""
    g, s = Subject(), Subject()
    streams = chat.chat_pipeline(g, s)
    acts, leaders = [], []
    streams.channel_activity.subscribe(acts.append)
    streams.top_user.subscribe(leaders.append)
    for subj, key in ((g, "a"), (s, "b"), (s, "c"), (g, "d")):
        subj.on_next(CHAT[key])
    assert acts[0] == "пусто" and acts[-1] == "#g: 2, #s: 2"
    assert leaders == ["ann", "bob", "ann"]


def test_crosspost_and_summary() -> None:
    """Обнаружение кросспостинга и итог сеанса."""
    g, s = Subject(), Subject()
    streams = chat.chat_pipeline(g, s)
    cross, summary = [], []
    streams.crossposts.subscribe(cross.append)
    streams.summary.subscribe(summary.append)
    msg = M("#g", "eve", "реклама")
    g.on_next(msg)
    s.on_next(M("#s", "eve", "реклама"))
    g.on_completed()
    s.on_completed()
    assert len(cross) == 1 and "eve" in cross[0]
    assert summary == ["итог: 2 сообщений от 1 участников"]


def test_load_events(tmp_path: Path) -> None:
    """Разбор файла журнала событий."""
    p = tmp_path / "log.txt"
    p.write_text("// c\n#a | u | hi | there\n\n", encoding="utf-8")
    assert chat.load_events(p) == (M("#a", "u", "hi | there"),)


# ------------------------- Дополнительное задание -------------------------
def test_interval_take() -> None:
    """Interval на виртуальном времени."""
    s = VirtualScheduler()
    out = record(interval(10, s).pipe(take(3)), s, 1000)
    assert out == [
        (10, ("N", 0)),
        (20, ("N", 1)),
        (30, ("N", 2)),
        (30, ("C",)),
    ]


def test_debounce() -> None:
    """Debounce на виртуальном времени."""
    s = VirtualScheduler()
    src = timed_hot(
        s, (10, ("N", "a")), (20, ("N", "b")), (100, ("N", "c")), (120, ("C",))
    )
    assert record(src.pipe(debounce(50, s)), s, 500) == [
        (70, ("N", "b")),
        (120, ("N", "c")),
        (120, ("C",)),
    ]


def test_throttle_first() -> None:
    """throttle_first на виртуальном времени."""
    s = VirtualScheduler()
    src = timed_hot(
        s,
        (0, ("N", 1)),
        (10, ("N", 2)),
        (50, ("N", 3)),
        (60, ("N", 4)),
        (99, ("N", 5)),
    )
    assert [t for t, _ in record(src.pipe(throttle_first(50, s)), s, 200)] == [
        0,
        50,
    ]


def test_delay_keeps_order_and_error_is_immediate() -> None:
    """Delay сдвигает значения, ошибка — сразу."""
    s = VirtualScheduler()
    err = ValueError("x")
    src = timed_hot(s, (10, ("N", 1)), (20, ("N", 2)), (25, ("E", err)))
    assert record(src.pipe(delay(30, s)), s, 200) == [(25, ("E", err))]
    s2 = VirtualScheduler()
    src2 = timed_hot(s2, (10, ("N", 1)), (20, ("C",)))
    assert record(src2.pipe(delay(30, s2)), s2, 200) == [
        (40, ("N", 1)),
        (50, ("C",)),
    ]


def test_scheduler_cancel() -> None:
    """Отменённая задача планировщика не выполняется."""
    s = VirtualScheduler()
    hits = []
    d = s.schedule(10, lambda: hits.append(1))
    d.dispose()
    s.advance_to(100)
    assert hits == [] and s.now == 100


def test_values_helper() -> None:
    """take(0) на субъекте сразу завершается."""
    assert values(materialize(Subject().pipe(take(0)))) == []
