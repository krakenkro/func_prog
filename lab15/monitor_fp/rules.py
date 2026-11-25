"""Чистые правила оповещений: (состояние, замер) → (состояние, оповещения).

Каждое правило — функция без побочных эффектов; состояние правила
передаётся и возвращается явно.
"""

from __future__ import annotations

from monitor_fp.model import Alert, Config, Metric

Alerts = tuple[Alert, ...]


def push_window(window: tuple[float, ...], x: float,
                size: int) -> tuple[float, ...]:
    """Скользящее окно из ``size`` последних значений."""
    return (*window, x)[-size:]


def cpu_rule(window: tuple[float, ...], alarm: bool, m: Metric,
             cfg: Config) -> tuple[tuple[float, ...], bool, Alerts]:
    """Среднее CPU за окно: тревога выше cpu_high, отбой ниже cpu_ok."""
    window = push_window(window, m.cpu, cfg.window)
    if len(window) < cfg.window:
        return window, alarm, ()
    avg = sum(window) / cfg.window
    if not alarm and avg > cfg.cpu_high:
        return window, True, (Alert(m.ts, m.server, "CPU_HIGH", "CRIT",
                                    f"CPU {avg:.1f}% (среднее за "
                                    f"{cfg.window} замера)"),)
    if alarm and avg < cfg.cpu_ok:
        return window, False, (Alert(m.ts, m.server, "CPU_OK", "INFO",
                                     f"CPU {avg:.1f}%, нагрузка "
                                     "снизилась"),)
    return window, alarm, ()


def mem_rule(last: int | None, m: Metric,
             cfg: Config) -> tuple[int | None, Alerts]:
    """Память выше порога — не чаще одного оповещения за mem_cooldown."""
    if m.mem > cfg.mem_high and (last is None
                                 or m.ts - last >= cfg.mem_cooldown):
        return m.ts, (Alert(m.ts, m.server, "MEM_HIGH", "WARN",
                            f"память {m.mem:.1f}%"),)
    return last, ()


def slow_rule(streak: int, m: Metric, cfg: Config) -> tuple[int, Alerts]:
    """Задержка выше порога: оповещение на втором замере серии."""
    if m.latency <= cfg.lat_high:
        return 0, ()
    streak += 1
    if streak == 2:
        return streak, (Alert(m.ts, m.server, "SLOW", "WARN",
                               f"задержка {m.latency:.0f} мс два замера "
                               "подряд"),)
    return streak, ()


def down_alert(server: str, ts: int, cfg: Config) -> Alert:
    """Оповещение о молчании сервера."""
    return Alert(ts, server, "DOWN", "CRIT",
                 f"нет данных более {cfg.silence} с")


def up_alert(m: Metric) -> Alert:
    """Оповещение о возобновлении данных."""
    return Alert(m.ts, m.server, "UP", "INFO", "данные снова поступают")
