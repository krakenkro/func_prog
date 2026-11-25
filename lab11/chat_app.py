"""Задание 6 (вариант 4). Чат на собственной библиотеке rx_mini.

Несколько каналов, фильтр запрещённых слов, счётчики активности.

Архитектура «функциональное ядро — императивная оболочка»:

* ядро — чистые функции над сообщениями (``censor``, ``inc`` …) и
  реактивный компонент ``chat_pipeline(*channels) -> ChatStreams``;
* оболочка — ``main``: читает события из файла, отправляет их в субъекты
  каналов и печатает результаты подписчиков.

Используемые операторы: merge, take_while, filter_, distinct_until_changed,
map_, scan, start_with, pairwise, buffer_with_count, reduce_ и Subject.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from rx_mini import (
    Observable,
    Subject,
    buffer_with_count,
    distinct_until_changed,
    filter_,
    map_,
    merge,
    pairwise,
    reduce_,
    scan,
    start_with,
    take_while,
)

BANNED: frozenset[str] = frozenset({"спам", "казино", "дурак", "лох"})
STOP_COMMAND = "/stop"
WARN_AFTER = 2
BATCH = 4
Counts = tuple[tuple[str, int], ...]
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Message:
    """Сообщение чата."""

    channel: str
    user: str
    text: str


# =========================== чистые функции ядра ===========================
def is_banned(word: str, banned: frozenset[str] = BANNED) -> bool:
    """Слово запрещено, если начинается с запрещённой основы.

    Сравнение по основе ловит словоформы: «дураком», «казино».
    """
    w = word.lower()
    return any(w.startswith(stem) for stem in banned)


def banned_words(
    text: str, banned: frozenset[str] = BANNED
) -> tuple[str, ...]:
    """Запрещённые слова в тексте (без учёта регистра)."""
    return tuple(w for w in _WORD.findall(text) if is_banned(w, banned))


def censor(text: str, banned: frozenset[str] = BANNED) -> str:
    """Заменить запрещённые слова звёздочками той же длины."""
    return _WORD.sub(
        lambda m: (
            "*" * len(m.group()) if is_banned(m.group(), banned) else m.group()
        ),
        text,
    )


def inc(counts: Counts, key: str) -> Counts:
    """Неизменяемый счётчик: новая версия с увеличенным ключом."""
    d = dict(counts)
    return tuple(sorted({**d, key: d.get(key, 0) + 1}.items()))


def leader(counts: Counts) -> str:
    """Ключ с максимальным счётчиком (при равенстве — по алфавиту)."""
    return min(counts, key=lambda kv: (-kv[1], kv[0]))[0]


def fmt_counts(counts: Counts) -> str:
    """«#a: 2, #b: 1»."""
    return ", ".join(f"{k}: {v}" for k, v in counts) or "пусто"


def is_crosspost(pair: tuple[Message, Message]) -> bool:
    """Один и тот же текст одного автора подряд в разных каналах."""
    a, b = pair
    return a.user == b.user and a.text == b.text and a.channel != b.channel


# ========================== реактивный компонент ===========================
class ChatStreams(NamedTuple):
    """Выходные потоки чата."""

    feed: Observable  # отцензурированная лента
    violations: Observable  # (пользователь, число нарушений)
    warnings: Observable  # предупреждения после WARN_AFTER нарушений
    channel_activity: Observable  # счётчики сообщений по каналам
    top_user: Observable  # смена лидера по активности
    crossposts: Observable  # кросспостинг
    batches: Observable  # активность каналов в пакетах по BATCH
    summary: Observable  # итог сеанса (одно значение при завершении)


