"""Generate coverage status for a batch run.

This is an operator/debug helper. It does not run collection or verification;
it only reads an existing batch run and writes coverage_status.json plus
coverage_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.coverage.analyzer import write_coverage_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze supported tax-type coverage for a batch run.")
    parser.add_argument("--run-dir", required=True, help="Batch run directory, for example output/batch_runs/ops_xxx.")
    parser.add_argument("--report-root", default="output/reports", help="Report root directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = write_coverage_status(Path(args.run_dir), report_root=Path(args.report_root))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"written: {Path(args.run_dir) / 'coverage_status.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
