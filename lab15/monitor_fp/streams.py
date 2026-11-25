"""Реактивный компонент мониторинга на RxPY.

* поток замеров разбивается по серверам — ``group_by``;
* молчание сервера — оператор времени: после каждого замера запускается
  таймер ``rx.timer(silence + 0.5)``, следующий замер его отменяет
  (``switch_map``); сработавший таймер порождает событие Silence;
* замеры и события молчания сливаются (``merge``) и сворачиваются
  чистым редьюсером ``core.step`` (``scan``);
* журнал воспроизводится в виртуальном времени ``HistoricalScheduler``,
  обработка заканчивается в момент последнего замера (``take_until``).

Тот же компонент работает и в реальном времени — достаточно передать
другой планировщик (например, AsyncIOScheduler) и «живой» источник.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from operator import attrgetter
from typing import Any

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import CompositeDisposable
from reactivex.scheduler import HistoricalScheduler

from monitor_fp.core import INITIAL, ServerState, ordered, step
from monitor_fp.model import DEFAULT, Alert, Config, Event, Metric, Silence
from monitor_fp.rules import Alerts

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def at(seconds: float) -> datetime:
    """Абсолютное виртуальное время."""
    return EPOCH + timedelta(seconds=seconds)


def replay(metrics: Sequence[Metric],
           scheduler: SchedulerBase) -> Observable[Metric]:
    """Источник: каждый замер испускается в момент своего ts."""

    def subscribe(observer: ObserverBase[Metric],
                  _: SchedulerBase | None = None) -> CompositeDisposable:
        def emit(m: Metric) -> Any:
            return scheduler.schedule_absolute(
                at(m.ts), lambda *_: observer.on_next(m))

        last = metrics[-1].ts if metrics else 0
        return CompositeDisposable(
            *map(emit, metrics),
            scheduler.schedule_absolute(
                at(last), lambda *_: observer.on_completed()))

    return rx.create(subscribe)


def silence_events(metrics: Observable[Metric], cfg: Config,
                   scheduler: SchedulerBase) -> Observable[Silence]:
    """Событие молчания, если за silence секунд не пришло нового замера."""
    return metrics.pipe(ops.switch_map(
        lambda m: rx.timer(cfg.silence + 0.5, scheduler=scheduler).pipe(
            ops.map(lambda _: Silence(m.ts + cfg.silence, m.server)))))


def server_alerts(metrics: Observable[Metric], cfg: Config,
                  scheduler: SchedulerBase) -> Observable[Alert]:
    """Оповещения одного сервера: merge(замеры, молчание) → scan(step)."""
    shared = metrics.pipe(ops.share())
    events: Observable[Event] = rx.merge(
        shared, silence_events(shared, cfg, scheduler))
    seed: tuple[ServerState, Alerts] = (INITIAL, ())
    return events.pipe(
        ops.scan(lambda acc, ev: step(acc[0], ev, cfg), seed),
        ops.flat_map(lambda acc: rx.from_iterable(acc[1])))


def monitor(metrics: Observable[Metric], until: datetime, cfg: Config,
            scheduler: SchedulerBase) -> Observable[Alert]:
    """Компонент «поток замеров → поток оповещений»."""
    return metrics.pipe(
        ops.group_by(attrgetter("server")),
        ops.flat_map(lambda group: server_alerts(group, cfg, scheduler)),
        ops.take_until(rx.timer(until, scheduler=scheduler)))


def detect_reactive(metrics: Sequence[Metric],
                    cfg: Config = DEFAULT) -> Alerts:
    """Пакетный запуск компонента на виртуальном времени."""
    if not metrics:
        return ()
    scheduler = HistoricalScheduler()
    collected: list[Alert] = []
    monitor(replay(metrics, scheduler), at(metrics[-1].ts + 0.25), cfg,
            scheduler).subscribe(collected.append)
    scheduler.start()
    return ordered(collected)
