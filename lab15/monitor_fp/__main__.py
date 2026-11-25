"""python -m monitor_fp metrics.csv [report.csv]."""

import sys

from monitor_fp.shell import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
