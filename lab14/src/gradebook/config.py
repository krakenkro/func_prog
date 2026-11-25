"""Конфигурация: значения по умолчанию ← файл TOML ← переменные окружения.

Результат — глубоко неизменяемый ``pyrsistent.PMap`` (``freeze``).
Переменные окружения передаются параметром (а не читаются из os.environ).
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from typing import Any

from pyrsistent import PMap, freeze

from gradebook.scale import Scale

PREFIX = "GRADEBOOK_"
DEFAULTS: PMap[str, Any] = freeze({
    "scale": Scale()._asdict(),
    "report": {"format": "txt", "top": 0},
})


def parse_scalar(text: str) -> Any:
    """'40' → 40, '0.1' → 0.1, 'true' → True, иначе строка."""
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    """GRADEBOOK_SCALE__EXAM_WEIGHT=40 → {'scale': {'exam_weight': 40}}."""
    result: dict[str, Any] = {}
    for key, value in env.items():
        if not key.startswith(PREFIX):
            continue
        *path, last = key[len(PREFIX):].lower().split("__")
        node = result
        for part in path:
            node = node.setdefault(part, {})
        node[last] = parse_scalar(value)
    return result


def deep_merge(base: PMap[str, Any], extra: Mapping[str, Any],
               ) -> PMap[str, Any]:
    """Рекурсивное слияние: значения extra перекрывают base."""
    merged = base
    for key, value in extra.items():
        old = base.get(key)
        merged = merged.set(key, deep_merge(old, value)
                            if isinstance(old, PMap)
                            and isinstance(value, Mapping)
                            else freeze(value))
    return merged


def load_config(file_text: str | None, env: Mapping[str, str],
                defaults: PMap[str, Any] = DEFAULTS) -> PMap[str, Any]:
    """Слить умолчания, содержимое файла TOML и переменные окружения."""
    from_file = tomllib.loads(file_text) if file_text else {}
    return deep_merge(deep_merge(defaults, from_file), env_overrides(env))


