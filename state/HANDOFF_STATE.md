# Dossier Review AI Assistant - Handoff State

Last updated: 2026-04-05 (Africa/Kampala)

## Repository Identity
- Repo folder name: `dossier-review-AI-assistant`
- Intended remote repo name: `dossier-review-AI-assistant`
- Project root path: `c:\Users\alber\OneDrive\Data Engineering\Projects\MlOps\dossier-review-AI-assistant`
- Active development host: ASUS laptop (current)
- Target validation host: ASUS Zenbook (32 GB RAM)

## What Is Already Done
- Requirements, architecture diagrams, and implementation plan are complete under `docs/`.
- Synthetic dossier pipeline is complete and cleaned for PDF-first generation.
- Strict machine-adjudicated gold set is available (Label Studio replacement for current phase).
- Balanced class-augmentation dataset is generated for holistic class rebalance.
- Stratified train/val/test split artifacts are available for both original and balanced datasets.
- Script path defaults were updated to `dossier-review-AI-assistant/...`.
- FastAPI foundation API + retrieval service + UI shell are implemented.
- Gemma-4-only review orchestration endpoint with routing and verification gates is implemented.
- Evaluation harness and CI/security gate scripts are implemented.
- Memory governance telemetry and guardrails are implemented (RAM snapshot + memory-pressure abstain guard).
- Lineage tags are attached to review/retrieval audit events.
- Retention compliance tooling is implemented (`scripts/retention_compliance.py`).

## Current Data Assets (Versioned)
- Raw dataset (active): `synthetic_data/data/raw/balanced_v1_2026-04-05`
  - `num_dossiers`: 1471
  - Files: `dossiers.jsonl`, `section_labels.csv`, `holistic_labels.csv`, `manifest.json`
- Raw dataset (original): `synthetic_data/data/raw/v1_2026-04-03`
  - `num_dossiers`: 1200
- Gold set: `synthetic_data/data/gold/strict_v1_2026-04-03`
  - `num_records`: 300
  - `adjudication_profile`: strict
  - `override_rate`: 0.20
- Splits (active): `synthetic_data/data/splits/balanced_v1_2026-04-05`
  - `train`: 1030
  - `val`: 222
  - `test`: 219

## Key Docs
- `docs/requirements-spec.md`
- `docs/implementation-plan.md`
- `docs/architecture-diagrams.md`
- `docs/acceptance-criteria.yaml`

## Recommended Local Inference Stack (32 GB RAM / 8 GB VRAM)
- Primary generator: `ai/gemma4:4B-Q4_K_XL`
- Embeddings: `ai/gemma4:4B-Q4_K_XL` (same model family for Gemma 4 only policy)
- Reranker: `ai/gemma4:4B-Q4_K_XL` (same model family for Gemma 4 only policy)
- Optional tool/structured helper: `ai/gemma4:4B-Q4_K_XL`
- Routing: quantized default route + streamed/offloaded fallback route for hard/long-context requests.

## Immediate Next Steps
1. On current ASUS dev host: validate `docker model` Gemma 4 execution path in non-mock mode.
2. On Zenbook 32 GB host: run memory envelope validation (`zenbook_*_peak_rss_gb`, `oom_kill_events_2h`).
3. Upgrade retrieval path from lexical-only to hybrid BM25 + pgvector.
4. Replace weak-label baseline with trained section and holistic models.
5. Add observability dashboards and signed audit record checks.
6. Run full CI on GitHub Actions and verify release gates.

## Governance/Continuity Commands
```powershell
python -m pytest
python -m evaluation.run_evaluation --max-records 120 --output state/eval/final_report.json
python scripts/check_eval_gate.py state/eval/final_report.json --acceptance docs/acceptance-criteria.yaml
python scripts/security_gate.py
python scripts/retention_compliance.py --retention-days 30 --output state/audit/retention_report.json
```

## Resume Prompt (Token-Saving)
Use this prompt in a new session:
"Continue `dossier-review-AI-assistant` from `state/HANDOFF_STATE.md`. Do not regenerate data unless requested. Start by validating Docker model runtime and implementing the local inference + retrieval service layer per docs/implementation-plan.md Day 4-6."
"Continue `dossier-review-AI-assistant` from `state/HANDOFF_STATE.md`. Use balanced dataset assets under `synthetic_data/data/raw/balanced_v1_2026-04-05` and splits under `synthetic_data/data/splits/balanced_v1_2026-04-05`. Validate Docker Gemma4 runtime in non-mock mode, then implement hybrid retrieval (BM25 + pgvector)."
