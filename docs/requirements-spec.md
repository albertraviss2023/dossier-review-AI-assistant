# Dossier Review AI Assistant Requirements Specification

## 1. Document Control
- Project: Regulatory Dossier Policy Copilot (Agentic RAG, Local-First)
- Version: 1.5
- Status: Draft for build execution
- Owner: Data Science / MLOps
- Last Updated: 2026-04-10

## 2. Policy Problem, Decision, and Business Impact
### 2.1 Problem Statement
Regulatory dossier review is slow and inconsistent. Reviewers face high cognitive load, fragmented evidence, and risk of unsupported LLM responses that are not grounded in institutional documents.

### 2.2 Core Policy Decision Supported
The system recommends one of:
- `fast_track`
- `standard_review`
- `deep_review`
- `reject_and_return`

It also generates section-level compliance and correctness diagnostics to justify the recommendation.
For antibacterial dossiers, the system must also distinguish review speed from stewardship friction by allowing
accelerated review for `Reserve` antibiotics that address critical MDR unmet need while still attaching
restricted-authorization controls where AMR stewardship requires them.

### 2.3 Business Impact
- Reduce dossier review turnaround time and backlog.
- Improve consistency and defensibility of review outcomes.
- Lower rework caused by incomplete/incorrect submissions.
- Increase trust through evidence-linked recommendations and full auditability.

## 3. Scope
### 3.1 In Scope
- Reviewer web UI for dossier upload, section diagnostics, and recommendation display.
- Policy API service for orchestration, policy rules, model routing, and auditing.
- Agentic RAG with retrieval, validation, and evidence-grounded synthesis.
- Curated local knowledge wiki for policy playbooks, source-of-truth guidance, and retrieval support.
- Section-level and holistic dossier correctness scoring.
- Local inference optimization using quantized models plus streamed-weight fallback path.
- CI/CD, observability, and security/privacy controls for local deployment.

### 3.2 Out of Scope (v1)
- Full cloud production deployment.
- Fully autonomous final regulatory decisions without human review.
- Broad multilingual expansion beyond pilot language setup.

## 4. Stakeholders and User Roles
- Reviewer: runs assessments, inspects evidence, and records actions.
- Lead Reviewer: confirms/overrides recommendations and tracks quality.
- System Admin: manages access, thresholds, runtime config, and releases.
- QA/Policy Analyst: validates performance and governance compliance.

## 5. Functional Requirements
- FR-01: Ingest dossier files and parse required sections.
- FR-02: Validate section presence and expected length ranges.
- FR-03: Score section correctness (`correct`, `partial`, `incorrect`).
- FR-04: Produce holistic dossier policy recommendation.
- FR-05: Enforce citation-grounded outputs for major claims.
- FR-06: Abstain/escalate on low evidence confidence.
- FR-07: Support reviewer override with structured reason codes.
- FR-08: Persist immutable audit traces for all recommendations.
- FR-09: Provide monitoring dashboard for quality, latency, and drift.
- FR-10: Operate fully local for sensitive dossier workflows.
- FR-11: Extract and validate GMP evidence per manufacturing site (certificate status, inspection status, validity window).
- FR-12: Extract and classify pivotal clinical trial outcomes (primary endpoint met/not met/inconclusive) from clinical sections.
- FR-13: Detect antibacterial submissions subject to AMR stewardship review and classify WHO AWaRe category (`Access`, `Watch`, `Reserve`, or `not_applicable`).
- FR-14: Identify Reserve-category antibiotics that address critical MDR unmet need and support accelerated review while preserving stewardship controls.
- FR-15: Detect high similarity to existing Watch antibiotics plus rising GLASS resistance trends and flag those dossiers for restricted authorization and deeper review.
- FR-16: The system shall use the official WHO AWaRe classification as the sole source of truth for Access/Watch/Reserve assignment; synthetic or hand-curated substitute lists are not permitted for production retrieval or policy execution.
- FR-17: The system shall maintain versioned source snapshots, provenance, and checksum metadata for every external reference dataset used in antibacterial policy logic.
- FR-18: Ingredient normalization shall use a standards-based drug vocabulary before chemistry comparison so that salts, esters, hydrates, and brand-name variants resolve to the intended active moiety.
- FR-19: Chemical similarity comparison for antibacterial dossiers shall be based on real structure data retrieved from authoritative chemistry sources and not on free-text name similarity alone.
- FR-20: The system shall expose source-backed evidence for AWaRe category assignment, GLASS trend retrieval, ingredient normalization, and chemistry comparison in the audit trace and reviewer rationale.
- FR-21: Every end-to-end workflow shall have an executable test path across mocked, recorded-snapshot, and live-external-source modes before a release can be promoted.
- FR-22: The system shall maintain a curated local knowledge wiki that captures policy playbooks, retrieval guidance, source precedence rules, and reviewer-facing operating notes as a first-class retrievable corpus.
- FR-23: The reviewer UI shall support explicit selection among approved local model profiles, including Gemma E4B, Gemma E2B, and Qwen 3.5, and the chosen model shall be recorded in the response and audit trace.
- FR-24: Complex multi-hop review questions shall be decomposed into sub-queries that can independently target dossier evidence, the curated knowledge wiki, and external-source evidence before final synthesis.
- FR-25: The system shall maintain explicit review conversations with thread IDs, message history, and adjustable context-window limits so reviewers can continue a dossier discussion across multiple turns.
- FR-26: The reviewer UI shall display a live context-window monitor and automatically compact conversation state when estimated context usage reaches 98% of the configured window.
- FR-27: Auto-compaction shall preserve continuity by storing low-cost rolling summaries of prior turns and using those summaries as model context in subsequent review turns.
- FR-28: Starting a new chat shall support linking to a previous selectable chat; the linked predecessor shall be summarized automatically and the carryover summary shall seed the new chat at lower token cost.
- FR-29: Conversation state orchestration shall be modeled as a LangGraph-compatible state flow so context hydration, compaction, and carryover rules remain explicit and testable.

