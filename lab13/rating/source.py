"""Имитация удалённого источника журналов (детерминированная)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

TASKS = (*(f"lab{i}" for i in range(1, 9)), "rk1", "rk2", "exam")
MAXIMA = {"lab": 5.0, "rk": 100.0, "exam": 100.0}
NAMES = ("Айгерим", "Алихан", "Арман", "Асель", "Бауыржан", "Дана",
         "Данияр", "Дильназ", "Ержан", "Жанна", "Зарина", "Ильяс",
         "Камила", "Марат", "Мадина", "Нурлан", "Салтанат", "Тимур")


def journal_text(group: str, students: int = 12, seed: int = 4,
                 skip_rate: float = 0.05) -> str:
    """Сгенерировать текст журнала группы (с пропусками и ошибками)."""
    rnd = random.Random(f"{group}-{seed}")
    lines = [f"# журнал группы {group}"]
    for i in range(students):
        name = f"{NAMES[i % len(NAMES)]}-{group}-{i // len(NAMES) + 1}"
        level = rnd.uniform(0.35, 1.0)
        for task in TASKS:
            if rnd.random() < skip_rate:
                continue
            mx = MAXIMA[task.rstrip("0123456789")]
            score = round(min(mx, max(0.0, rnd.gauss(level, 0.12) * mx)), 1)
            lines.append(f"{name};{task};{score:g};{mx:g}")
    if rnd.random() < 0.3:                  # ошибка в части журналов
        lines.append(f"Нарушитель;lab1;7;{MAXIMA['lab']:g}")
    return "\n".join(lines) + "\n"


def make_fetch(delays: dict[str, float], broken: frozenset[str] = frozenset(),
               students: int = 12,
               sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
               ) -> Callable[[str], Awaitable[str]]:
    """Асинхронная «загрузка» журнала группы с заданной задержкой."""

    async def fetch(group: str) -> str:
        await sleep(delays.get(group, 0.1))
        if group in broken:
            raise ConnectionError(f"сервер группы {group} недоступен")
        return journal_text(group, students)

    return fetch
