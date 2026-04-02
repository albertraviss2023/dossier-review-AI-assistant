# Dossier Review AI Assistant Implementation Plan (7-Day Build)

## 1. Delivery Objective
Deliver a production-grade local-first Regulatory Dossier Policy Copilot with agentic RAG, section-level + holistic correctness scoring, and policy-ready recommendation workflow.

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
- Stand up local dependencies: Postgres/pgvector, MinIO, MLflow, Redis.
- Bootstrap FastAPI policy service and UI shell.
- Add initial CI pipeline (lint + unit test scaffold).

Exit criteria:
- Local stack starts successfully.
- API contracts and schemas committed.

### Day 2: Synthetic Data and Label Pipeline
- Build synthetic dossier generator with realistic section distributions.
- Add controlled failure modes: missing sections, wrong lengths, contradictory evidence.
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
- Implement evidence pack assembly with citation spans.
- Add evidence sufficiency and faithfulness gates.

Exit criteria:
- End-to-end recommendation path works with citations.
- Unsupported-claim gate blocks unsafe answers.

### Day 5: Inference Optimization (Quantized + Streaming)
- Integrate Docker Model Runner as primary inference runtime.
- Configure quantized local model route.
- Add streamed-weight fallback route for hard cases.
- Implement routing policy, queueing, and fallback observability.
- Benchmark quality/latency/resource trade-offs.

Exit criteria:
- Dual-route inference active with policy-based routing.
- Latency and VRAM profile documented.

### Day 6: Security, Observability, and CI/CD Gates
- Enforce RBAC and signed audit logs.
- Add restricted-workload egress controls.
- Add Prometheus/Grafana dashboards and alert rules.
- Add CI gates for quality thresholds and security checks.

Exit criteria:
- Release pipeline blocks failing metrics/tests.
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
- Deploy strategy: local dev -> local staging -> local prod namespace.
- Rollback strategy: model alias rollback + previous container image restore.

## 7. Deliverables
- Requirements specification.
- Architecture diagrams.
- Dataset schema + synthetic generator.
- Trained baseline models and evaluation report.
- Running UI/API with dual-route inference.
- Monitoring dashboards and alerting.
- Release runbook and readiness checklist.
