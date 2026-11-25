"""Точка входа заданий 1–2: python main_grades.py [txt|csv|md]."""

import sys
from pathlib import Path

from gradesapp.shell import production

if __name__ == "__main__":
    fmt = sys.argv[1] if len(sys.argv) > 1 else "txt"
    production(Path("grades.csv"), Path(f"report.{fmt}"), fmt)()
