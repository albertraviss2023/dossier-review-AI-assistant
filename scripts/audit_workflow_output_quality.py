from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "state" / "reports"


@dataclass
class StepQualityIssue:
    dossier_id: str
    step_id: int
    step_name: str
    issue: str
    severity: str
    response_excerpt: str


def _latest_simulation_path() -> Path | None:
    candidates = sorted(REPORTS_DIR.glob("workflow_simulation_*.json"), reverse=True)
    return candidates[0] if candidates else None


def _word_count(text: str) -> int:
    return len([token for token in str(text).split() if token.strip()])


def _check_step_depth(step: dict[str, Any]) -> list[StepQualityIssue]:
    issues: list[StepQualityIssue] = []
    step_id = int(step.get("step_id", 0))
    step_name = str(step.get("step_name", "unknown"))
    dossier_id = str(step.get("dossier_id", "unknown"))
    full_text = str(step.get("response_full", "")) or str(step.get("response_excerpt", ""))
    excerpt = str(step.get("response_excerpt", ""))
    words = _word_count(full_text)
    if words < 45:
        issues.append(
            StepQualityIssue(
                dossier_id=dossier_id,
                step_id=step_id,
                step_name=step_name,
                issue=f"Response too short for structured review step ({words} words).",
                severity="major",
                response_excerpt=excerpt[:300],
            )
        )
    lower = full_text.lower()
    if step_id == 7:
        amr_terms = ("aware", "stewardship", "authorization", "resistance", "watch", "reserve")
        missing = [term for term in amr_terms if term not in lower]
        if len(missing) >= 3:
            issues.append(
                StepQualityIssue(
                    dossier_id=dossier_id,
                    step_id=step_id,
                    step_name=step_name,
                    issue="AMR step lacks policy-depth terms required for decision support.",
                    severity="critical",
                    response_excerpt=excerpt[:300],
                )
            )
    if step_id == 12:
        verdict_terms = ("final verdict", "recommendation", "acceptable", "revision", "not acceptable", "escalate")
        if not any(term in lower for term in verdict_terms):
            issues.append(
                StepQualityIssue(
                    dossier_id=dossier_id,
                    step_id=step_id,
                    step_name=step_name,
                    issue="Overall verdict step does not clearly express decision language.",
                    severity="major",
                    response_excerpt=excerpt[:300],
                )
            )
    return issues


def run(simulation_path: Path | None = None) -> dict[str, Any]:
    simulation_path = simulation_path or _latest_simulation_path()
    if simulation_path is None or not simulation_path.exists():
        raise FileNotFoundError("No workflow simulation report found. Run structured simulation first.")

    payload = json.loads(simulation_path.read_text(encoding="utf-8"))
    steps = payload.get("step_results", [])

    issues: list[StepQualityIssue] = []
    for step in steps:
        issues.extend(_check_step_depth(step))

    summary = {
        "source_simulation": str(simulation_path),
        "total_steps": len(steps),
        "issue_count": len(issues),
        "critical_count": sum(1 for issue in issues if issue.severity == "critical"),
        "major_count": sum(1 for issue in issues if issue.severity == "major"),
        "issues": [asdict(issue) for issue in issues],
        "status": "pass" if not issues else "needs_improvement",
    }
    out_path = REPORTS_DIR / f"workflow_quality_audit_{simulation_path.stem}.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved quality audit: {out_path}")
    return summary


if __name__ == "__main__":
    run()
