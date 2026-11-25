"""Тесты ЛР 12 на TestScheduler (виртуальное время)."""

import asyncio
import random
from typing import Any

import async_loader as al
import combining as cb
import errors as er
import moderation as md
import reactivex as rx
import rx_monitor as rm
import time_ops as to
import tk_draw as td
from reactivex import Observable
from reactivex import operators as ops
from reactivex.testing import TestScheduler
from reactivex.testing.recorded import Recorded
from rx_helpers import (
    diagram,
    on_completed,
    on_error,
    on_next,
    run,
    times,
    values,
)

Rec = tuple[float, str, Any]


# ------------------------------ Задание 1 ---------------------------------
def test_monitor_alerts() -> None:
    """Оповещения мониторинга на RxPY."""

    def build(s: TestScheduler) -> Observable:
        cpu = s.create_hot_observable(
            on_next(210, 50.0),
            on_next(220, 95.0),
            on_next(250, 40.0),
            on_completed(300),
        )
        mem = s.create_hot_observable(on_next(205, 85.0), on_completed(300))
        return rm.monitoring(cpu, mem, rx.never()).alerts

    ev = run(build)
    assert times(ev) == [220, 250, 300]
    assert values(ev)[0].startswith("ТРЕВОГА")


def test_monitor_moving_average_matches_lab11() -> None:
    """Скользящее среднее совпадает с ЛР 11."""

    def build(s: TestScheduler) -> Observable:
        req = s.create_hot_observable(
            *(
                on_next(210 + i, r)
                for i, r in enumerate((10, 20, 30, 40, 50, 60))
            )
        )
        return rm.monitoring(rx.never(), rx.never(), req).moving_avg

    assert values(run(build)) == [30.0, 40.0]


# ------------------------------ Задание 2 ---------------------------------
def test_cart_total() -> None:
    """Сумма корзины через combine_latest."""

    def build(s: TestScheduler) -> Observable:
        p = s.create_hot_observable(
            on_next(210, ("a", 10.0)), on_next(240, ("a", 20.0))
        )
        q = s.create_hot_observable(
            on_next(220, ("a", 2)), on_next(230, ("a", 3))
        )
        return cb.cart_total(p, q)

    assert values(run(build)) == [20.0, 30.0, 60.0]


def test_with_latest_from_does_not_wait_for_rate() -> None:
    """with_latest_from: событие порождает только покупка."""

    def build(s: TestScheduler) -> Observable:
        usd = s.create_hot_observable(on_next(205, 1.0), on_next(230, 2.0))
        rate = s.create_hot_observable(
            on_next(210, 500.0), on_next(220, 510.0), on_next(240, 1.0)
        )
        return cb.purchases_in_kzt(usd, rate)

    ev = run(build)
    assert ev == [(230, "N", (2.0, 1020.0))]


def test_zip_buffers_unmatched() -> None:
    """Zip копит значения без пары."""

    def build(s: TestScheduler) -> Observable:
        a = s.create_hot_observable(
            on_next(210, 1), on_next(220, 2), on_next(230, 3)
        )
        b = s.create_hot_observable(on_next(300, "x"))
        return cb.match_responses(a, b)

    assert run(build) == [(300, "N", (1, "x"))]


def test_news_distinct() -> None:
    """Merge + distinct убирает дубликаты новостей."""

    def build(s: TestScheduler) -> Observable:
        a = s.create_hot_observable(on_next(210, cb.News("a", "Hello  World")))
        b = s.create_hot_observable(
            on_next(220, cb.News("b", "hello world")),
            on_next(230, cb.News("b", "Other")),
        )
        return cb.news_feed(a, b)

    assert [n.source for n in values(run(build))] == ["a", "b"]


def test_group_by_city() -> None:
    """Накопительные суммы по городам."""

    def build(s: TestScheduler) -> Observable:
        return cb.running_totals_by_city(
            s.create_hot_observable(
                on_next(210, cb.Order("A", 1)),
                on_next(220, cb.Order("B", 5)),
                on_next(230, cb.Order("A", 2)),
            )
        )

    assert values(run(build)) == [("A", 1.0), ("B", 5.0), ("A", 3.0)]


