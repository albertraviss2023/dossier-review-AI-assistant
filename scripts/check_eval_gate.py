from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check evaluation report release gate status")
    parser.add_argument("report", help="Path to evaluation report JSON")
    parser.add_argument(
        "--acceptance",
        default="docs/acceptance-criteria.yaml",
        help="Acceptance criteria file used to ensure required metrics are present",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    acceptance = yaml.safe_load(Path(args.acceptance).read_text(encoding="utf-8"))
    required_metrics = set(acceptance.get("metrics", {}).keys())
    summary = report.get("summary", {})
    release_status = summary.get("release_gate_status", {})
    overall_passed = bool(release_status.get("overall_passed", False))
    all_metrics_passed = bool(summary.get("all_metrics_passed", False))
    reported_metrics = report.get("metrics", {})
    missing_metrics = sorted(required_metrics - set(reported_metrics.keys()))

    if overall_passed and all_metrics_passed and not missing_metrics:
        print("evaluation_gate=PASS")
        return 0

    print("evaluation_gate=FAIL")
    failed = [name for name, payload in reported_metrics.items() if not payload.get("passed", False)]
    if failed:
        print("failed_metrics=" + ",".join(sorted(failed)))
    if missing_metrics:
        print("missing_required_metrics=" + ",".join(missing_metrics))
    return 1


if __name__ == "__main__":
    sys.exit(main())
