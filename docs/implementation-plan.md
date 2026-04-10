# Dossier Review AI Assistant Implementation Plan (7-Day Build)

## 1. Delivery Objective
Deliver a production-grade local-first Regulatory Dossier Policy Copilot with agentic RAG, section-level + holistic correctness scoring, curated knowledge wiki support, conversation continuity controls, and policy-ready recommendation workflow.

Priority note:
- For antibacterial dossiers, retrieval strength is the primary success factor. Real WHO AWaRe, WHO GLASS, and chemistry-source integration are on the critical path and must not be treated as optional model enhancements.

## 2. Workstream Breakdown
- WS-A: Platform and security foundation
- WS-B: Data generation and labeling
- WS-C: Modeling and evaluation
- WS-D: Agentic RAG and inference orchestration
- WS-E: UI, observability, and release hardening

## 3. Day-by-Day Execution

### Day 1: Foundation and Contracts
- Create monorepo skeleton and service boundaries.
- Define dossier schema, section taxonomy, and policy output schema.
- Define external-source contracts for WHO AWaRe, WHO GLASS, RxNorm, PubChem, ChEMBL, and identifier reconciliation.
- Define the knowledge wiki content model, citation boundaries, and update workflow.
- Define the switchable local model catalog and UI contract for Gemma E4B, Gemma E2B, and Qwen 3.5.
- Define conversation-thread contracts, context-window telemetry, linked-chat carryover behavior, and LangGraph-compatible state flow.
- Stand up local dependencies: Postgres/pgvector, MinIO, MLflow, Redis.
- Bootstrap FastAPI policy service and UI shell.
- Add initial CI pipeline (lint + unit test scaffold).

Exit criteria:
- Local stack starts successfully.
- API contracts and schemas committed.

### Day 2: Synthetic Data and Label Pipeline
- Build synthetic dossier generator with realistic section distributions.
- Add controlled failure modes: missing sections, wrong lengths, contradictory evidence.
- Add synthetic placeholders only for development scaffolding while planning real-source retrieval adapters and pinned source snapshots.
- Generate v0 dataset (>=500 dossiers) and version with DVC.
- Generate strict adjudicated gold set from raw synthetic outputs.
- Produce train/val/test splits with section-level and holistic labels.

Exit criteria:
- Versioned dataset exists with section and holistic labels.
- Gold-set adjudication and split workflow documented and runnable.

### Day 3: Section and Holistic Models
- Train section validators (presence, length class, correctness class).
- Train holistic policy classifier.
- Calibrate confidence and define abstention threshold.
- Log artifacts and metrics in MLflow.

Exit criteria:
- Baseline model versions registered.
- Offline metrics generated against acceptance table.

### Day 4: Agentic RAG Pipeline
- Implement orchestrator and specialized agents.
- Build hybrid retrieval and reranking pipeline.
- Implement external evidence retrieval adapters and cache layers for WHO AWaRe, WHO GLASS, RxNorm, PubChem, ChEMBL, and source snapshot replay.
- Index the curated knowledge wiki and wire it into retrieval and synthesis flows as a distinct evidence corpus.
- Implement query decomposition and evidence-pack assembly for compare/synthesize prompts that span dossier, wiki, and external sources.
- Implement conversation context hydration, rolling-summary compaction, and linked-thread carryover before synthesis.
- Implement evidence pack assembly with citation spans.
- Add evidence sufficiency and faithfulness gates.

Exit criteria:
- End-to-end recommendation path works with citations.
- Antibacterial decisions are grounded in real-source retrieval or pinned source snapshots.
- Unsupported-claim gate blocks unsafe answers.

### Day 5: Inference Optimization (Quantized + Streaming)
- Integrate Docker Model Runner as primary inference runtime.
- Configure quantized local model route.
- Register switchable local profiles for Gemma E4B, Gemma E2B, and Qwen 3.5.
- Expose model selection in the UI and propagate the chosen profile through review responses and audit logs.
- Add local vLLM compatibility path and env-driven Hugging Face token handling without writing secrets to disk.
- Add streamed-weight fallback route for hard cases.
- Implement routing policy, queueing, and fallback observability.
- Benchmark quality/latency/resource trade-offs.

Exit criteria:
- Dual-route inference active with policy-based routing.
- Latency and VRAM profile documented.

### Day 6: Security, Observability, and CI/CD Gates
- Enforce RBAC and signed audit logs.
- Add restricted-workload egress controls.
- Enforce data governance controls (classification tags, lineage fields, retention jobs).
- Add memory governance checks for 32 GB RAM hosts (peak RSS capture, OOM prevention guardrails).
- Add Prometheus/Grafana dashboards and alert rules.
- Add CI gates for quality thresholds and security checks.
- Add multi-tier test execution: mocked external-source tests, snapshot-replay tests, and live-source smoke tests.
- Add workflow coverage for knowledge-wiki retrieval, multi-hop query decomposition, and model-switch execution paths.
- Add workflow coverage for context-window monitoring, auto-compaction, and linked-chat continuation.

Exit criteria:
- Release pipeline blocks failing metrics/tests.
- Governance and RAM safety thresholds are evaluated in CI release gates.
- Security checks pass in CI.

### Day 7: UAT, Hardening, and Release Candidate
- Execute full validation matrix.
- Conduct reviewer UAT scenarios and override workflow tests.
- Finalize runbook, incident guide, and rollback procedure.
- Tag release candidate and generate readiness report.

Exit criteria:
- Go-live criteria met or remediation list approved.
- Demo flow is reproducible end-to-end.

## 4. Capacity and Resource Management Plan
- Run only one GPU-intensive route at a time.
- Set conservative concurrency and queue depth.
- Prefer quantized route by default.
- Use streamed route only under explicit complexity/uncertainty triggers.
- Cache retrieval and embeddings to reduce repeated compute.
- Maintain a 32 GB RAM operating budget with explicit route-level memory envelopes.
- Throttle or abstain under memory pressure instead of overcommitting RAM.

## 5. Risk Register and Mitigations
- Risk: Hallucinated unsupported outputs.
  - Mitigation: evidence and faithfulness gates, abstention protocol.
- Risk: Latency spikes from streamed fallback.
  - Mitigation: routing thresholds, queue controls, route-specific SLOs.
- Risk: Synthetic data mismatch with field reality.
  - Mitigation: targeted human-reviewed gold subset, scenario stress tests.
- Risk: Sensitive data leakage.
  - Mitigation: local-only processing, egress controls, log redaction.

## 6. CI/CD and Release Policy
- PR checks: lint, unit, integration, schema validation, security scan.
- Model gate checks: retrieval, classification, groundedness thresholds.
- External-source gate checks: API contract tests, pinned-snapshot replay tests, and live-source smoke tests for production-critical source adapters.
- Deploy strategy: local dev -> local staging -> local prod namespace.
- Rollback strategy: model alias rollback + previous container image restore.

## 7. Deliverables
- Requirements specification.
- Architecture diagrams.
- Dataset schema + synthetic generator.
- Trained baseline models and evaluation report.
- Running UI/API with dual-route inference.
- Curated knowledge wiki with indexed pages and retrieval tests.
- Conversation continuity layer with context monitor, auto-compaction, and linked-thread carryover.
- Monitoring dashboards and alerting.
- Release runbook and readiness checklist.