# ------------------------------ Задание 3 ---------------------------------
def test_debounce_search() -> None:
    """Debounce в поле поиска."""

    def build(s: TestScheduler) -> Observable:
        return to.search_box(
            s.create_hot_observable(
                on_next(210, "л"),
                on_next(220, "ла"),
                on_next(230, "лам"),
                on_next(300, "лам "),
                on_next(330, "лаб"),
                on_completed(500),
            ),
            s,
        )

    ev = run(build)
    assert ev == [
        (280, "N", ("лампа", "ламинат")),
        (380, "N", ("лабораторная", "лаборант", "лабиринт")),
        (500, "C", None),
    ]


def test_throttle_pay_button() -> None:
    """throttle_first для кнопки оплаты."""

    def build(s: TestScheduler) -> Observable:
        return to.pay_button(
            s.create_hot_observable(
                on_next(210, 1),
                on_next(220, 1),
                on_next(305, 2),
                on_next(320, 2),
            ),
            s,
        )

    assert times(run(build)) == [210, 320]


def test_buffer_with_time_logs() -> None:
    """buffer_with_time для пакетов журналов."""

    def build(s: TestScheduler) -> Observable:
        return to.log_batches(
            s.create_hot_observable(
                on_next(210, "a"),
                on_next(290, "b"),
                on_next(450, "c"),
                on_completed(460),
            ),
            s,
        )

    assert run(build) == [
        (300, "N", ("a", "b")),
        (460, "N", ("c",)),
        (460, "C", None),
    ]


def test_sample_sensor() -> None:
    """Sample для быстрого датчика."""

    def build(s: TestScheduler) -> Observable:
        return to.sensor_sampling(
            s.create_hot_observable(
                *(on_next(201 + 10 * i, i) for i in range(10))
            ),
            s,
        )

    assert run(build) == [(250, "N", 4), (300, "N", 9)]


def test_timeout_switches_to_backup() -> None:
    """Timeout переключает на резервный источник."""

    def build(s: TestScheduler) -> Observable:
        return to.with_fallback(
            s.create_hot_observable(on_next(220, "P"), on_next(400, "P")),
            s.create_cold_observable(on_next(10, "B"), on_completed(20)),
            s,
        )

    assert run(build) == [(220, "N", "P"), (290, "N", "B"), (300, "C", None)]


def test_diagram_helper() -> None:
    """Отрисовка мраморной диаграммы."""
    ev = [(210, "N", "a"), (230, "N", "b"), (230, "C", None)]
    assert diagram(ev) == "-a-(b|)"


# ------------------------------ Задание 4 ---------------------------------
def test_retry_succeeds_and_catch_fallback() -> None:
    """retry(3) и резервный поток catch."""
    attempts = []
    ok = er.collect(er.reliable(er.flaky_source(random.Random(4), attempts)))
    assert ok[-4:] == ["N 1", "N 2", "N 3", "C"] and len(attempts) == 3
    attempts = []
    fb = er.collect(er.reliable(er.flaky_source(random.Random(149), attempts)))
    assert fb[-2:] == ["N резервные данные", "C"] and len(attempts) == 3


def test_retry_on_test_scheduler() -> None:
    """Retry и catch на виртуальном времени."""

    def build(s: TestScheduler) -> Observable:
        cold = s.create_cold_observable(
            on_next(10, 1), on_error(20, ValueError("x"))
        )
        return cold.pipe(ops.retry(2), ops.catch(rx.of("backup")))

    assert values(run(build)) == [1, 1, "backup"]


def test_error_as_value_does_not_stop_stream() -> None:
    """Ошибка как значение не обрывает поток."""
    failing = er.collect(er.process_failing(rx.from_iterable(er.RECORDS)))
    assert failing[-1].startswith("E")
    results = []
    er.process_resilient(rx.from_iterable(er.RECORDS)).subscribe(
        results.append
    )
    assert len(results) == 5
    assert [type(r).__name__ for r in results] == [
        "Ok",
        "Err",
        "Err",
        "Err",
        "Ok",
    ]