def chat_pipeline(
    *channels: Observable, banned: frozenset[str] = BANNED
) -> ChatStreams:
    """Построить все потоки чата из потоков сообщений каналов."""
    messages = merge(*channels).pipe(
        take_while(lambda m: m.text != STOP_COMMAND),  # завершение сеанса
        filter_(lambda m: m.text.strip() != ""),  # пустые — мимо
        distinct_until_changed(lambda m: (m.channel, m.user, m.text)),
    )
    feed = messages.pipe(
        map_(lambda m: f"{m.channel:<9} {m.user}: {censor(m.text, banned)}")
    )
    violations = messages.pipe(
        filter_(lambda m: bool(banned_words(m.text, banned))),
        scan(lambda acc, m: (inc(acc[0], m.user), m.user), ((), "")),
        map_(lambda acc: (acc[1], dict(acc[0])[acc[1]])),
    )
    warnings = violations.pipe(
        filter_(lambda uv: uv[1] == WARN_AFTER),
        map_(lambda uv: f"предупреждение: {uv[0]} — {uv[1]} нарушения"),
    )
    channel_activity = messages.pipe(
        scan(lambda acc, m: inc(acc, m.channel), ()),
        start_with(()),
        map_(fmt_counts),
    )
    top_user = messages.pipe(
        scan(lambda acc, m: inc(acc, m.user), ()),
        map_(leader),
        distinct_until_changed(),
    )
    crossposts = messages.pipe(
        pairwise(),
        filter_(is_crosspost),
        map_(
            lambda p: (
                f"кросспостинг: {p[1].user} в {p[0].channel} и {p[1].channel}"
            )
        ),
    )
    batches = messages.pipe(
        buffer_with_count(BATCH),
        map_(
            lambda batch: fmt_counts(
                tuple(
                    sorted(
                        {
                            m.channel: sum(
                                x.channel == m.channel for x in batch
                            )
                            for m in batch
                        }.items()
                    )
                )
            )
        ),
    )
    summary = messages.pipe(
        reduce_(
            lambda acc, m: (acc[0] + 1, acc[1] | {m.user}), (0, frozenset())
        ),
        map_(
            lambda acc: f"итог: {acc[0]} сообщений от {len(acc[1])} участников"
        ),
    )
    return ChatStreams(
        feed,
        violations,
        warnings,
        channel_activity,
        top_user,
        crossposts,
        batches,
        summary,
    )


# ================================ оболочка =================================
def parse_line(line: str) -> Message:
    """Строка файла «#канал|пользователь|текст» → Message."""
    channel, user, text = (part.strip() for part in line.split("|", 2))
    return Message(channel, user, text)


def load_events(path: Path) -> tuple[Message, ...]:
    """Прочитать события из файла (пустые строки и # комментарии — мимо)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(
        parse_line(ln)
        for ln in lines
        if ln.strip() and not ln.startswith("//")
    )


def main(path: Path) -> None:
    """Воспроизвести журнал событий через реактивный компонент."""
    events = load_events(path)
    names = sorted({m.channel for m in events})
    subjects = {n: Subject() for n in names}
    streams = chat_pipeline(*subjects.values())

    streams.feed.subscribe(lambda s: print("  " + s))
    streams.violations.subscribe(
        lambda uv: print(f"    [фильтр] нарушение у {uv[0]} (всего {uv[1]})")
    )
    streams.warnings.subscribe(lambda s: print(f"    [модератор] {s}"))
    streams.top_user.subscribe(lambda u: print(f"    [активность] лидер: {u}"))
    streams.crossposts.subscribe(lambda s: print(f"    [антиспам] {s}"))
    streams.batches.subscribe(lambda s: print(f"    [пакет из {BATCH}] {s}"))
    final = {"counts": ""}
    streams.channel_activity.subscribe(
        lambda s: final.update(counts=s),
        on_completed=lambda: print(
            f"\nсообщений по каналам: {final['counts']}"
        ),
    )
    streams.summary.subscribe(print)

    for m in events:
        subjects[m.channel].on_next(m)
    for s in subjects.values():
        s.on_completed()


if __name__ == "__main__":
    main(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).with_name("chat_log.txt")
    )
