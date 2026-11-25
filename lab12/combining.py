"""Задание 2. Комбинирование потоков в RxPY.

Каждый сценарий — чистая функция «потоки → поток»; демонстрация
запускает их на TestScheduler с виртуальным временем.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.testing.recorded import Recorded
from rx_helpers import (
    diagram,
    on_completed,
    on_next,
    recorded_events,
    run,
    values,
)

Snapshot = tuple[tuple[str, float], ...]


# ---------------------------- 1. корзина ------------------------------------
def upsert(snapshot: Snapshot, item: tuple[str, float]) -> Snapshot:
    """Неизменяемое обновление «словаря» товар → число."""
    key, value = item
    return tuple(sorted({**dict(snapshot), key: value}.items()))


def cart_total(prices: Observable, quantities: Observable) -> Observable:
    """Итоговая сумма корзины при изменении цен или количеств."""

    def total(pq: tuple[Snapshot, Snapshot]) -> float:
        price = dict(pq[0])
        return round(sum(price.get(k, 0.0) * q for k, q in pq[1]), 2)

    return rx.combine_latest(
        prices.pipe(ops.scan(upsert, ())),
        quantities.pipe(ops.scan(upsert, ())),
    ).pipe(ops.map(total), ops.distinct_until_changed())


# ---------------------------- 2. курс валют ---------------------------------
def purchases_in_kzt(
    purchases_usd: Observable, rates: Observable
) -> Observable:
    """Покупка в $ → в ₸ по последнему известному курсу.

    ``with_latest_from``: событие порождает только покупка; изменение
    курса само по себе ничего не выдаёт и не задерживает покупку.
    """
    return purchases_usd.pipe(
        ops.with_latest_from(rates),
        ops.map(lambda pr: (pr[0], round(pr[0] * pr[1], 2))),
    )


# --------------------------- 3. запрос — ответ ------------------------------
def match_responses(requests: Observable, responses: Observable) -> Observable:
    """Сопоставить i-й запрос i-му ответу (zip)."""
    return rx.zip(requests, responses)


# --------------------------- 4. агрегатор новостей --------------------------
@dataclass(frozen=True)
class News:
    """Новость из источника."""

    source: str
    title: str


def normalize(title: str) -> str:
    """Ключ дубликата: регистр и лишние пробелы не важны."""
    return " ".join(title.lower().split())


def news_feed(*sources: Observable) -> Observable:
    """Слить источники и убрать дубликаты по заголовку."""
    return rx.merge(*sources).pipe(ops.distinct(lambda n: normalize(n.title)))


# ---------------------------- 5. группировка --------------------------------
@dataclass(frozen=True)
class Order:
    """Заказ."""

    city: str
    amount: float


def running_totals_by_city(orders: Observable) -> Observable:
    """(город, накопительная сумма) — group_by + flat_map + scan."""
    return orders.pipe(
        ops.group_by(lambda o: o.city),
        ops.flat_map(
            lambda group: group.pipe(
                ops.scan(lambda acc, o: acc + o.amount, 0.0),
                ops.map(lambda total, key=group.key: (key, total)),
            )
        ),
    )


# ------------------------------- демонстрация -------------------------------
Fmt = Callable[[Any], str]


def item_letter(v: tuple[str, float]) -> str:
    """Первая буква товара."""
    return v[0][0]


def by_title(n: News) -> str:
    """Буква темы новости: К — курс, Н — закон, П — погода."""
    return {"курс": "К", "новый": "Н", "погода": "П"}[
        normalize(n.title).split()[0]
    ]


def city_code(city: str) -> str:
    """Код города для диаграммы."""
    return str(("Алматы", "Астана", "Шымкент").index(city) + 1)


def show(
    title: str,
    inputs: tuple[tuple[str, tuple[Recorded[Any], ...], Fmt], ...],
    output: list[tuple[float, str, Any]],
    fmt: Fmt,
) -> None:
    """Напечатать мраморную диаграмму сценария (1 символ = 10 единиц)."""
    print(title)
    for label, msgs, f in inputs:
        print(f"  {label:<10}", diagram(recorded_events(*msgs), fmt=f))
    print(f"  {'результат':<10}", diagram(output, fmt=fmt))
    print("  значения:", values(output))


def demo() -> None:
    """Запустить все сценарии на виртуальном времени с диаграммами."""
    prices = (
        on_next(210, ("хлеб", 250.0)),
        on_next(220, ("молоко", 600.0)),
        on_next(300, ("молоко", 650.0)),
        on_completed(500),
    )
    qty = (
        on_next(230, ("хлеб", 2)),
        on_next(240, ("молоко", 1)),
        on_next(280, ("хлеб", 3)),
        on_completed(500),
    )
    show(
        "1. Корзина (combine_latest); х — хлеб, м — молоко, s — сумма",
        (("цены", prices, item_letter), ("кол-во", qty, item_letter)),
        run(
            lambda s: cart_total(
                s.create_hot_observable(*prices), s.create_hot_observable(*qty)
            )
        ),
        lambda v: "s",
    )

    usd = (
        on_next(205, 1.0),
        on_next(220, 10.0),
        on_next(260, 5.0),
        on_next(300, 20.0),
        on_completed(400),
    )
    rate = (
        on_next(210, 505.0),
        on_next(250, 510.0),
        on_next(290, 498.5),
        on_completed(400),
    )
    show(
        "2. Покупки в ₸ (with_latest_from); $ — покупка, к — курс, ₸ — итог",
        (("покупки", usd, lambda v: "$"), ("курс", rate, lambda v: "к")),
        run(
            lambda s: purchases_in_kzt(
                s.create_hot_observable(*usd), s.create_hot_observable(*rate)
            )
        ),
        lambda v: "₸",
    )

    req = tuple(on_next(210 + 10 * i, f"q{i}") for i in range(6))
    resp = (on_next(260, "r0"), on_next(400, "r1"))
    show(
        "3. Запрос—ответ (zip); q2..q5 копятся в буфере без ответа",
        (("запросы", req, lambda v: v[1]), ("ответы", resp, lambda v: v[1])),
        run(
            lambda s: match_responses(
                s.create_hot_observable(*req), s.create_hot_observable(*resp)
            )
        ),
        lambda v: v[0][1],
    )

    src_a = (
        on_next(210, News("tengri", "Курс тенге вырос")),
        on_next(250, News("tengri", "Новый закон о ФП")),
    )
    src_b = (
        on_next(220, News("kapital", "курс  тенге ВЫРОС")),
        on_next(260, News("kapital", "Погода в Алматы")),
    )
    src_c = (on_next(230, News("zakon", "Новый закон о ФП")),)
    show(
        "4. Новости (merge + distinct); К — курс, Н — закон, П — погода",
        (
            ("tengri", src_a, by_title),
            ("kapital", src_b, by_title),
            ("zakon", src_c, by_title),
        ),
        run(
            lambda s: news_feed(
                s.create_hot_observable(*src_a),
                s.create_hot_observable(*src_b),
                s.create_hot_observable(*src_c),
            )
        ),
        by_title,
    )

    orders = (
        on_next(210, Order("Алматы", 100)),
        on_next(220, Order("Астана", 50)),
        on_next(230, Order("Алматы", 70)),
        on_next(240, Order("Шымкент", 20)),
        on_next(250, Order("Астана", 30)),
    )
    show(
        "5. Суммы по городам (group_by + flat_map + scan); "
        "1 — Алматы, 2 — Астана, 3 — Шымкент",
        (("заказы", orders, lambda o: city_code(o.city)),),
        run(
            lambda s: running_totals_by_city(s.create_hot_observable(*orders))
        ),
        lambda v: city_code(v[0]),
    )


if __name__ == "__main__":
    demo()