## 6. Non-Functional Requirements
- NFR-01: Privacy by default (no external inference for restricted data).
- NFR-02: Reproducibility (versioned data, prompts, configs, models).
- NFR-03: Reliability with graceful fallback across inference strategies.
- NFR-04: Security with RBAC, least privilege, and encrypted storage.
- NFR-05: Performance within laptop constraints (8GB VRAM GPU).
- NFR-06: CI quality gates must block unsafe/low-quality releases.
- NFR-07: Data governance controls must be enforced for classification, lineage, retention, and deletion.
- NFR-08: Local RAG indexes must preserve data-domain isolation (synthetic vs restricted data).
- NFR-09: Memory-aware execution must support a 32 GB RAM laptop profile (Asus Zenbook class host).
- NFR-10: Zero out-of-policy data egress events are permitted for restricted dossiers.
- NFR-11: Retrieval quality for antibacterial policy decisions takes priority over model complexity; if required source evidence cannot be retrieved, normalized, and reconciled, the system must abstain or degrade gracefully rather than infer from incomplete data.
- NFR-12: External reference ingestion must support snapshot pinning, cache validation, and deterministic replay for offline evaluation and incident review.
- NFR-13: The local knowledge wiki must be versioned, reviewable, and citation-addressable by page and section so the system can distinguish curated internal guidance from dossier evidence and external source-of-truth evidence.
- NFR-14: Context-window monitoring shall be approximate-token aware, visible to the reviewer, and accurate enough to trigger compaction before the configured limit is breached.
- NFR-15: Secrets for vLLM or model downloads, including Hugging Face access tokens, shall be injected only through environment variables or secret stores and must never be committed to the repository or written to audit logs.

## 7. Data Requirements
### 7.1 Dossier Schema Requirements
Each dossier instance shall contain:
- dossier_id
- jurisdiction
- submission_date
- required sections (structured)
- section text content
- section metadata (length, language, type)
- expected section constraints (min_len, max_len, criticality)
- antibacterial stewardship metadata where applicable (WHO AWaRe category, MDR unmet-need signal, GLASS resistance trend, similarity-to-Watch comparator, and authorization-control recommendation)

### 7.2 Standard Submission Dossier Section Set (CTD-Aligned)
The synthetic and evaluation datasets shall follow a CTD-style structure. Module 1 is region-specific; Modules 2-5 are common.

Module 1 (Administrative / Regional):
- Application form and cover letter
- Applicant and MAH details
- Manufacturing authorizations
- GMP certificates and latest inspection outcomes for API/FPP sites
- Product information (SmPC/PI/PIL/labeling)
- Regulatory status and commitments

Module 2 (Summaries):
- Quality Overall Summary (QOS)
- Nonclinical overview/summary
- Clinical overview/summary

