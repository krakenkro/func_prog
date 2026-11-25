"""Асинхронная загрузка журналов групп с ограничением конкурентности."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import NamedTuple

Fetch = Callable[[str], Awaitable[str]]
TIMEOUT_TEXT = "превышено время ожидания"


class Loaded(NamedTuple):
    """Результат загрузки: журналы и сообщения о сбоях."""

    journals: tuple[tuple[str, str], ...]
    failed: tuple[str, ...]


def split_results(groups: Sequence[str],
                  results: Sequence[str | BaseException]) -> Loaded:
    """Чистая функция: разделить успешные загрузки и ошибки."""
    pairs = tuple(zip(groups, results, strict=True))
    return Loaded(
        tuple((g, r) for g, r in pairs if isinstance(r, str)),
        tuple(f"{g}: {type(r).__name__}: {str(r) or TIMEOUT_TEXT}"
              for g, r in pairs if isinstance(r, BaseException)),
    )


async def load_groups(groups: Sequence[str], fetch: Fetch, limit: int = 3,
                      timeout: float = 1.0) -> Loaded:
    """Загрузить журналы конкурентно (не более ``limit`` одновременно)."""
    sem = asyncio.Semaphore(limit)

    async def one(group: str) -> str:
        async with sem:
            return await asyncio.wait_for(fetch(group), timeout)

    results = await asyncio.gather(*map(one, groups), return_exceptions=True)
    return split_results(groups, results)


async def load_sequential(groups: Sequence[str], fetch: Fetch,
                          timeout: float = 1.0) -> Loaded:
    """Последовательная загрузка — для сравнения времени."""
    results: list[str | BaseException] = []
    for g in groups:
        try:
            results.append(await asyncio.wait_for(fetch(g), timeout))
        except Exception as exc:  # noqa: BLE001 — ошибка как значение
            results.append(exc)
    return split_results(groups, results)
