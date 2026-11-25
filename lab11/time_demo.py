"""Дополнительное задание: операторы времени на виртуальном планировщике."""

from __future__ import annotations

from typing import Any

from rx_mini import take
from rx_mini.scheduler import (
    VirtualScheduler,
    debounce,
    delay,
    interval,
    record,
    throttle_first,
    timed_hot,
)


def show(title: str, events: list[tuple[float, tuple[Any, ...]]]) -> None:
    """Напечатать записанные уведомления."""
    body = ", ".join(
        f"{t:g}:{n[1] if n[0] == 'N' else n[0]}" for t, n in events
    )
    print(f"{title:<22} {body}")


def typing_events() -> tuple[tuple[float, tuple[Any, ...]], ...]:
    """Ввод в поле поиска: две «очереди» нажатий и завершение."""
    return (
        (10, ("N", "f")),
        (20, ("N", "fu")),
        (30, ("N", "fun")),
        (100, ("N", "func")),
        (105, ("N", "funct")),
        (200, ("C",)),
    )


if __name__ == "__main__":
    s = VirtualScheduler()
    show("interval(10), take 4", record(interval(10, s).pipe(take(4)), s, 100))

    s = VirtualScheduler()
    show(
        "delay(15)",
        record(timed_hot(s, *typing_events()).pipe(delay(15, s)), s, 300),
    )

    s = VirtualScheduler()
    show(
        "debounce(50)",
        record(timed_hot(s, *typing_events()).pipe(debounce(50, s)), s, 300),
    )

    s = VirtualScheduler()
    clicks = (
        (0, ("N", 1)),
        (5, ("N", 2)),
        (30, ("N", 3)),
        (55, ("N", 4)),
        (61, ("N", 5)),
        (70, ("C",)),
    )
    show(
        "throttle_first(30)",
        record(timed_hot(s, *clicks).pipe(throttle_first(30, s)), s, 100),
    )