Module 3 (Quality / CMC):
- API manufacturing and controls
- FPP manufacturing process and controls
- Specifications and analytical validation
- Stability data and shelf-life justification

Module 4 (Nonclinical):
- Pharmacology, pharmacokinetics, toxicology reports (where applicable)

Module 5 (Clinical):
- Tabular listing of clinical studies
- Clinical study reports (efficacy/safety)
- Biopharmaceutics / bioequivalence (where applicable)
- Statistical and endpoint result narratives for pivotal studies

For antibacterial submissions, the dossier shall also include evidence statements in the clinical and product-information
sections covering:
- WHO AWaRe category and intended place in therapy
- MDR or last-resort unmet-need justification where relevant
- similarity to existing Watch antibiotics or comparator class
- GLASS resistance-trend context
- proposed stewardship restrictions or restricted-authorization controls

### 7.3 Synthetic Data Representation Strategy (Canonical Text + Rendered PDF)
Use dual-format synthetic generation:
- Canonical source format: structured JSON/JSONL with section boundaries, labels, and evidence anchors.
- Rendered format: realistic CTD-like PDFs generated from canonical source to test ingestion/OCR/chunking.

Why dual format:
- JSON/JSONL gives deterministic training labels and easy rule generation.
- PDF gives realistic production behavior for parsing and retrieval failure modes.

Training/evaluation policy:
- Train validators/classifiers using canonical text and metadata.
- Evaluate end-to-end pipeline on rendered PDFs plus text-native cases.

### 7.4 Synthetic Data Strategy
Synthetic data will represent realistic dossier patterns and failure modes.
- MVP: 500 dossiers
- Recommended: 1,200 dossiers
- Interview-grade: 1,800 dossiers

### 7.5 Labeling Strategy
Section-level labels:
- presence: `present` | `missing`
- length: `length_ok` | `too_short` | `too_long`
- correctness: `correct` | `partial` | `incorrect`

Holistic labels:
- `fast_track`
- `standard_review`
- `deep_review`
- `reject_and_return`

Specialized policy labels:
- `gmp_inspection_status`: `compliant` | `non_compliant` | `expired` | `missing_evidence`
- `gmp_certificate_validity`: `valid` | `expired` | `not_provided`
- `pivotal_trial_outcome`: `endpoint_met` | `endpoint_not_met` | `inconclusive` | `missing_evidence`
- `aware_category`: `access` | `watch` | `reserve` | `not_applicable`
- `amr_unmet_need`: `routine` | `moderate` | `high` | `critical` | `not_applicable`
- `glass_resistance_trend`: `rising` | `stable` | `declining` | `not_applicable`
- `similarity_to_existing_watch`: `low` | `moderate` | `high` | `not_applicable`
- `authorization_control`: `standard_authorization` | `restricted_authorization`

Labeling method:
- Weak labels from generator metadata + deterministic rules.
- Strict machine adjudication on a 20-25% gold subset with higher evidence thresholds.
- Optional later human review only if calibration gaps remain after offline validation.

### 7.6 External Source-of-Truth Requirements for Antibacterial Policy
For antibacterial dossiers, synthetic metadata may be used only for development scaffolding. The production retrieval and policy path shall be grounded in real external sources with explicit source precedence.

Mandatory source stack:
- WHO AWaRe classification of antibiotics for evaluation and monitoring of use: normative source of truth for Access/Watch/Reserve grouping.
- WHO Essential Medicines / eEML antibiotic entries: product and medicine-list cross-check for WHO naming and stewardship context.
- WHO GLASS indicators and surveillance exports: source of resistance and antimicrobial-use trend context used in Watch/Reserve risk decisions.
- RxNorm API: primary normalization layer for ingredient names, synonyms, branded names, and ingredient-level concept resolution.
- PubChem PUG-REST: primary chemistry source for canonical SMILES, InChI, InChIKey, molecular formula, parent compound normalization, and similarity or substructure comparisons.
- ChEMBL web services: secondary chemistry source for structure cross-checking, mechanism/class context, and supplemental similarity validation.
- UniChem identifier mapping: identifier reconciliation layer between chemistry databases when PubChem, ChEMBL, or other identifiers need to be linked reliably.

