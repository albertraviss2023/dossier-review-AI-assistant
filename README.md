# dossier-review-AI-assistant

Policy-focused MLOps project for regulatory dossier review with local-first privacy controls.

## Structure
- `docs/` requirements, architecture diagrams, implementation plan, acceptance criteria
- `synthetic_data/` synthetic dossier generator, gold-set adjudication, split tooling
- `state/` handoff context for cross-laptop continuation

## Model Policy
- Gemma 4 only. See `docs/model-policy.md`.
- Development host can be Asus (current), while release memory envelopes target a 32 GB Zenbook profile.

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

## Current Dataset Snapshot
- Raw (active): `synthetic_data/data/raw/balanced_v1_2026-04-05` (1471 dossiers)
- Raw (original): `synthetic_data/data/raw/v1_2026-04-03` (1200 dossiers)
- Gold: `synthetic_data/data/gold/strict_v1_2026-04-03` (300 dossiers)
- Splits (active): `synthetic_data/data/splits/balanced_v1_2026-04-05` (1030/222/219)
- Splits (original): `synthetic_data/data/splits/v1_2026-04-03` (838/181/181)

## Session Continuation (Token-Saving)
1. Open `state/HANDOFF_STATE.md`
2. Open `state/project_state.json`
3. Continue implementation from `docs/implementation-plan.md` Day 4-7

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
