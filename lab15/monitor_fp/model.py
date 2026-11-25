"""Неизменяемая модель данных мониторинга."""

from __future__ import annotations

from typing import NamedTuple


class Metric(NamedTuple):
    """Замер сервера."""

    ts: int
    server: str
    cpu: float
    mem: float
    latency: float


class Silence(NamedTuple):
    """Событие «от сервера нет данных» (порождается правилом молчания)."""

    ts: int
    server: str


Event = Metric | Silence


class Alert(NamedTuple):
    """Оповещение. Порядок полей (ts, server, code) — порядок вывода."""

    ts: int
    server: str
    code: str
    level: str
    message: str


class Config(NamedTuple):
    """Пороги и параметры правил."""

    cpu_high: float = 85.0
    cpu_ok: float = 70.0
    mem_high: float = 90.0
    mem_cooldown: int = 60
    lat_high: float = 500.0
    silence: int = 30
    window: int = 3


DEFAULT = Config()
