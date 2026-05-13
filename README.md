# dossier-review-AI-assistant

Policy-focused regulatory review workstation for pre-market authorization dossiers, with local-first privacy controls and a real MCP tool layer.

## Structure
- `docs/` requirements, architecture diagrams, implementation plan, acceptance criteria
- `regulatory_mcp_server/` real MCP server, tool contracts, fixtures, and MCP-specific tests
- `synthetic_data/` synthetic dossier generator, gold-set adjudication, split tooling
- `state/` handoff context for cross-laptop continuation

## Model Policy
- Switchable local profiles: Gemma E4B, Gemma E2B, and Gemma 26B.
- Optional local vLLM path is supported through environment configuration; Hugging Face tokens must be injected through environment variables and never committed.
- Development host can be Asus (current), while release memory envelopes target a 32 GB Zenbook profile.
- Public demo profile is supported via Gemini API without changing feature logic (`DOSSIER_MODEL_PROVIDER=gemini`).

## API Contracts
- Current API surface is documented in `docs/api-contracts.md`.

## Quick Start
```powershell
python dossier-review-AI-assistant/synthetic_data/generate_dossiers.py --help
python dossier-review-AI-assistant/synthetic_data/create_gold_set.py --help
python dossier-review-AI-assistant/synthetic_data/create_splits.py --help
```

Run the local API:
```powershell
python -m uvicorn dossier_review_ai_assistant.api:app --reload --app-dir src
```

Run the real Regulatory MCP server:
```powershell
python -m regulatory_mcp_server.server
```

Optional vLLM runtime setup:
```powershell
$env:HF_TOKEN="<your_hf_token>"
$env:DOSSIER_MODEL_MODE="vllm"
$env:DOSSIER_VLLM_BASE_URL="http://127.0.0.1:8001/v1/chat/completions"
```

Local infra stack (Postgres/pgvector, Redis, MinIO, MLflow):
```powershell
docker compose -f docker-compose.local.yml up -d
```

Run offline evaluation harness:
```powershell
python -m evaluation.run_evaluation --max-records 120
```

Run local gates:
```powershell
python -m evaluation.run_evaluation --max-records 120 --output state/eval/final_report.json
python scripts/check_eval_gate.py state/eval/final_report.json --acceptance docs/acceptance-criteria.yaml
python scripts/security_gate.py
python scripts/retention_compliance.py --retention-days 30 --output state/audit/retention_report.json
```

## Public Demo Profile

This repository supports one codebase with runtime switching:

- local profile: `DOSSIER_MODEL_PROVIDER=local`
- public demo profile: `DOSSIER_MODEL_PROVIDER=gemini`

Use `.env.demo.example` as a template for the public profile.
Deployment details are in `docs/public-demo-deployment.md`.

Run MCP validation:
```powershell
python -m pytest regulatory_mcp_server/tests -q
python scripts/test_mcp_end_to_end.py
python scripts/run_mcp_realistic_simulations.py
```

## Regulatory MCP

The application now uses a real MCP tool layer for structured review workflows. The server exposes independently callable JSON tools for:

- vector search
- reranking
- correct/incorrect section comparison
- WHO INN similarity
- AWaRe / Reserve stewardship review
- innovator patient-information lookup and generic comparison
- evidence packet construction
- findings-table generation

See [regulatory_mcp_server/README.md](/D:/projects/ai%20dossier%20assistant/regulatory_mcp_server/README.md) and [regulatory-mcp-server.md](/D:/projects/ai%20dossier%20assistant/docs/regulatory-mcp-server.md).

## Current Dataset Snapshot
- Raw (active): `synthetic_data/data/raw/balanced_v1_2026-04-05` (1475 dossiers)
- Raw (original): `synthetic_data/data/raw/v1_2026-04-03` (1200 dossiers)
- Gold: `synthetic_data/data/gold/strict_v1_2026-04-03` (300 dossiers)
- Splits (active): `synthetic_data/data/splits/balanced_v1_2026-04-05` (1034/223/218)
- Splits (original): `synthetic_data/data/splits/v1_2026-04-03` (838/183/179)

## Session Continuation (Token-Saving)
1. Open `state/HANDOFF_STATE.md`
2. Open `state/project_state.json`
3. Continue implementation from `docs/implementation-plan.md` Day 4-7

## Conversation Continuity
- New review chats default to a `4096` token context window.
- The UI shows live context usage and auto-compacts at `98%` of the configured window.
- New chats can link to previous chats, carrying forward a compressed summary instead of the raw full transcript.

## Push and Fetch Workflow
From this folder:
```powershell
cd dossier-review-AI-assistant
git init
git add .
git commit -m "Initial scaffold: data, docs, and state handoff"
git branch -M main
git remote add origin <YOUR_REMOTE_URL>
git push -u origin main
```

On NVIDIA laptop:
```powershell
git clone <YOUR_REMOTE_URL>
cd dossier-review-AI-assistant
```
