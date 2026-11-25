# Задание 1: исходная монолитная программа (без изменений, для сравнения).
# ruff: noqa
import csv, datetime

def main():
    rows = []
    with open("grades.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["score"] = int(r["score"])
            rows.append(r)
    today = datetime.date.today()
    groups = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r["score"])
    for g in sorted(groups):
        avg = sum(groups[g]) / len(groups[g])
        status = "ОК" if avg >= 70 else "РИСК"
        print(f"{today} {g}: средний {avg:.1f} [{status}]")
    with open("report.txt", "w", encoding="utf-8") as out:
        out.write(f"Отчёт от {today}: групп {len(groups)}\n")

main()
