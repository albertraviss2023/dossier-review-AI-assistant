# dossier-review-AI-assistant

Policy-focused MLOps project for regulatory dossier review with local-first privacy controls.

## Structure
- `docs/` requirements, architecture diagrams, implementation plan, acceptance criteria
- `synthetic_data/` synthetic dossier generator, gold-set adjudication, split tooling
- `state/` handoff context for cross-laptop continuation

## Quick Start
```powershell
python dossier-review-AI-assistant/synthetic_data/generate_dossiers.py --help
python dossier-review-AI-assistant/synthetic_data/create_gold_set.py --help
python dossier-review-AI-assistant/synthetic_data/create_splits.py --help
```

## Current Dataset Snapshot
- Raw: `synthetic_data/data/raw/v1_2026-04-03` (1200 dossiers)
- Gold: `synthetic_data/data/gold/strict_v1_2026-04-03` (300 dossiers)
- Splits: `synthetic_data/data/splits/v1_2026-04-03` (838/181/181)

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
