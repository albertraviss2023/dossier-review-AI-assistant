# API Contracts (Current Implementation)

## Base
- Local FastAPI app (default): `http://127.0.0.1:8000`

## Endpoints
- `GET /health`
  - Response:
    - `status`
    - `dossiers_loaded`
    - `sections_indexed`
    - `system_total_ram_gb`
    - `system_available_ram_gb`
    - `process_rss_gb`
    - `model_policy`

- `GET /v1/dossiers/{dossier_id}`
  - Returns dossier metadata and policy labels.

- `POST /v1/retrieval/search`
  - Request:
    - `query` (string, required)
    - `dossier_id` (string, optional)
    - `top_k` (int, optional)
  - Response:
    - `query`
    - `total_hits`
    - `citations[]` (citation_id, section metadata, score, snippet)

- `POST /v1/review`
  - Request:
    - `dossier_id` (string, required)
    - `question` (string, optional)
    - `top_k` (int, optional)
    - `force_fallback` (bool, optional)
  - Response:
    - `recommendation`
    - `confidence`
    - `route` (`standard` or `fallback`)
    - `abstained` + `abstain_reason`
    - `rationale`
    - `policy_rule_hits[]`
    - `section_diagnostics[]`
    - `citations[]`
    - `verifier` (groundedness summary)
    - `memory` (current process/system RAM snapshot + budget limits)
    - `lineage_tags` (data/model/prompt lineage metadata)

## Model Policy
- Runtime route is Gemma 4 only (see `docs/model-policy.md`).
