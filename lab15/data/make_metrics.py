"""Генератор детерминированного журнала метрик (сценарии сбоев)."""

import random
import sys
from pathlib import Path

SERVERS = ("web-1", "web-2", "db-1", "cache-1")


def generate(steps: int, seed: int = 4) -> str:
    """Журнал: замер каждого сервера раз в 5 с, всплески и «молчание»."""
    rnd = random.Random(seed)
    lines = ["# ts,server,cpu,mem,latency_ms"]
    for step in range(steps):
        phase = step % 200
        for server in SERVERS:
            if server == "cache-1" and 80 <= phase < 92:
                continue                                  # сервер молчит
            if rnd.random() < 0.02:
                continue                                  # потеря замера
            cpu = rnd.gauss(45, 10)
            if server == "web-1" and 40 <= phase < 64:
                cpu = rnd.gauss(93, 4)                    # перегрузка CPU
            mem = rnd.gauss(60, 8)
            if server == "db-1" and 100 <= phase < 140:
                mem = rnd.gauss(93, 2)                    # утечка памяти
            lat = rnd.gauss(180, 60)
            if server == "web-2" and phase in (20, 21, 22, 150, 152):
                lat = rnd.gauss(800, 50)                  # медленные ответы
            lines.append(f"{step * 5},{server},{min(max(cpu, 0), 100):.1f},"
                         f"{min(max(mem, 0), 100):.1f},{max(lat, 0):.0f}")
        if rnd.random() < 0.01:
            lines.append(rnd.choice(("мусор", f"{step * 5},web-1,abc,1,1",
                                     f"{step * 5},,1,1,1",
                                     f"{step * 5},db-1,150,1,1",
                                     f"{step * 5 - 100},web-1,1,1,1")))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    Path(sys.argv[2] if len(sys.argv) > 2 else "metrics.csv").write_text(
        generate(steps), encoding="utf-8")
