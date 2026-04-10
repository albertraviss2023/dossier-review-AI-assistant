# End-to-End Test Matrix

## 1. Purpose
This matrix defines the mandatory end-to-end workflow coverage for the dossier-review system, especially for antibacterial dossiers that rely on external source retrieval.
The machine-readable companion file is `tests/e2e_workflow_matrix.yaml`.

Testing principle:
- Every production workflow must be executable in three iterations:
  - `mock`: fast local development with mocked external services
  - `snapshot`: deterministic CI run using pinned external-source snapshots or recorded responses
  - `live`: release-validation smoke run against live external sources or officially published source endpoints

## 2. External Source Paths
- WHO AWaRe / eEML: Access/Watch/Reserve source of truth
- WHO GLASS: resistance and use trend context
- RxNorm: ingredient normalization
- PubChem: canonical structure and chemistry lookup
- ChEMBL: chemistry cross-check and supplemental structure context
- UniChem or equivalent identifier reconciliation layer: identifier linking across chemistry sources
- Curated local knowledge wiki: internal operating guidance and retrieval support corpus

## 3. Workflow Matrix

| Workflow ID | Workflow | Mock | Snapshot | Live | Required Result |
|---|---|---|---|---|---|
| E2E-01 | Ingest dossier and detect antibacterial ingredient | Yes | Yes | Yes | ingredient normalized and classified as antibacterial or not applicable |
| E2E-02 | WHO AWaRe lookup for antibiotic in official list | Yes | Yes | Yes | returned AWaRe group matches pinned WHO source |
| E2E-03 | Reserve antibiotic with critical MDR unmet need | Yes | Yes | Yes | `fast_track` plus `restricted_authorization` with WHO-backed evidence |
| E2E-04 | Watch antibiotic with high chemistry similarity and rising GLASS trend | Yes | Yes | Yes | `deep_review` or restricted-authorization escalation with chemistry and GLASS evidence |
| E2E-05 | Access antibiotic without escalation | Yes | Yes | Yes | standard or non-escalated recommendation with cited source evidence |
| E2E-06 | Non-antibacterial dossier | Yes | Yes | Yes | AWaRe logic marked `not_applicable` and no false AMR escalation |
| E2E-07 | Unresolved ingredient normalization | Yes | Yes | Yes | system abstains or flags reviewer intervention; no fabricated mapping |
| E2E-08 | WHO AWaRe source unavailable | Yes | Yes | Yes | fallback to pinned snapshot or abstain according to configuration |
| E2E-09 | GLASS source unavailable or stale | Yes | Yes | Yes | cached snapshot used if valid; otherwise stewardship decision degrades safely |
| E2E-10 | PubChem or ChEMBL timeout / rate limit | Yes | Yes | Yes | retry and fallback policy exercised; no silent chemistry omission |
| E2E-11 | Source disagreement between chemistry sources | Yes | Yes | Yes | discrepancy logged, surfaced, and recommendation abstains or downgrades confidence |
| E2E-12 | Full reviewer-facing rationale and audit trace | Yes | Yes | Yes | rationale includes dossier evidence, external evidence, versions, and source provenance |
| E2E-13 | Knowledge wiki search and citation rendering | Yes | Yes | Yes | wiki pages are searchable with page-tag metadata and section citations |
| E2E-14 | Multi-hop question spanning dossier evidence and knowledge wiki guidance | Yes | Yes | Yes | query decomposition executes and synthesis returns both dossier and wiki evidence |
| E2E-15 | UI or API model switch across Gemma E4B, Gemma E2B, and Qwen 3.5 | Yes | Yes | Yes | selected model is honored, returned in the response, and recorded in audit lineage |
| E2E-16 | Context-window monitor and 98% auto-compaction | Yes | Yes | Yes | usage is surfaced to the reviewer and oversized threads compact before the next turn |
| E2E-17 | New chat linked to previous chat with carryover summary | Yes | Yes | Yes | predecessor thread is summarized and the successor thread starts with linked carryover context |

## 4. Assertions Per Test
- Recommendation class is correct for the workflow scenario.
- External evidence is cited with source name, source version, and retrieval timestamp or snapshot version.
- Ingredient normalization path is traceable from dossier text to final chemistry identifier.
- Failures in external sources do not produce silent fallback to model-only inference.
- Audit record contains the external-source retrieval status and any fallback mode used.
- When wiki evidence is used, page IDs and section IDs remain distinguishable from dossier citations.
- Selected model ID and runtime alias are recorded for every review workflow.
- Context monitor values and compaction events are recorded when conversation continuity is enabled.

## 5. Release Policy
- `mock` mode must pass in every pull request that touches policy, retrieval, or source adapters.
- `snapshot` mode must pass in CI before merge to main.
- `live` mode must pass for every release candidate touching antibacterial policy, retrieval ranking, source adapters, cache logic, or source normalization.
- A release is blocked if any workflow marked `Yes` in the live column fails for production-critical source paths.
