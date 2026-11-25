"""Задание 4. Обработка ошибок в RxPY.

1. Ненадёжный источник: в ~30 % подписок завершается ошибкой
   (детерминированный ГПСЧ). ``retry(3)`` повторяет подписку, ``catch``
   переключает на резервный поток, если все попытки неудачны.
2. «Битая» запись внутри ``ops.map``: исключение превращается в значение
   ``Err`` (тип Result), поток не прерывается.

Ошибка-уведомление (``on_error``) *завершает* поток — после неё значений
не будет. Ошибка-значение (``Err``) — обычный элемент потока: её можно
отфильтровать, посчитать, показать пользователю, а обработка остальных
записей продолжается.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.testing import TestScheduler
from reactivex.testing.recorded import Recorded
from rx_helpers import (
    diagram,
    on_completed,
    on_error,
    on_next,
    recorded_events,
    run,
)

FAIL_RATE = 0.3


class SourceError(Exception):
    """Сбой источника данных."""


def flaky_source(
    rng: random.Random, attempts: list[int], data: tuple[int, ...] = (1, 2, 3)
) -> Observable:
    """Холодный источник: каждая подписка с вероятностью 30 % падает.

    ``rng`` задаёт детерминированную последовательность сбоев;
    ``attempts`` — журнал попыток (только для демонстрации/тестов).
    """

    def factory(_: Any) -> Observable:
        attempts.append(len(attempts) + 1)
        if rng.random() < FAIL_RATE:
            return rx.concat(
                rx.of(*data[:1]),
                rx.throw(SourceError(f"сбой #{len(attempts)}")),
            )
        return rx.of(*data)

    return rx.defer(factory)


BACKUP: Observable = rx.of("резервные данные")


def reliable(
    source: Observable, retries: int = 3, backup: Observable = BACKUP
) -> Observable:
    """retry, затем catch с резервным потоком."""
    return source.pipe(ops.retry(retries), ops.catch(lambda err, _src: backup))


# ------------------------- ошибка как значение ------------------------------
@dataclass(frozen=True)
class Ok:
    """Успешный результат."""

    value: Any


@dataclass(frozen=True)
class Err:
    """Ошибка как значение: исходные данные и сообщение."""

    raw: Any
    error: str


Result = Ok | Err


def safe(f: Callable[[Any], Any]) -> Callable[[Any], Result]:
    """Превратить функцию, бросающую исключения, в функцию → Result."""

    def wrapper(x: Any) -> Result:
        try:
            return Ok(f(x))
        except Exception as e:  # noqa: BLE001 - любая ошибка → значение
            return Err(x, f"{type(e).__name__}: {e}")

    return wrapper


def parse_record(line: str) -> dict[str, Any]:
    """Разобрать JSON-запись о платеже и проверить сумму."""
    rec = json.loads(line)
    if rec["amount"] <= 0:
        raise ValueError("сумма должна быть положительной")
    return rec


def process_failing(lines: Observable) -> Observable:
    """Наивно: первая битая запись обрывает поток (on_error)."""
    return lines.pipe(ops.map(parse_record))


def process_resilient(lines: Observable) -> Observable:
    """Устойчиво: ошибки становятся значениями Err, поток продолжается."""
    return lines.pipe(ops.map(safe(parse_record)))


RECORDS = (
    '{"id": 1, "amount": 500}',
    '{"id": 2, "amount": -3}',
    "не json",
    '{"id": 4}',
    '{"id": 5, "amount": 120}',
)


def collect(observable: Observable) -> list[str]:
    """Синхронно собрать уведомления в текстовом виде."""
    out: list[str] = []
    observable.subscribe(
        lambda v: out.append(f"N {v}"),
        lambda e: out.append(f"E {e!r}"),
        lambda: out.append("C"),
    )
    return out


# --------------------------- мраморные диаграммы ---------------------------
FAILED_ATTEMPT = (on_next(10, 1), on_error(20, SourceError("сбой")))
GOOD_ATTEMPT = (
    on_next(10, 1),
    on_next(20, 2),
    on_next(30, 3),
    on_completed(40),
)
BACKUP_MSGS = (on_next(10, "R"), on_completed(20))


def retry_scenario(
    scheduler: TestScheduler, failures: tuple[bool, ...]
) -> Observable:
    """retry(3) + catch на холодном источнике с заданной судьбой попыток."""
    attempt = iter(failures)

    def factory(_: Any) -> Observable:
        msgs = FAILED_ATTEMPT if next(attempt) else GOOD_ATTEMPT
        return scheduler.create_cold_observable(*msgs)

    return reliable(
        rx.defer(factory), 3, scheduler.create_cold_observable(*BACKUP_MSGS)
    )


def result_letter(r: Any) -> str:
    """Ok → o, Err → e, словарь (без Result) → o."""
    return "e" if isinstance(r, Err) else "o"


def marble_demo() -> str:
    """Диаграммы задания 4 (1 символ = 10 единиц виртуального времени)."""

    def cold(msgs: tuple[Recorded[Any], ...]) -> str:
        return diagram(recorded_events(*msgs), 0)

    lines = [
        "retry(3) + catch:",
        f"  неудачная попытка   {cold(FAILED_ATTEMPT)}",
        f"  удачная попытка     {cold(GOOD_ATTEMPT)}",
        f"  резерв              {cold(BACKUP_MSGS)}",
    ]
    for title, failures in (
        ("2 сбоя, 3-я успешна", (True, True, False)),
        ("3 сбоя → резерв", (True, True, True)),
    ):
        out = run(lambda s, f=failures: retry_scenario(s, f))
        lines.append(f"  {title:<19} {diagram(out)}")
    records = tuple(
        on_next(210 + 10 * i, line) for i, line in enumerate(RECORDS)
    ) + (on_completed(260),)
    lines += [
        "ошибка в map (o — корректная запись, e — Err):",
        "  записи              "
        + diagram(recorded_events(*records), fmt=lambda v: "x"),
    ]
    for title, process in (
        ("on_error", process_failing),
        ("Result", process_resilient),
    ):
        out = run(lambda s, p=process: p(s.create_hot_observable(*records)))
        lines.append(f"  {title:<19} {diagram(out, fmt=result_letter)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== retry(3) + catch ===")
    for seed in (0, 1, 4, 149):  # 149 — все три попытки неудачны → catch
        attempts: list[int] = []
        result = collect(reliable(flaky_source(random.Random(seed), attempts)))
        print(f"seed={seed}: попыток {len(attempts)} → {result}")

    print("\n=== ошибка завершает поток ===")
    print(collect(process_failing(rx.from_iterable(RECORDS))))
    print("\n=== ошибка как значение (Result) ===")
    results = collect(process_resilient(rx.from_iterable(RECORDS)))
    print("\n".join(results))
    oks = process_resilient(rx.from_iterable(RECORDS)).pipe(
        ops.filter(lambda r: isinstance(r, Ok)),
        ops.map(lambda r: r.value["amount"]),
        ops.sum(),
    )
    print("сумма корректных платежей:", oks.run())
    print("\n=== мраморные диаграммы (TestScheduler) ===")
    print(marble_demo())
