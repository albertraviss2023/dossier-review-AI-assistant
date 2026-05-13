# Dataset Audit — Dossier Review AI Assistant

## Dataset Realism Overview

| Artifact | Type | Quantity | Realistic Visuals | Realism Rating | Use for Metrics |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sample_dossiers/*.json` | Sample | 6 | No (JSON) | Toy/Demo | No |
| `synthetic_data/.../dossiers.jsonl` | Synthetic | ~1,200 | No (JSONL) | Acceptable Synthetic | Yes (Policy/Retrieval) |
| `synthetic_data/.../dossiers_pdf/*.pdf` | PDF | ~1,200 | No (Text-only) | Weak Synthetic | No (Visual/OCR) |
| `sample_dossiers/incoming_files/*.pdf` | Sample | 12 | 1 (Scanned) | Acceptable Synthetic | Yes (Smoke test) |
| `synthetic_data/data/gold/.../*.jsonl` | Gold set | 240 | No (JSONL) | Acceptable Synthetic | Yes (Validation) |

## Quality & Realism Audit

### A. Structural Completeness
- **Module Coverage**: Excellent. The synthetic generator supports Modules 1, 2, 3, 4, and 5.
- **Critical Sections**: GMP evidence and clinical trial reports are consistently included.
- **Section Count**: Most dossiers contain 12 sections. Real dossiers vary significantly.

### B. Section Realism
- **Language**: Acceptable regulatory language is used.
- **Diversity**: Weak. Repetitive "filler" sentences are used for non-critical sections.
- **Internal Consistency**: High. Policy signals match section content (essential for training).

### C. PDF Visual Realism (Critical Failure)
- **Layout**: Synthetic PDFs are text-only, rendered in single-column Helvetica.
- **Mixed Content**: No tables, diagrams, or charts exist in the synthetic PDFs.
- **Stamps/Signatures**: Completely absent.
- **OCR Challenge**: Too "clean" for robust OCR validation.

### D. Label Quality
- **Section Labels**: (presence, length, correctness) are 100% complete and consistent.
- **Policy Labels**: (decision, risk_score) are 100% complete.
- **Usability**: High for training standard policy classifiers, but likely too "clean" for real-world performance.

## Data Readiness Verdict

**Verdict: PARTIALLY FIT**

The dataset is excellent for testing **policy logic, intent routing, and retrieval heuristics** using the canonical JSONL source. However, it is **unsuitable for validating the "visual" and "OCR" requirements** of the project.

## Required Data Actions

1.  **Enhance PDF Generator**: Add basic table structures and simulated stamps using a library like `reportlab` or `pypdf`.
2.  **Increase Text Diversity**: Replace static `FILLER_SENTENCES` with a larger pool of randomized paragraphs or LLM-generated text.
3.  **Gold Set Standard**: Force all evaluation runs to default to the `gold` set (240 records) to ensure rigorous metric reporting.