Reference endpoints and publications to pin:
- WHO AWaRe classification publication: `https://www.who.int/publications/i/item/WHO-MHP-HPS-EML-2023.04`
- WHO GLASS data portal: `https://apps.who.int/gho/data/node.main.AMRGLASS?lang=en`
- RxNorm API overview: `https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html`
- PubChem PUG-REST specification: `https://pubchem.ncbi.nlm.nih.gov/pug_rest/PUG_REST.html`
- ChEMBL web services overview: `https://chembl.gitbook.io/chembl-interface-documentation/web-services`
- ChEMBL data API docs: `https://www.ebi.ac.uk/chembl/api/data/docs`
- ChEMBL chemistry utils docs: `https://www.ebi.ac.uk/chembl/api/utils/docs`
- UniChem API docs: `https://www.ebi.ac.uk/unichem/api/docs`

Source precedence rules:
- AWaRe group assignment must come from WHO data, not from PubChem, ChEMBL, RxNorm, or locally inferred heuristics.
- GLASS trend signals must come from WHO GLASS data, not from synthetic metadata when operating in real-source mode.
- Chemistry identifiers must be normalized through RxNorm plus identifier reconciliation before similarity scoring is computed.
- When sources disagree, WHO remains authoritative for AWaRe class, while chemistry comparison shall record the disagreement and abstain if normalization cannot be resolved confidently.

### 7.7 Chemical Comparison Requirements for Watch vs Reserve Analysis
The system shall compare antibacterial active ingredients at the active-moiety level, not formulation excipients or free-text labels.

Chemical comparison workflow:
1. Normalize dossier ingredient names to ingredient concepts and active moieties.
2. Map the normalized ingredient to authoritative chemistry identifiers.
3. Retrieve canonical structure representations and parent-compound relationships.
4. Compute structure-based similarity and class-level comparison against the relevant WHO AWaRe cohorts.
5. Join the chemistry result with WHO AWaRe group membership and GLASS trend context before any policy recommendation is made.

Required chemical comparison fields:
- normalized ingredient name
- active moiety or parent compound
- RxNorm concept identifier when available
- PubChem CID and canonical SMILES
- InChI and InChIKey
- ChEMBL identifier when available
- similarity score and similarity method
- matched Watch or Reserve comparator ingredient(s)
- source timestamps, versions, and retrieval status

Operational interpretation:
- The purpose of chemistry comparison is not to re-derive WHO AWaRe categories from structure.
- The purpose is to detect meaningful similarity between a dossier ingredient and existing Watch or Reserve antibiotics so stewardship restrictions can be applied with evidence.

### 7.8 Local Knowledge Wiki Requirements
The system shall maintain a local-first knowledge wiki as a curated operational layer for retrieval-heavy review tasks.

Knowledge wiki scope:
- reviewer playbooks for recurring regulatory reasoning patterns
- AMR stewardship interpretations, including AWaRe speed-versus-control logic
- source-precedence rules and normalization workflows
- retrieval tactics for compare/synthesize questions that span multiple evidence domains
- model selection guidance for approved local profiles

Knowledge wiki controls:
- Each page shall have a stable page ID, title, tags, and section-level citation boundaries.
- Wiki content is curated and versioned; it is not a substitute source of truth for WHO or chemistry databases.
- The retrieval layer shall cite wiki evidence distinctly from dossier citations and external-source citations.
- The review UI shall allow direct wiki search so reviewers can inspect the curated knowledge base independently of a dossier run.

### 7.9 Conversation Continuity Requirements
The system shall preserve review continuity across turns and across linked chats without forcing the full raw transcript into every model invocation.

Conversation requirements:
- Default context window for a new review thread shall be 4096 tokens, with reviewer-adjustable limits for larger dossiers.
- Every conversation shall expose estimated token usage, remaining capacity, compaction threshold, and compaction count.
- Rolling summaries and linked-chat carryover summaries shall be clearly distinguished from raw recent turns.
- Auto-compaction shall trigger at 98% of the configured context window and must reduce the active context footprint before the next model call.
- Linked-chat carryover summaries shall be generated with a lower-cost summary route than the primary synthesis model when possible.

## 8. Agentic RAG Requirements
### 8.1 Agent Set
- Orchestrator Agent
- Retrieval Agent (hybrid search)
- Section Validator Agent
- Policy Rules Agent
- Evidence Verifier Agent
- Decision Synthesizer Agent