# ------------------------------ Задание 5 ---------------------------------
def test_aggregate_pure_part() -> None:
    """Чистая часть загрузчика: средние."""

    def rnd(t: int, vals: tuple[float, ...]) -> tuple[al.Reading, ...]:
        return tuple(("s", t, v) for v in vals)

    def build(s: TestScheduler) -> Observable:
        return al.aggregate(
            s.create_hot_observable(
                on_next(210, rnd(0, (1, 2, 3))),
                on_next(220, rnd(1, (4, 4, 4))),
                on_next(230, rnd(2, (6, 6, 6))),
                on_next(240, rnd(3, (0, 0, 0))),
            )
        )

    assert values(run(build)) == [
        (0, 2.0, 2.0),
        (1, 4.0, 3.0),
        (2, 6.0, 4.0),
        (3, 0.0, 3.33),
    ]


def test_async_loader_terminates_and_disposes() -> None:
    """Загрузчик завершается и освобождает подписки."""
    out = asyncio.run(al.run_loader(duration=0.5, period=0.2, echo=False))
    assert any(str(x).startswith("сводка: опросов 2") for x in out)
    assert out[-1].startswith("все подписки освобождены")


# ------------------------- Задание 6: модерация ---------------------------
CFG = md.Config(rate_limit=2, rate_window=30, strikes_to_ban=2, ban_time=100)


def moderate(
    msgs: list[Recorded[Any]],
    cmds: tuple[Recorded[Any], ...] = (),
    cfg: md.Config = CFG,
) -> list[Rec]:
    """Прогнать модерацию на TestScheduler."""

    def build(s: TestScheduler) -> Observable:
        return md.pipeline(
            s.create_hot_observable(*msgs),
            s.create_hot_observable(*cmds),
            s,
            cfg,
        )

    return run(build)


def kinds(events: list[Rec]) -> list[tuple[float, str, str]]:
    """(время, вид события, пользователь) для значений потока."""
    return [(t, e.kind, e.user) for t, k, e in events if k == "N"]


def test_post_and_censor() -> None:
    """Публикация и цензура."""
    ev = moderate(
        [
            on_next(210, md.Message("a", "привет")),
            on_next(220, md.Message("b", "Это СПАМ")),
            on_next(230, md.Message("c", "   ")),
        ]
    )
    assert kinds(ev) == [(210, "post", "a"), (220, "censored", "b")]
    assert values(ev)[1].detail == "Это ****"


def test_rate_limit_sliding_window() -> None:
    """Ограничение частоты по скользящему окну."""
    m = md.Message("u", "hi")
    lenient = md.Config(rate_limit=2, rate_window=30, strikes_to_ban=10)
    ev = moderate(
        [on_next(t, m) for t in (210, 215, 220, 241, 244, 246)], cfg=lenient
    )
    # окно 30: в 241 «выпало» 210, в 246 — 215
    assert [k for _, k, _ in kinds(ev)] == [
        "post",
        "post",
        "rate_limited",
        "post",
        "rate_limited",
        "post",
    ]


def test_strikes_ban_block_and_expiry() -> None:
    """Страйки → бан → блокировка → истечение бана."""
    bad = md.Message("e", "казино")
    ev = moderate(
        [
            on_next(210, bad),
            on_next(220, bad),
            on_next(250, md.Message("e", "ок")),
            on_next(330, md.Message("e", "я вернулся")),
        ]
    )
    assert kinds(ev) == [
        (210, "censored", "e"),
        (220, "censored", "e"),
        (220, "ban", "e"),
        (250, "blocked", "e"),
        (330, "unban", "e"),
        (330, "post", "e"),
    ]


def test_moderator_commands() -> None:
    """Команды модератора ban/unban."""
    ev = moderate(
        [
            on_next(220, md.Message("x", "a")),
            on_next(260, md.Message("x", "b")),
        ],
        [
            on_next(210, md.Command("ban", "x")),
            on_next(250, md.Command("unban", "x")),
            on_next(255, md.Command("unban", "nobody")),
        ],
    )
    assert kinds(ev) == [
        (210, "ban", "x"),
        (220, "blocked", "x"),
        (250, "unban", "x"),
        (260, "post", "x"),
    ]


