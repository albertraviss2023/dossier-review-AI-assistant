from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dossier_review_ai_assistant.audit import read_audit_records, write_audit_records
from dossier_review_ai_assistant.governance import retention_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check and optionally enforce retention policy on audit logs")
    parser.add_argument(
        "--audit-log",
        default="state/audit/recommendations.jsonl",
        help="Audit log path",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Retention period in days",
    )
    parser.add_argument(
        "--output",
        default="state/audit/retention_report.json",
        help="Where to write retention report",
    )
    parser.add_argument(
        "--apply-delete",
        action="store_true",
        help="Delete expired records by rewriting audit log",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_path = Path(args.audit_log)
    records = read_audit_records(audit_path)
    summary = retention_stats(records, retention_days=args.retention_days)

    kept_records = records
    deleted_count = 0
    if args.apply_delete and records:
        cutoff = datetime.now(UTC).timestamp() - (args.retention_days * 86400)
        kept_records = []
        for row in records:
            ts = row.get("created_at_utc")
            if not ts:
                kept_records.append(row)
                continue
            try:
                dt = datetime.fromisoformat(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            except ValueError:
                kept_records.append(row)
                continue
            if dt.timestamp() >= cutoff:
                kept_records.append(row)
            else:
                deleted_count += 1

        write_audit_records(audit_path, kept_records)

    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "audit_log": str(audit_path),
        "retention_days": args.retention_days,
        "apply_delete": args.apply_delete,
        "deleted_records": deleted_count,
        "summary": summary,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"report_path={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