### 8.2 RAG Optimization Rules
- Structure-aware chunking by section boundaries.
- Hybrid retrieval (BM25 + embeddings).
- Reranking for top-k context quality.
- Metadata filters by dossier type/jurisdiction/date.
- Dynamic top-k and query decomposition for complex questions.
- Query decomposition must separate dossier, knowledge-wiki, and external-source sub-queries for compare/synthesize prompts when the question spans multiple evidence domains.
- Citation-required response schema.
- Abstention protocol when support is insufficient.
- Retrieval-first orchestration for antibacterial policy: WHO AWaRe, GLASS, and chemistry evidence retrieval must complete before the model synthesizes a final answer.
- Source reconciliation layer: the system must fuse dossier evidence with external source evidence and return provenance for every external claim.
- The curated knowledge wiki shall be indexed as a first-class corpus and retrievable with page-level and section-level provenance.
- Conversation state shall be hydrated through a LangGraph-compatible flow that evaluates context usage, applies compaction, and injects carryover summary context before synthesis.

### 8.3 Hallucination Mitigation Controls
- Retrieval quality gate before generation.
- Evidence sufficiency gate per claim.
- Grounded generation prompt constraints.
- Post-generation faithfulness verification.
- Hard policy rules gate before recommendation release.

## 9. Inference and Model Optimization Requirements
### 9.1 Local Runtime
- Primary runtime: Docker Model Runner (local).
- Secondary runtime option: local vLLM endpoint for Gemma and Qwen profiles when available.
- Primary path: quantized model for standard requests.
- Fallback path: streamed-weight inference for hard/long-context requests.

### 9.2 Routing Policy
- Default to quantized low-latency model.
- Escalate to streamed path on low confidence / high complexity.
- Cap concurrent fallback requests.
- Log route decisions for optimization analysis.
- Expose approved local model profiles in the reviewer UI so the operator can choose the synthesis model explicitly for a given run.
- Use the lower-cost summary model for conversation compaction and linked-chat carryover whenever that path is available.

### 9.3 Resource Constraints
Primary local build profile:
- Host: Asus Zenbook class laptop with 32 GB RAM.
- Approved initial runtime profiles: Gemma E4B, Gemma E2B, and Qwen 3.5, all switchable from the UI and configurable by alias.
- GPU: optional; the system must still operate in CPU-compatible mode when discrete GPU is unavailable.
- Hugging Face download credentials for vLLM-backed models must be supplied via environment variable and never persisted in project files.

Operational memory constraints:
- Reserve at least 6 GB RAM for OS and user tooling; AI stack working set must remain <= 26 GB.
- Standard route target memory envelope: <= 20 GB peak RSS.
- Fallback route target memory envelope: <= 26 GB peak RSS.
- Only one heavy inference route active at a time.
- Cache retrieval artifacts aggressively but enforce bounded cache size.
- Use async queue for expensive requests and cap fallback queue depth.
- Trigger throttle/abstain behavior when free RAM drops below safe threshold.

## 10. Privacy, Security, and Governance Requirements
- Data locality: restricted dossier data remains local.
- Network policy: block external egress for restricted workloads.
- Encryption at rest for object and DB volumes.
- PII redaction in logs and observability traces.
- Full audit logging (user, model version, evidence IDs, policy output).
- Secrets never committed; scanned in CI.

### 10.1 Data Governance Principles (Local Agentic RAG)
- Data classification: every artifact is tagged as `synthetic`, `internal`, or `restricted`.
- Purpose limitation: indexed content is used only for dossier review and policy-support workflows.
- Data minimization: ingest and index only required sections/metadata for decisions.
- Lineage and provenance: each recommendation must link to source dossier ID, section ID, model version, and prompt version.
- Retention and deletion: retention windows are defined per class, with auditable deletion jobs.
- Domain isolation: synthetic and restricted data are stored and indexed in separate namespaces.
- Access governance: least-privilege access to raw files, indexes, and audit logs.
- Governance by default: PR and CI checks must block releases with policy violations.

### 10.2 RAM Governance Principles (Local Models on 32 GB Hosts)
- Capacity-first scheduling: never co-run multiple heavy inference routes on a 32 GB machine.
- Bounded concurrency: fallback route concurrency remains capped at 1.
- Memory observability: collect per-route peak RSS and include in release gates.
- OOM prevention: enforce request queue backpressure and fail-safe abstention over crash-risk execution.
- Predictable degradation: if memory pressure is high, prefer smaller context windows and policy abstention paths.

## 11. Acceptance Criteria