def test_banned_users_and_violations_streams() -> None:
    """Потоки забаненных и нарушений."""
    bad = md.Message("e", "лох")

    def build(s: TestScheduler) -> Observable:
        events = md.pipeline(
            s.create_hot_observable(
                on_next(210, bad), on_next(220, bad), on_next(230, bad)
            ),
            s.create_hot_observable(on_next(400, md.Command("unban", "e"))),
            s,
            CFG,
        ).pipe(ops.share())
        return rx.merge(
            md.banned_users(events).pipe(ops.map(sorted)),
            md.violations_by_user(events),
        )

    assert values(run(build)) == [[], ("e", 1), ("e", 2), ["e"], ("e", 3), []]


def test_activity_report() -> None:
    """Отчёт активности по окнам времени."""

    def build(s: TestScheduler) -> Observable:
        events = md.pipeline(
            s.create_hot_observable(
                on_next(210, md.Message("a", "1")),
                on_next(220, md.Message("a", "спам")),
                on_next(350, md.Message("b", "2")),
            ),
            rx.never(),
            s,
            CFG,
        )
        return md.activity_report(events, 100, s)

    assert values(run(build, disposed=450)) == [
        "censored: 1, post: 1",
        "post: 1",
    ]


def test_state_is_immutable() -> None:
    """Шаг автомата не меняет исходное состояние."""
    st0 = md.ModState()
    stamped = rx.of(md.Message("a", "x")).pipe(ops.timestamp()).run()
    st1 = md.step(CFG)(st0, stamped)
    assert st0.recent == {} and "a" in st1.recent


# ------------------------- Дополнительное задание -------------------------
def test_drag_strokes() -> None:
    """Отрезки рисуются только при нажатой кнопке."""

    def build(s: TestScheduler) -> Observable:
        down = s.create_hot_observable(
            on_next(220, (0, 0)), on_next(300, (5, 5))
        )
        move = s.create_hot_observable(
            on_next(210, (9, 9)),
            on_next(230, (1, 0)),
            on_next(240, (2, 0)),
            on_next(260, (3, 0)),
            on_next(310, (6, 6)),
        )
        up = s.create_hot_observable(
            on_next(250, (2, 0)), on_next(320, (6, 6))
        )
        return td.strokes(down, move, up)

    assert values(run(build)) == [
        ((0, 0), (1, 0)),
        ((1, 0), (2, 0)),
        ((5, 5), (6, 6)),
    ]


# ---------------- диаграммы и сравнение (добавленные сценарии) -------------
def test_rx_mini_and_rxpy_agree_on_errors_and_completion() -> None:
    """Обе библиотеки одинаково завершают поток и передают ошибки."""
    rows = rm.compare_with_rx_mini()
    for _, mini, rxpy in rows[:3]:
        assert mini == rxpy
    assert rows[3][1] == "—" and rows[3][2].startswith("исключение")


def test_loader_in_virtual_time() -> None:
    """Загрузчик в виртуальном времени: zip ждёт самый медленный источник."""

    def build(s: TestScheduler) -> Observable:
        ticks = rx.interval(20, scheduler=s).pipe(
            ops.take_until(rx.timer(70, scheduler=s)), ops.share()
        )
        return al.rounds_stream(ticks, al.virtual_request(s, 100)).pipe(
            ops.map(lambda r: r[0][1])
        )

    # тики в 220, 240, 260; самый медленный источник отвечает через 8
    assert run(build) == [
        (228, "N", 0),
        (248, "N", 1),
        (268, "N", 2),
        (270, "C", None),
    ]


def test_retry_scenario_marbles() -> None:
    """retry(3) + catch на холодных источниках TestScheduler."""
    ok = run(lambda s: er.retry_scenario(s, (True, True, False)))
    assert diagram(ok) == "-1-1-123|"
    backup = run(lambda s: er.retry_scenario(s, (True, True, True)))
    assert diagram(backup) == "-1-1-1-R|"
