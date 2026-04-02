# Dossier Review AI Assistant - Handoff State

Last updated: 2026-04-03 (Africa/Kampala)

## Repository Identity
- Repo folder name: `dossier-review-AI-assistant`
- Intended remote repo name: `dossier-review-AI-assistant`
- Project root path: `c:\Users\alber\OneDrive\Data Engineering\Projects\MlOps\dossier-review-AI-assistant`

## What Is Already Done
- Requirements, architecture diagrams, and implementation plan are complete under `docs/`.
- Synthetic dossier pipeline is complete and cleaned for PDF-first generation.
- Strict machine-adjudicated gold set is available (Label Studio replacement for current phase).
- Stratified train/val/test split artifacts are available.
- Script path defaults were updated to `dossier-review-AI-assistant/...`.

## Current Data Assets (Versioned)
- Raw dataset: `synthetic_data/data/raw/v1_2026-04-03`
  - `num_dossiers`: 1200
  - Files: `dossiers.jsonl`, `section_labels.csv`, `holistic_labels.csv`, `dossiers_pdf/`, `manifest.json`
- Gold set: `synthetic_data/data/gold/strict_v1_2026-04-03`
  - `num_records`: 300
  - `adjudication_profile`: strict
  - `override_rate`: 0.20
- Splits: `synthetic_data/data/splits/v1_2026-04-03`
  - `train`: 838
  - `val`: 181
  - `test`: 181

## Key Docs
- `docs/requirements-spec.md`
- `docs/implementation-plan.md`
- `docs/architecture-diagrams.md`
- `docs/acceptance-criteria.yaml`

## Recommended Local Inference Stack (32 GB RAM / 8 GB VRAM)
- Primary generator: `ai/gemma4:4B-Q4_K_XL`
- Embeddings: `ai/qwen3-embedding:4B`
- Reranker: `ai/qwen3-reranker:0.6B`
- Optional tool/structured helper: `ai/functiongemma:Q4_K_XL-270M`
- Routing: quantized default route + streamed/offloaded fallback route for hard/long-context requests.

## Immediate Next Steps
1. Start Docker Desktop and validate `docker model` runtime.
2. Stand up inference services and retrieval store (local-only, no external egress).
3. Implement evaluator harness against acceptance criteria.
4. Build API + web UI flow: user -> policy API -> RAG -> inference -> auditable decision.
5. Add CI gates for metrics, security scans, and reproducibility.

## Resume Prompt (Token-Saving)
Use this prompt in a new session:
"Continue `dossier-review-AI-assistant` from `state/HANDOFF_STATE.md`. Do not regenerate data unless requested. Start by validating Docker model runtime and implementing the local inference + retrieval service layer per docs/implementation-plan.md Day 4-6."
