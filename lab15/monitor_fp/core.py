"""Чистое ядро: состояние сервера и редьюсер событий.

``step(state, event)`` — единственная функция перехода; используется и
пакетным конвейером ``detect``, и реактивным компонентом (streams.py).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import accumulate, chain, groupby
from operator import attrgetter
from typing import NamedTuple

from monitor_fp.model import DEFAULT, Alert, Config, Event, Metric, Silence
from monitor_fp.rules import (
    Alerts,
    cpu_rule,
    down_alert,
    mem_rule,
    slow_rule,
    up_alert,
)


class ServerState(NamedTuple):
    """Состояние правил одного сервера."""

    window: tuple[float, ...] = ()
    alarm: bool = False
    mem_last: int | None = None
    slow: int = 0
    down: bool = False


INITIAL = ServerState()


def step(state: ServerState, event: Event,
         cfg: Config = DEFAULT) -> tuple[ServerState, Alerts]:
    """Переход: (состояние, событие) → (новое состояние, оповещения)."""
    if isinstance(event, Silence):
        if state.down:
            return state, ()
        return (state._replace(down=True),
                (down_alert(event.server, event.ts, cfg),))
    up = (up_alert(event),) if state.down else ()
    window, alarm, cpu = cpu_rule(state.window, state.alarm, event, cfg)
    mem_last, mem = mem_rule(state.mem_last, event, cfg)
    slow, lat = slow_rule(state.slow, event, cfg)
    return (ServerState(window, alarm, mem_last, slow, False),
            up + cpu + mem + lat)


def run_server(events: Iterable[Event], cfg: Config = DEFAULT) -> Alerts:
    """Свёртка событий одного сервера в оповещения (accumulate)."""
    seed: tuple[ServerState, Alerts] = (INITIAL, ())
    states = accumulate(events, lambda acc, ev: step(acc[0], ev, cfg),
                        initial=seed)
    return tuple(chain.from_iterable(new for _, new in states))


def silences(own: Sequence[Metric], end: int,
             cfg: Config = DEFAULT) -> tuple[Silence, ...]:
    """События молчания: промежутки > silence и молчание до конца журнала."""
    times = [m.ts for m in own]
    gaps = zip(times, [*times[1:], end], strict=True)
    return tuple(Silence(a + cfg.silence, own[0].server)
                 for a, b in gaps if b - a > cfg.silence)


def timeline(own: Sequence[Metric], end: int,
             cfg: Config = DEFAULT) -> list[Event]:
    """Замеры и события молчания сервера в порядке времени."""
    return sorted((*own, *silences(own, end, cfg)), key=lambda e: e.ts)


def ordered(alerts: Iterable[Alert]) -> tuple[Alert, ...]:
    """Порядок вывода: время, сервер, код (устойчивая сортировка)."""
    return tuple(sorted(alerts, key=lambda a: (a.ts, a.server, a.code)))


def detect(metrics: Sequence[Metric], cfg: Config = DEFAULT) -> Alerts:
    """Пакетный конвейер: все оповещения журнала."""
    if not metrics:
        return ()
    end = metrics[-1].ts
    by_server = groupby(sorted(metrics, key=attrgetter("server")),
                        key=attrgetter("server"))
    return ordered(chain.from_iterable(
        run_server(timeline(tuple(own), end, cfg), cfg)
        for _, own in by_server))
