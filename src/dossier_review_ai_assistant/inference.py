from __future__ import annotations

import json
import os
import subprocess
from urllib import request
from typing import Any


class LocalModelClient:
    def __init__(self, model_id: str = "gemma-e4b") -> None:
        self.model_id = model_id
        self.mode = os.getenv("DOSSIER_MODEL_MODE", os.getenv("DOSSIER_GEMMA4_MODE", "mock")).lower()
        self.vllm_base_url = os.getenv("DOSSIER_VLLM_BASE_URL", "http://127.0.0.1:8001/v1/chat/completions")
        self.vllm_api_key = os.getenv(os.getenv("DOSSIER_VLLM_API_KEY_ENV", "VLLM_API_KEY"), "")

    def _mock_generate(
        self,
        recommendation: str,
        evidence: list[dict[str, Any]],
        question: str,
        conversation_context: str | None = None,
    ) -> dict[str, Any]:
        claims: list[dict[str, str]] = []
        for ev in evidence[:3]:
            claims.append(
                {
                    "text": (
                        f"Evidence from {ev['section_title']} supports regulatory assessment for "
                        f"{recommendation} using model {self.model_id}."
                    ),
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

        lines = [
            f"Question: {question}",
            f"Selected model: {self.model_id}",
            f"Proposed recommendation: {recommendation}",
            f"Conversation context: {conversation_context or 'none'}",
            "Grounded rationale:",
        ]
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

    def _vllm_generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a regulatory dossier review assistant. Cite every grounded claim with citation IDs.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if self.vllm_api_key:
            headers["Authorization"] = f"Bearer {self.vllm_api_key}"
        req = request.Request(
            self.vllm_base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=45) as response:  # noqa: S310
            parsed = json.loads(response.read().decode("utf-8"))
        choices = parsed.get("choices", [])
        if not choices:
            raise RuntimeError("vLLM response did not include choices")
        message = choices[0].get("message", {})
        return str(message.get("content", "")).strip()

    def generate(
        self,
        question: str,
        recommendation: str,
        evidence: list[dict[str, Any]],
        route: str,
        conversation_context: str | None = None,
    ) -> dict[str, Any]:
        if self.mode == "mock":
            return self._mock_generate(
                recommendation=recommendation,
                evidence=evidence,
                question=question,
                conversation_context=conversation_context,
            )

        prompt_lines = [
            f"You are a regulatory dossier assistant using local model {self.model_id} route={route}.",
            f"Question: {question}",
            f"Recommendation: {recommendation}",
            f"Conversation context: {conversation_context or 'none'}",
            "Cite each claim with citation_id in brackets.",
            "Evidence:",
        ]
        for ev in evidence[:6]:
            prompt_lines.append(
                f"- {ev['citation_id']} | {ev['section_title']} | snippet={ev['snippet']}"
            )
        prompt = "\n".join(prompt_lines)
        if self.mode == "vllm":
            text = self._vllm_generate(prompt)
        else:
            text = self._docker_generate(prompt)
        return {
            "rationale": text,
            "claims": [{"text": text, "citation_id": evidence[0]["citation_id"] if evidence else ""}],
        }


Gemma4Client = LocalModelClient
