# Dossier Review AI Assistant Requirements Specification

## 1. Document Control
- Project: Regulatory Dossier Policy Copilot (Agentic RAG, Local-First)
- Version: 1.0
- Status: Draft for build execution
- Owner: Data Science / MLOps
- Last Updated: 2026-04-02

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

## 6. Non-Functional Requirements
- NFR-01: Privacy by default (no external inference for restricted data).
- NFR-02: Reproducibility (versioned data, prompts, configs, models).
- NFR-03: Reliability with graceful fallback across inference strategies.
- NFR-04: Security with RBAC, least privilege, and encrypted storage.
- NFR-05: Performance within laptop constraints (8GB VRAM GPU).
- NFR-06: CI quality gates must block unsafe/low-quality releases.

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

Labeling method:
- Weak labels from generator metadata + deterministic rules.
- Strict machine adjudication on a 20-25% gold subset with higher evidence thresholds.
- Optional later human review only if calibration gaps remain after offline validation.

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
- Citation-required response schema.
- Abstention protocol when support is insufficient.

### 8.3 Hallucination Mitigation Controls
- Retrieval quality gate before generation.
- Evidence sufficiency gate per claim.
- Grounded generation prompt constraints.
- Post-generation faithfulness verification.
- Hard policy rules gate before recommendation release.

## 9. Inference and Model Optimization Requirements
### 9.1 Local Runtime
- Primary runtime: Docker Model Runner (local).
- Primary path: quantized model for standard requests.
- Fallback path: streamed-weight inference for hard/long-context requests.

### 9.2 Routing Policy
- Default to quantized low-latency model.
- Escalate to streamed path on low confidence / high complexity.
- Cap concurrent fallback requests.
- Log route decisions for optimization analysis.

### 9.3 Resource Constraints
Hardware baseline:
- GPU: RTX 3070 8GB VRAM
- Host memory constrained; avoid multiple concurrent heavy models.

Operational constraints:
- Only one GPU-heavy inference service active at a time.
- Cache retrieval and embeddings aggressively.
- Use async queue for expensive requests.

## 10. Privacy, Security, and Governance Requirements
- Data locality: restricted dossier data remains local.
- Network policy: block external egress for restricted workloads.
- Encryption at rest for object and DB volumes.
- PII redaction in logs and observability traces.
- Full audit logging (user, model version, evidence IDs, policy output).
- Secrets never committed; scanned in CI.

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
| Groundedness | Claims with valid citations | >= 95% | >= 98% |
| Hallucination control | Unsupported critical claims | <= 3% | <= 1% |
| Abstention quality | Correct abstain under low evidence | >= 85% | >= 92% |
| Standard route latency | p95 | <= 8s | <= 5s |
| Fallback route latency | p95 | <= 30s | <= 20s |
| Reliability | 2-hour soak test error rate | <= 1% | <= 0.3% |
| Privacy compliance | Restricted-data external egress events | 0 | 0 |
| Audit coverage | Recommendations with full trace | 100% | 100% |
| CI quality gates | Mandatory checks passed | 100% | 100% |
| Reproducibility | Fixed-set rerun variance | <= 2% | <= 1% |

## 12. Validation and Test Requirements
- Unit tests for parsers, validators, routers, and policy rules.
- Integration tests for end-to-end decision path.
- Offline evaluation on synthetic holdout + human-reviewed gold set.
- Faithfulness and citation checks.
- Latency/load/soak tests under local resource constraints.
- Security tests for egress blocking, secrets, and image vulnerabilities.

## 13. Definition of Done
- All minimum acceptance criteria achieved.
- End-to-end workflow available in UI and API.
- Local optimized inference routes validated.
- Security/privacy checks pass with zero restricted-data egress.
- Full auditability and reproducibility demonstrated.
