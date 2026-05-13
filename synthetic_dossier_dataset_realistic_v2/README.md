# Synthetic Dossier Dataset

This dataset is generated for regulatory LLM+vision+RAG benchmarking.

## Run
```powershell
python synthetic_data/generate_dataset.py --config synthetic_data/dataset_config.yaml --num-dossiers 192 --output synthetic_dossier_dataset
```

Smoke:
```powershell
python synthetic_data/generate_dataset.py --config synthetic_data/dataset_config.yaml --num-dossiers 16 --output synthetic_dossier_dataset_smoke
```

## Label interpretation
- `dossier_labels.jsonl`: dossier-level benchmark targets and expected SOP outcomes.
- `section_labels.jsonl`: module/section quality + SOP pass/query expectations.
- `chunk_labels.jsonl`: chunk-level text type and expected LLM action.
- `issue_labels.jsonl`: controlled known-query failure records.