| Category | Metric | Minimum (Go-Live) | Stretch |
|---|---|---:|---:|
| Section presence | Accuracy | >= 0.97 | >= 0.99 |
| Section length | Macro F1 | >= 0.93 | >= 0.96 |
| Section correctness | Macro F1 | >= 0.85 | >= 0.90 |
| GMP evidence extraction | Macro F1 | >= 0.88 | >= 0.92 |
| Pivotal trial outcome extraction | Macro F1 | >= 0.86 | >= 0.90 |
| Holistic policy class | Macro F1 | >= 0.82 | >= 0.88 |
| High-risk class (`reject_and_return`) | Recall | >= 0.90 | >= 0.94 |
| Calibration | ECE | <= 0.08 | <= 0.05 |
| Retrieval quality | Recall@10 | >= 0.88 | >= 0.93 |
| Retrieval ranking | nDCG@10 | >= 0.75 | >= 0.82 |
| Knowledge wiki retrieval | Recall@5 | >= 0.85 | >= 0.90 |
| Conversation compaction | Reviews with context monitor visible and functioning | 100% | 100% |
| Linked chat carryover | Linked chats with carryover summary successfully seeded | >= 0.95 | 100% |
| Groundedness | Claims with valid citations | >= 95% | >= 98% |
| Hallucination control | Unsupported critical claims | <= 3% | <= 1% |
| Abstention quality | Correct abstain under low evidence | >= 85% | >= 92% |
| Model selection auditability | Runs with selected model correctly logged | 100% | 100% |
| Standard route latency | p95 | <= 8s | <= 5s |
| Fallback route latency | p95 | <= 30s | <= 20s |
| Reliability | 2-hour soak test error rate | <= 1% | <= 0.3% |
| Memory governance (Zenbook 32 GB) | Standard route peak RSS | <= 20 GB | <= 16 GB |
| Memory governance (Zenbook 32 GB) | Fallback route peak RSS | <= 26 GB | <= 22 GB |
| Memory governance (Zenbook 32 GB) | OOM kill events (2-hour soak) | 0 | 0 |
| Privacy compliance | Restricted-data external egress events | 0 | 0 |
| Audit coverage | Recommendations with full trace | 100% | 100% |
| Governance coverage | Recommendations with lineage tags | 100% | 100% |
| Retention governance | Retention-policy deletion compliance | >= 99% | 100% |
| CI quality gates | Mandatory checks passed | 100% | 100% |
| Reproducibility | Fixed-set rerun variance | <= 2% | <= 1% |

## 12. Validation and Test Requirements
- Unit tests for parsers, validators, routers, and policy rules.
- Integration tests for end-to-end decision path.
- Offline evaluation on synthetic holdout + human-reviewed gold set.
- Faithfulness and citation checks.
- Latency/load/soak tests under local resource constraints.
- Security tests for egress blocking, secrets, and image vulnerabilities.
- Scenario tests covering Reserve fast-track with restricted authorization and Watch cross-resistance restriction rules.
- Contract tests for every external API or source adapter, including WHO source ingestion, GLASS retrieval, RxNorm normalization, PubChem lookup, ChEMBL lookup, and identifier reconciliation.
- End-to-end antibacterial workflow tests in three modes:
  1. mocked external sources for fast developer feedback,
  2. recorded source snapshots for deterministic CI,
  3. live external-source smoke tests for release validation.
- End-to-end workflows must cover at minimum:
  1. AWaRe category lookup for an antibiotic present in WHO data,
  2. Reserve antibiotic with critical MDR unmet need,
  3. Watch antibiotic with high structural similarity and rising GLASS trend,
  4. Access antibiotic with no escalation,
  5. non-antibacterial dossier where AWaRe logic is not applicable,
  6. external-source timeout or rate-limit fallback,
  7. source disagreement or unresolved ingredient normalization,
  8. cached-snapshot replay when live external access is unavailable.
- Every release candidate must include at least one live-source smoke execution for each external integration path that is used in production policy decisions.
- The executable workflow inventory shall be maintained in `docs/e2e-test-matrix.md`.

## 13. Definition of Done
- All minimum acceptance criteria achieved.
- End-to-end workflow available in UI and API.
- Local optimized inference routes validated.
- Security/privacy checks pass with zero restricted-data egress.
- Full auditability and reproducibility demonstrated.
- Real WHO AWaRe and GLASS sources are integrated or explicitly version-pinned as production source snapshots.
- Chemistry comparison uses authoritative structure data and is traceable end to end for antibacterial decisions.
- Mocked, snapshot-based, and live external-source end-to-end workflows all pass for the approved release scope.
