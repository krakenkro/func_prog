"""Задание 6 (вариант 4). Модерация чата на RxPY.

Ограничение частоты сообщений пользователя, фильтр запрещённых слов, бан.

Правила:

* не более ``rate_limit`` сообщений пользователя за ``rate_window`` единиц
  времени — лишние отклоняются (``rate_limited``) и дают «страйк»;
* сообщение с запрещёнными словами публикуется с цензурой (``censored``)
  и даёт страйк;
* ``strikes_to_ban`` страйков → бан на ``ban_time``; сообщения забаненного
  отклоняются (``blocked``); по истечении срока бан снимается (``unban``);
* модератор может забанить навсегда и разбанить командами.

Компонент ``pipeline(messages, commands, scheduler) -> Observable[Event]``
не имеет побочных эффектов: время берётся из планировщика оператором
``timestamp``, состояние — неизменяемое (pyrsistent) и сворачивается
``scan``-ом. Поэтому вся логика проверяется на TestScheduler.

Операторы: merge, filter, timestamp, scan, flat_map, map, group_by,
distinct_until_changed, buffer_with_time, start_with, share.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import reactivex as rx
from pyrsistent import PMap, pmap
from reactivex import Observable
from reactivex import operators as ops
from reactivex.abc import SchedulerBase
from reactivex.scheduler.eventloop import AsyncIOScheduler
from reactivex.subject import Subject

BANNED: frozenset[str] = frozenset({"спам", "казино", "дурак", "лох"})
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Message:
    """Сообщение пользователя."""

    user: str
    text: str


@dataclass(frozen=True)
class Command:
    """Команда модератора: action — "ban" или "unban"."""

    action: str
    user: str


@dataclass(frozen=True)
class Event:
    """Результат модерации."""

    kind: str  # post | censored | rate_limited | blocked | ban | unban
    user: str
    detail: str
    time: float


@dataclass(frozen=True)
class Config:
    """Параметры модерации (единицы времени планировщика)."""

    rate_limit: int = 3
    rate_window: float = 30
    strikes_to_ban: int = 3
    ban_time: float = 100
    banned: frozenset[str] = BANNED


@dataclass(frozen=True)
class ModState:
    """Неизменяемое состояние модератора."""

    recent: PMap = pmap()  # user → кортеж времён последних сообщений
    strikes: PMap = pmap()  # user → число нарушений
    banned_until: PMap = pmap()  # user → момент окончания бана
    emitted: tuple[Event, ...] = ()


# ============================ чистые функции ===============================
def is_banned_word(word: str, banned: frozenset[str]) -> bool:
    """Слово начинается с запрещённой основы."""
    w = word.lower()
    return any(w.startswith(stem) for stem in banned)


def censor(text: str, banned: frozenset[str]) -> tuple[str, int]:
    """(текст со звёздочками, число запрещённых слов)."""
    hits = sum(is_banned_word(w, banned) for w in _WORD.findall(text))
    clean = _WORD.sub(
        lambda m: (
            "*" * len(m.group())
            if is_banned_word(m.group(), banned)
            else m.group()
        ),
        text,
    )
    return clean, hits


def _emit(st: ModState, *events: Event) -> ModState:
    """Добавить события текущего шага."""
    return replace(st, emitted=st.emitted + events)


def _strike(cfg: Config, st: ModState, user: str, t: float) -> ModState:
    """Засчитать нарушение; при достижении порога — бан."""
    n = st.strikes.get(user, 0) + 1
    if n < cfg.strikes_to_ban:
        return replace(st, strikes=st.strikes.set(user, n))
    until = t + cfg.ban_time
    return _emit(
        replace(
            st,
            strikes=st.strikes.set(user, 0),
            banned_until=st.banned_until.set(user, until),
            recent=st.recent.discard(user),
        ),
        Event("ban", user, f"{n} нарушения → бан на {cfg.ban_time:g}", t),
    )


def on_message(cfg: Config, st: ModState, m: Message, t: float) -> ModState:
    """Обработать сообщение в момент t."""
    until = st.banned_until.get(m.user)
    if until is not None and t < until:
        return _emit(st, Event("blocked", m.user, m.text, t))
    if until is not None:  # срок бана истёк
        st = _emit(
            replace(st, banned_until=st.banned_until.discard(m.user)),
            Event("unban", m.user, "срок бана истёк", t),
        )
    recent = tuple(
        x for x in st.recent.get(m.user, ()) if x > t - cfg.rate_window
    )
    if len(recent) >= cfg.rate_limit:
        st = _emit(
            replace(st, recent=st.recent.set(m.user, recent)),
            Event("rate_limited", m.user, m.text, t),
        )
        return _strike(cfg, st, m.user, t)
    st = replace(st, recent=st.recent.set(m.user, recent + (t,)))
    clean, hits = censor(m.text, cfg.banned)
    if hits:
        return _strike(
            cfg, _emit(st, Event("censored", m.user, clean, t)), m.user, t
        )
    return _emit(st, Event("post", m.user, m.text, t))


def on_command(st: ModState, c: Command, t: float) -> ModState:
    """Обработать команду модератора."""
    if c.action == "ban":
        return _emit(
            replace(st, banned_until=st.banned_until.set(c.user, math.inf)),
            Event("ban", c.user, "модератором", t),
        )
    if c.action == "unban" and c.user in st.banned_until:
        return _emit(
            replace(
                st,
                banned_until=st.banned_until.discard(c.user),
                strikes=st.strikes.discard(c.user),
            ),
            Event("unban", c.user, "модератором", t),
        )
    return st


def step(cfg: Config) -> Callable[[ModState, Any], ModState]:
    """Функция свёртки состояния по событиям с отметкой времени."""

    def f(st: ModState, stamped: Any) -> ModState:
        t = stamped.timestamp.timestamp()
        st = replace(st, emitted=())
        item: Message | Command = stamped.value
        if isinstance(item, Command):
            return on_command(st, item, t)
        return on_message(cfg, st, item, t)

    return f


# ========================== реактивный компонент ===========================
def pipeline(
    messages: Observable,
    commands: Observable,
    scheduler: SchedulerBase,
    cfg: Config = Config(),
) -> Observable:
    """Потоки сообщений и команд → поток событий модерации."""
    return rx.merge(
        messages.pipe(ops.filter(lambda m: m.text.strip() != "")),
        commands,
    ).pipe(
        ops.timestamp(scheduler=scheduler),
        ops.scan(step(cfg), ModState()),
        ops.flat_map(lambda st: rx.from_iterable(st.emitted)),
    )


def published(events: Observable) -> Observable:
    """Лента чата: опубликованные сообщения."""
    return events.pipe(
        ops.filter(lambda e: e.kind in ("post", "censored")),
        ops.map(lambda e: f"{e.user}: {e.detail}"),
    )


def banned_users(events: Observable) -> Observable:
    """Множество забаненных пользователей при каждом изменении."""
    return events.pipe(
        ops.filter(lambda e: e.kind in ("ban", "unban")),
        ops.scan(
            lambda acc, e: (
                acc | {e.user} if e.kind == "ban" else acc - {e.user}
            ),
            frozenset(),
        ),
        ops.start_with(frozenset()),
        ops.distinct_until_changed(),
    )


def violations_by_user(events: Observable) -> Observable:
    """(пользователь, число отклонённых/зацензуренных сообщений)."""
    return events.pipe(
        ops.filter(
            lambda e: e.kind in ("censored", "rate_limited", "blocked")
        ),
        ops.group_by(lambda e: e.user),
        ops.flat_map(
            lambda g: g.pipe(
                ops.scan(lambda n, _: n + 1, 0),
                ops.map(lambda n, user=g.key: (user, n)),
            )
        ),
    )


def activity_report(
    events: Observable, period: float, scheduler: SchedulerBase
) -> Observable:
    """Каждые ``period`` — сводка «вид события: количество»."""

    def summarize(batch: list[Event]) -> str:
        kinds = sorted({e.kind for e in batch})
        return ", ".join(
            f"{k}: {sum(e.kind == k for e in batch)}" for k in kinds
        )

    return events.pipe(
        ops.buffer_with_time(period, scheduler=scheduler),
        ops.filter(bool),
        ops.map(summarize),
    )


# ================================ оболочка =================================
SCRIPT: tuple[tuple[float, Message | Command], ...] = (
    (0.00, Message("aruzhan", "Всем привет!")),
    (0.05, Message("erlan", "Заходите в казино")),
    (0.10, Message("daniyar", "Кто готов к защите?")),
    (0.15, Message("erlan", "спам спам")),
    (0.20, Message("dana", "1")),
    (0.22, Message("dana", "2")),
    (0.24, Message("dana", "3")),
    (0.26, Message("dana", "4")),
    (0.30, Message("erlan", "ну и ладно")),
    (0.40, Message("erlan", "казино лучшее")),
    (0.45, Message("erlan", "почему меня не слышно?")),
    (0.50, Command("ban", "spammer")),
    (0.55, Message("aruzhan", "Модерация работает")),
    (1.30, Message("erlan", "Я исправился")),
    (1.35, Command("ban", "erlan")),
    (1.40, Message("erlan", "эй!")),
    (1.50, Command("unban", "erlan")),
    (1.55, Message("erlan", "спасибо")),
)
REAL_CFG = Config(
    rate_limit=3, rate_window=0.3, strikes_to_ban=3, ban_time=0.7
)


async def main() -> None:
    """Воспроизвести сценарий в реальном времени (AsyncIOScheduler)."""
    loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler(loop)
    messages, commands = Subject(), Subject()
    events = pipeline(messages, commands, scheduler, REAL_CFG).pipe(
        ops.share()
    )
    start = {"t": 0.0}

    def show(e: Event) -> None:
        print(
            f"{e.time - start['t']:5.2f} с  {e.kind:<13} {e.user:<8} "
            f"{e.detail}"
        )

    subs = [
        events.subscribe(show),
        banned_users(events).subscribe(
            lambda b: print(f"        забанены: {sorted(b) or '—'}")
        ),
        activity_report(events, 0.5, scheduler).subscribe(
            lambda r: print(f"        [отчёт за 0.5 с] {r}")
        ),
    ]
    start["t"] = scheduler.now.timestamp()
    elapsed = 0.0
    for at, item in SCRIPT:
        await asyncio.sleep(at - elapsed)
        elapsed = at
        (commands if isinstance(item, Command) else messages).on_next(item)
    await asyncio.sleep(0.6)
    messages.on_completed()
    commands.on_completed()
    for s in subs:
        s.dispose()


if __name__ == "__main__":
    asyncio.run(main())
