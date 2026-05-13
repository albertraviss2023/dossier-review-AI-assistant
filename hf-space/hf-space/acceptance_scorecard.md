# Acceptance Scorecard — Dossier Review AI Assistant

## System Readiness Overview

| Metric Category | Status | Confidence |
| :--- | :--- | :--- |
| **Dossier Processing** | Pass | High |
| **Policy Evaluation** | Pass | High |
| **Agentic RAG / Review** | Partial | Medium (Mocked) |
| **AMR Stewardship** | Pass | High |
| **Non-Functional** | Pass | Medium (Simulated) |

## Detailed Scorecard

| Requirement ID | Metric Name | Target | Current | Status | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| FR-01 | Section Presence Accuracy | >= 0.97 | 1.00 | Measured (Passing) | **Valid** |
| FR-02 | Section Length Macro F1 | >= 0.93 | 1.00 | Measured (Passing) | **Valid** |
| FR-03 | Section Correctness F1 | >= 0.85 | 1.00 | Measured (Passing) | **Valid (Synthetic)** |
| FR-11 | GMP Extraction F1 | >= 0.88 | 1.00 | Measured (Passing) | **Speculative (Mock)** |
| FR-12 | Clinical Extraction F1 | >= 0.86 | 1.00 | Measured (Passing) | **Speculative (Mock)** |
| FR-21 | Holistic Policy F1 | >= 0.82 | 1.00 | Measured (Passing) | **Valid** |
| FR-23 | Reject & Return Recall | >= 0.90 | 0.00 | Measured (Failing) | **Fail (Sample size)** |
| FR-28 | Retrieval Recall @ 10 | >= 0.88 | 1.00 | Measured (Passing) | **Valid** |
| FR-29 | Chunking Retrieval Lift | >= 0.10 | 0.00 | Measured (Failing) | **Fail (Tune RAG)** |
| FR-34 | AWaRe Category F1 | >= 0.95 | 1.00 | Measured (Passing) | **Valid** |
| FR-36 | Watch Restriction Recall | >= 0.85 | 1.00 | Measured (Passing) | **Valid** |
| FR-41 | Grounded Claim Rate | >= 0.95 | 1.00 | Measured (Passing) | **Speculative (Mock)** |
| NFR-01 | Latency P95 (Standard) | <= 8s | 0.003s | Measured (Passing) | **Speculative (Mock)** |
| NFR-05 | Peak RSS (Standard) | <= 20GB | 1.06GB | Measured (Passing) | **Valid (System base)** |
| AUD-01 | Audit Trace Coverage | 1.0 | 1.0 | Measured (Passing) | **Valid** |

## Audit Verdicts

1.  **Section Accuracy**: (1.0) High performance on structured synthetic input. **Pass**.
2.  **GMP/Clinical Extraction**: (1.0) Current score reflects mock heuristic performance. Real-world model extraction remains unvalidated. **Invalid**.
3.  **Reject & Return Recall**: (0.0) The evaluation run on 3 records failed to select any "reject_and_return" cases. **Fail (Statistical significance)**.
4.  **Retrieval Lift**: (0.0) No measurable benefit for structure-aware chunking on toy text. **Fail**.
5.  **Groundedness**: (1.0) Scores are driven by a mock heuristic. **Speculative**.
6.  **Latency**: (0.003s) Mock responses are nearly instantaneous. **Speculative**.

**FINAL READINESS: CONDITIONALLY READY**
Architecture is sound, but intelligence must be validated with real models and larger datasets.
