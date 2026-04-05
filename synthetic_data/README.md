# Synthetic Dossier Data Generator (Dossier Review AI Assistant)

This folder contains a Python generator that creates CTD-aligned synthetic dossiers for the
Regulatory Dossier Policy Copilot.

## What it generates
- `dossiers_pdf/`: one PDF dossier per record (default)
- `dossiers.jsonl`: canonical record per dossier (sections + labels + policy signals)
- `section_labels.csv`: section-level training labels
- `holistic_labels.csv`: policy-level labels and key risk signals
- `manifest.json`: dataset summary and defect distribution
- `dossiers_txt/` (optional): text exports for parser and retrieval testing

## Core failure modes covered
- INN infringement risk (`inn_infringement`)
- Missing pivotal clinical data (`clinical_missing`)
- Failed pivotal endpoint (`clinical_failed`)
- GMP non-compliance (`gmp_non_compliant`)
- GMP evidence outdated (`gmp_outdated`)
- GMP certificate expired (`gmp_certificate_expired`)
- Missing section (`missing_section` / `missing_critical_section`)
- Section too short (`insufficient_detail`)

## Realism and consistency controls
- Defect generation uses conditional logic to prevent incompatible combinations (for example, `clinical_missing` and `clinical_failed` cannot appear together).
- Section mutations for policy defects are kept within section length bounds unless the defect is explicitly about missing/short content.
- Internal validation rejects contradictory dossier states and regenerates records automatically.

## Source vocabulary breadth
- Manufacturers: 24 synthetic manufacturer entities across the target operating context.
- Drug naming: expanded INN pool using WHO-INN-aligned generic naming conventions for broad coverage.

## Usage
```powershell
python dossier-review-AI-assistant/synthetic_data/generate_dossiers.py \
  --num-dossiers 1200 \
  --compliant-rate 0.35 \
  --seed 20260402 \
  --output-dir dossier-review-AI-assistant/synthetic_data/output
```

Optional flags:
- `--emit-section-text` to also write plain text copies
- `--no-emit-pdf` to disable PDF output (not recommended for this project)

## Machine-adjudicated gold set (Label Studio replacement for this phase)
You can create a reviewer-style gold set directly from generated dossiers:

```powershell
python dossier-review-AI-assistant/synthetic_data/create_gold_set.py \
  --input-jsonl dossier-review-AI-assistant/synthetic_data/output/dossiers.jsonl \
  --output-dir dossier-review-AI-assistant/synthetic_data/gold_set \
  --sample-size 240 \
  --seed 20260402
```

Strict reviewer profile:

```powershell
python dossier-review-AI-assistant/synthetic_data/create_gold_set.py \
  --input-jsonl dossier-review-AI-assistant/synthetic_data/output/dossiers.jsonl \
  --output-dir dossier-review-AI-assistant/synthetic_data/gold_set_strict \
  --sample-size 240 \
  --seed 20260402 \
  --adjudication-profile strict
```

This produces:
- `gold_set.jsonl`
- `gold_holistic_labels.csv`
- `gold_section_labels.csv`
- `gold_manifest.json`

Note: this is a **machine-adjudicated** proxy for human labeling. It is suitable for rapid development
and CI quality gates, but a smaller expert-reviewed set is still recommended before final production release.

## Train/Validation/Test splits
```powershell
python dossier-review-AI-assistant/synthetic_data/create_splits.py \
  --input-jsonl dossier-review-AI-assistant/synthetic_data/data/raw/v1_2026-04-03/dossiers.jsonl \
  --output-dir dossier-review-AI-assistant/synthetic_data/data/splits/v1_2026-04-03 \
  --seed 20260403 \
  --train-ratio 0.70 \
  --val-ratio 0.15 \
  --test-ratio 0.15
```

## Class rebalance augmentation (holistic labels)
Use this when `standard_review` and `deep_review` are underrepresented:
```powershell
python dossier-review-AI-assistant/synthetic_data/rebalance_holistic_classes.py \
  --input-jsonl dossier-review-AI-assistant/synthetic_data/data/raw/v1_2026-04-03/dossiers.jsonl \
  --output-dir dossier-review-AI-assistant/synthetic_data/data/raw/balanced_v1_2026-04-05 \
  --min-class-count 180 \
  --seed 20260405
```

Then regenerate splits on the balanced dataset:
```powershell
python dossier-review-AI-assistant/synthetic_data/create_splits.py \
  --input-jsonl dossier-review-AI-assistant/synthetic_data/data/raw/balanced_v1_2026-04-05/dossiers.jsonl \
  --output-dir dossier-review-AI-assistant/synthetic_data/data/splits/balanced_v1_2026-04-05 \
  --seed 20260405
```

## Recommended strategy: PDF-first with canonical labels
Because real submissions are PDF-based, this generator is PDF-first by default.
Use a dual representation approach:
1. **Production-mimic artifacts**: `dossiers_pdf/` for parser/RAG/OCR evaluation.
2. **Canonical training source**: `dossiers.jsonl` + labels for deterministic model training and audit.

## Label taxonomy
Section labels:
- presence: `present` | `missing`
- length_status: `length_ok` | `too_short` | `too_long` | `missing`
- correctness: `correct` | `partial` | `incorrect`

Policy signals:
- `inn_infringement`
- `gmp_inspection_status`
- `gmp_inspection_recent`
- `gmp_certificate_validity`
- `clinical_data_available`
- `pivotal_trial_outcome`

Holistic policy decision:
- `fast_track`
- `standard_review`
- `deep_review`
- `reject_and_return`

## Country scope
Synthetic dossiers are generated across:
- Tanzania
- Burkina Faso
- Uganda
- Botswana

## Notes
- This dataset is synthetic and safe for development.
- Tune `--compliant-rate` and defect weights in script to rebalance class distribution.
- Keep a human-reviewed subset for final validation and calibration.
