from __future__ import annotations

import os
import subprocess
from typing import Any


class Gemma4Client:
    def __init__(self, model_id: str = "ai/gemma4:4B-Q4_K_XL") -> None:
        self.model_id = model_id
        self.mode = os.getenv("DOSSIER_GEMMA4_MODE", "mock").lower()

    def _mock_generate(self, recommendation: str, evidence: list[dict[str, Any]], question: str) -> dict[str, Any]:
        claims: list[dict[str, str]] = []
        for ev in evidence[:3]:
            claims.append(
                {
                    "text": f"Evidence from {ev['section_title']} supports regulatory assessment for {recommendation}.",
                    "citation_id": ev["citation_id"],
                }
            )

        if not claims:
            claims.append(
                {
                    "text": "No sufficient evidence was found for a grounded recommendation.",
                    "citation_id": "",
                }
            )

        lines = [f"Question: {question}", f"Proposed recommendation: {recommendation}", "Grounded rationale:"]
        for idx, claim in enumerate(claims, start=1):
            citation = claim["citation_id"] or "missing_citation"
            lines.append(f"{idx}. {claim['text']} [{citation}]")

        return {"rationale": "\n".join(lines), "claims": claims}

    def _docker_generate(self, prompt: str) -> str:
        command = ["docker", "model", "run", self.model_id, "--prompt", prompt]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "docker model run failed")
        return completed.stdout.strip()

    def generate(
        self,
        question: str,
        recommendation: str,
        evidence: list[dict[str, Any]],
        route: str,
    ) -> dict[str, Any]:
        if self.mode != "docker":
            return self._mock_generate(recommendation=recommendation, evidence=evidence, question=question)

        prompt_lines = [
            f"You are a regulatory dossier assistant using Gemma4 route={route}.",
            f"Question: {question}",
            f"Recommendation: {recommendation}",
            "Cite each claim with citation_id in brackets.",
            "Evidence:",
        ]
        for ev in evidence[:6]:
            prompt_lines.append(
                f"- {ev['citation_id']} | {ev['section_title']} | snippet={ev['snippet']}"
            )
        prompt = "\n".join(prompt_lines)
        text = self._docker_generate(prompt)
        return {
            "rationale": text,
            "claims": [{"text": text, "citation_id": evidence[0]["citation_id"] if evidence else ""}],
        }

