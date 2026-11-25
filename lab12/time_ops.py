"""Задание 3. Операторы времени и их тестирование на TestScheduler.

* debounce        — поле поиска: запрос после паузы ввода;
* throttle_first  — защита кнопки «Оплатить» от двойного нажатия;
* buffer_with_time — пакетная отправка журналов каждые 100 единиц;
* sample          — снятие показаний быстрого датчика раз в 50 единиц;
* timeout         — переключение на резервный источник при молчании.

Все функции принимают ``scheduler`` — в тестах это TestScheduler,
в реальном приложении — AsyncIOScheduler или TimeoutScheduler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from reactivex import Observable
from reactivex import operators as ops
from reactivex.abc import SchedulerBase
from reactivex.testing import TestScheduler
from rx_helpers import diagram, on_completed, on_next, recorded_events, run

CATALOG = ("лабораторная", "лаборант", "лабиринт", "лава", "лампа", "ламинат")


def suggest(prefix: str) -> tuple[str, ...]:
    """Чистая функция «сервера» подсказок."""
    return tuple(w for w in CATALOG if w.startswith(prefix.lower()))


def search_box(
    inputs: Observable, scheduler: SchedulerBase, pause: float = 50
) -> Observable:
    """Подсказки после паузы ввода ``pause`` и минимум 2 символа."""
    return inputs.pipe(
        ops.debounce(pause, scheduler=scheduler),
        ops.map(str.strip),
        ops.filter(lambda t: len(t) >= 2),
        ops.distinct_until_changed(),
        ops.map(suggest),
    )


def pay_button(
    clicks: Observable, scheduler: SchedulerBase, window: float = 100
) -> Observable:
    """Каждое нажатие → платёж, но не чаще одного за ``window``."""
    return clicks.pipe(
        ops.throttle_first(window, scheduler=scheduler),
        ops.map(lambda order: f"оплата {order}"),
    )


def log_batches(
    logs: Observable, scheduler: SchedulerBase, period: float = 100
) -> Observable:
    """Пакеты журналов каждые ``period``; пустые пакеты не отправляются."""
    return logs.pipe(
        ops.buffer_with_time(period, scheduler=scheduler),
        ops.filter(bool),
        ops.map(tuple),
    )


def sensor_sampling(
    readings: Observable, scheduler: SchedulerBase, period: float = 50
) -> Observable:
    """Последнее показание датчика раз в ``period``."""
    return readings.pipe(ops.sample(period, scheduler=scheduler))


def with_fallback(
    primary: Observable,
    backup: Observable,
    scheduler: SchedulerBase,
    silence: float = 60,
) -> Observable:
    """Если основной источник молчит дольше ``silence`` — резервный."""
    return primary.pipe(ops.timeout(silence, backup, scheduler=scheduler))


# ------------------------------ демонстрация --------------------------------
Scenario = tuple[
    str,
    Callable[[TestScheduler], Observable],
    tuple[Any, ...],
    Callable[[Any], str],
]


def scenarios() -> tuple[Scenario, ...]:
    """Сценарии: (название, построитель, события входа, формат значения)."""
    typing = (
        on_next(210, "л"),
        on_next(220, "ла"),
        on_next(230, "лаб"),
        on_next(300, "лаб "),
        on_next(400, "лам"),
        on_next(420, "лава"),
        on_completed(600),
    )
    clicks = (
        on_next(210, "№1"),
        on_next(215, "№1"),
        on_next(230, "№1"),
        on_next(350, "№2"),
        on_next(390, "№2"),
        on_completed(500),
    )
    logs = (
        on_next(210, "a"),
        on_next(250, "b"),
        on_next(280, "c"),
        on_next(420, "d"),
        on_completed(520),
    )
    sensor = tuple(on_next(205 + 15 * i, 20 + i) for i in range(18)) + (
        on_completed(480),
    )
    primary = (on_next(220, "P"), on_next(250, "P"), on_next(400, "P"))
    backup = (on_next(30, "B"), on_completed(60))

    def build(
        fn: Callable[..., Observable], events: tuple[Any, ...], **kw: Any
    ) -> Callable[[TestScheduler], Observable]:
        return lambda s: fn(s.create_hot_observable(*events), s, **kw)

    return (
        (
            "debounce(50)",
            build(search_box, typing),
            typing,
            lambda v: str(len(v)),
        ),
        (
            "throttle_first(100)",
            build(pay_button, clicks),
            clicks,
            lambda v: v[-1],
        ),
        (
            "buffer_with_time(100)",
            build(log_batches, logs),
            logs,
            lambda v: str(len(v)),
        ),
        (
            "sample(50)",
            build(sensor_sampling, sensor),
            sensor,
            lambda v: str(v % 10),
        ),
        (
            "timeout(60) → резерв",
            lambda s: with_fallback(
                s.create_hot_observable(*primary),
                s.create_cold_observable(*backup),
                s,
            ),
            primary,
            lambda v: v,
        ),
    )


def demo() -> None:
    """Печать результатов и мраморных диаграмм (1 символ = 10 единиц)."""
    for title, build, inputs, fmt in scenarios():
        out = run(build)
        print(f"== {title}")
        print("  вход: ", diagram(recorded_events(*inputs), fmt=lambda v: "x"))
        print("  выход:", diagram(out, fmt=fmt))
        print("  ", [(t, k, v) for t, k, v in out])


if __name__ == "__main__":
    demo()
    print("\nПодсказки для «лаб»:", suggest("лаб"))
