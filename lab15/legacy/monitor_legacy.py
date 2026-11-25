# Исходное императивное решение практического случая (вариант 4):
# мониторинг серверов с оповещениями. Написано в «типичном» императивном
# стиле и намеренно не исправляется — это объект анализа и рефакторинга.
#
# Запуск: python monitor_legacy.py metrics.csv [report.csv]
# Формат журнала: ts,server,cpu,mem,latency_ms (ts — секунды, по возрастанию)
# ruff: noqa
import sys

CPU_HIGH = 85.0
CPU_OK = 70.0
MEM_HIGH = 90.0
MEM_COOLDOWN = 60
LAT_HIGH = 500.0
SILENCE = 30

last_seen = {}
cpu_window = {}
cpu_alarm = {}
mem_last = {}
slow_count = {}
down = set()
alerts = []
stats = {}
errors = []


def process_line(line, lineno):
    global errors
    parts = line.strip().split(",")
    if len(parts) != 5:
        errors.append("строка %d: неверное число полей" % lineno)
        return None
    try:
        ts = int(parts[0])
        server = parts[1].strip()
        cpu = float(parts[2])
        mem = float(parts[3])
        lat = float(parts[4])
    except ValueError:
        errors.append("строка %d: не число" % lineno)
        return None
    if server == "":
        errors.append("строка %d: пустое имя сервера" % lineno)
        return None
    if cpu < 0 or cpu > 100 or mem < 0 or mem > 100 or lat < 0:
        errors.append("строка %d: значение вне диапазона" % lineno)
        return None
    return (ts, server, cpu, mem, lat)


def check_silence(now):
    for s in list(last_seen.keys()):
        if s not in down and now - last_seen[s] > SILENCE:
            down.add(s)
            alerts.append((last_seen[s] + SILENCE, s, "DOWN", "CRIT",
                           "нет данных более %d с" % SILENCE))


def handle(ts, server, cpu, mem, lat):
    check_silence(ts)
    if server in down:
        down.remove(server)
        alerts.append((ts, server, "UP", "INFO", "данные снова поступают"))
    last_seen[server] = ts
    # статистика
    if server not in stats:
        stats[server] = {"n": 0, "cpu_max": 0.0, "lat_sum": 0.0,
                         "alerts": 0}
    stats[server]["n"] += 1
    if cpu > stats[server]["cpu_max"]:
        stats[server]["cpu_max"] = cpu
    stats[server]["lat_sum"] += lat
    # CPU: среднее за 3 замера с гистерезисом
    if server not in cpu_window:
        cpu_window[server] = []
    cpu_window[server].append(cpu)
    if len(cpu_window[server]) > 3:
        cpu_window[server].pop(0)
    if len(cpu_window[server]) == 3:
        avg = sum(cpu_window[server]) / 3
        if not cpu_alarm.get(server, False) and avg > CPU_HIGH:
            cpu_alarm[server] = True
            alerts.append((ts, server, "CPU_HIGH", "CRIT",
                           "CPU %.1f%% (среднее за 3 замера)" % avg))
        elif cpu_alarm.get(server, False) and avg < CPU_OK:
            cpu_alarm[server] = False
            alerts.append((ts, server, "CPU_OK", "INFO",
                           "CPU %.1f%%, нагрузка снизилась" % avg))
    # память: не чаще одного оповещения за MEM_COOLDOWN секунд
    if mem > MEM_HIGH:
        if server not in mem_last or ts - mem_last[server] >= MEM_COOLDOWN:
            mem_last[server] = ts
            alerts.append((ts, server, "MEM_HIGH", "WARN",
                           "память %.1f%%" % mem))
    # задержка: два замера подряд выше порога
    if lat > LAT_HIGH:
        slow_count[server] = slow_count.get(server, 0) + 1
        if slow_count[server] == 2:
            alerts.append((ts, server, "SLOW", "WARN",
                           "задержка %.0f мс два замера подряд" % lat))
    else:
        slow_count[server] = 0


def main():
    if len(sys.argv) < 2:
        print("использование: monitor_legacy.py metrics.csv [report.csv]")
        return 1
    path = sys.argv[1]
    report_path = None
    if len(sys.argv) > 2:
        report_path = sys.argv[2]
    f = open(path, encoding="utf-8")
    lineno = 0
    last_ts = None
    for line in f:
        lineno += 1
        if line.strip() == "" or line.startswith("#"):
            continue
        rec = process_line(line, lineno)
        if rec is None:
            continue
        if last_ts is not None and rec[0] < last_ts:
            errors.append("строка %d: нарушен порядок времени" % lineno)
            continue
        last_ts = rec[0]
        handle(rec[0], rec[1], rec[2], rec[3], rec[4])
    f.close()
    if last_ts is not None:
        check_silence(last_ts)
    alerts.sort(key=lambda a: (a[0], a[1], a[2]))
    for e in errors:
        print("ПРЕДУПРЕЖДЕНИЕ:", e)
    for a in alerts:
        stats[a[1]]["alerts"] += 1
        print("[%6d] %-4s %s: %s" % (a[0], a[3], a[1], a[4]))
    print("=== Итоги ===")
    for s in sorted(stats):
        st = stats[s]
        print("%s: замеров %d, CPU max %.1f%%, задержка ср. %.1f мс, "
              "оповещений %d" % (s, st["n"], st["cpu_max"],
                                 st["lat_sum"] / st["n"], st["alerts"]))
    print("Всего оповещений: %d, ошибок разбора: %d"
          % (len(alerts), len(errors)))
    if report_path:
        out = open(report_path, "w", encoding="utf-8")
        counts = {}
        for a in alerts:
            counts[a[2]] = counts.get(a[2], 0) + 1
        out.write("code,count\n")
        for k in sorted(counts):
            out.write("%s,%d\n" % (k, counts[k]))
        out.close()
        print("отчёт:", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
