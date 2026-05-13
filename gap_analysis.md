# Gap Analysis — Dossier Review AI Assistant

## Top 10 Implementation Gaps

1.  **Model-Based Extraction vs. Heuristic Inference**: `intake.py` uses keyword-based heuristics (`_infer_policy_signals`) to populate policy signals. Requirements FR-11 and FR-12 imply robust model-based extraction from PDF text, which is not currently active in the intake pipeline.
2.  **LLM-Judge Validity**: The `GemmaJudge` in `evaluation/run_evaluation.py` defaults to a **mock heuristic** when not explicitly configured with a live model. This makes reported groundedness and relevance metrics speculative rather than empirical.
3.  **Visual Evidence Integration**: While `RapidOCR` is present in `intake.py`, the `generate_dossiers.py` script does not generate the complex visual artifacts (tables, stamps, signatures) required to truly test the OCR and visual summary capabilities.
4.  **Retrieval Evaluation Baseline**: `evaluation/run_evaluation.py` reports a 0.0 lift for chunking vs. baseline in the latest run. This suggests the test cases or baseline itself are not properly configured to show the advantage of structure-aware chunking.
5.  **Policy Evaluation Circularity**: Metrics like `gmp_evidence_extraction_macro_f1` are computed by comparing the dossier's `policy_signals` to themselves, rather than comparing a model's extraction output to ground truth. This invalidates current accuracy scores for extraction.
6.  **Abstention Precision**: While `correct_abstain_rate` is 1.0 in the 3-record run, the `GemmaJudge` mock logic for groundedness is overly simplistic, potentially missing nuanced hallucinations.
7.  **External Source Live Integration**: `external_sources.py` is implemented for live URLs, but evaluation reports show it was run in `snapshot_only` mode. Live-source precedence and latency (FR-38, FR-40) are unvalidated.
8.  **Memory Compaction Trigger**: Requirement NFR-06 specifies compaction at 98% context usage. While `ConversationStore` has `compact_context`, there is no evidence of an automated monitor triggering this during long-running sessions in real-world multi-turn scenarios.
9.  **UI Feedback Loop**: The UI (`review.html`) provides evidence inspection, but "re-evaluate" or "human-in-the-loop" correction of policy signals (implied by policy-copilot workflows) is not fully implemented as a write-back to dossier state.
10. **Error Tag Granularity**: `error_tags` in synthetic data are limited to 7-8 modes. Real regulatory dossiers have hundreds of possible defect types (ICH/CTD).

## Top 10 Dataset Gaps

1.  **PDF Visual Realism**: PDFs are text-only. They lack the headers, footers, tables, and scanned elements required by Requirement 5.E.
2.  **Section Text Diversity**: Synthetic text relies heavily on `FILLER_SENTENCES`. This creates a "toy" dataset that may over-index on specific phrases (e.g., "mixed-effects model"), making retrieval artificially easy or biased.
3.  **Gold Set Utilization**: The machine-adjudicated gold set exists but is not the default target for the main evaluation script, leading to potentially inflated results on the standard "balanced" set.
4.  **Mixed-Language Support**: Current datasets are 100% English; no testing of multi-language extraction or normalization.
5.  **Contradiction Scenario Density**: Cross-section inconsistency (`cross_section_inconsistency`) is a defect mode but is poorly represented in sample dossiers.
6.  **Image Asset Coverage**: `sample_dossiers/incoming_files/` has only one "scanned" PDF. No broad dataset of scanned or multi-column layouts to validate OCR robustness at scale.
7.  **Clinical Endpoint Nuance**: Clinical "failed" status is binary in current signals. Real dossiers often have complex "non-inferiority" or "subgroup" failures not represented.
8.  **Chemistry Comparator Complexity**: Watch similarity is a simple "high/low" signal. It lacks actual molecular structure data (SMILES/InChI) that would be needed to test a true chemistry-aware agent.
9.  **Dossier Completeness Variability**: Most synthetic dossiers have 12 sections. Real dossiers vary significantly in Module 3/5 completeness.
10. **Annotated Citation Spans**: There is no "gold" mapping of questions to exact character spans in PDFs, making "citation accuracy" (Requirement 7.3) difficult to measure objectively.

## Top 10 Instrumentation Gaps

1.  **Latency Breakdown**: `telemetry.py` tracks total latency but not the breakdown between retrieval, routing, and model generation.
2.  **Context Window Monitoring**: `contextRing` in the UI is a good visual, but no telemetry logging of "near-OOM" or "high-context-pressure" events in backend audit.
3.  **Token Counting Accuracy**: Token estimation uses a whitespace heuristic (`len().split()`). This is inaccurate for sub-word tokenizers used by Gemma/LLMs.
4.  **Retrieval "Missingness" Tracking**: No metric for "Search Miss" (where relevant info exists but was not retrieved) vs "Source Missing" (info does not exist).
5.  **User Correction Logging**: When a user corrects an AI claim in the UI, this is not currently captured in the audit trace to facilitate future RLHF or fine-tuning.
6.  **Model Selection Transparency**: Audit trace logs the model used, but not the specific "intent confidence" that led the router to pick that model/path.
7.  **Prompt Leakage Detection**: No instrumentation to check if retrieved context for one dossier is accidentally leaking into a conversation about another (Requirement 6.1).
8.  **External API Health**: No heartbeat or failure-rate monitoring for live WHO/GLASS/RxNorm adapters.
9.  **Evaluation Sample Size**: Main evaluation script defaults to 120, but recent runs used only 3 records, making CI/CD gates unreliable.
10. **System Resource Attribution**: Memory RSS is tracked at process level, but not attributed to specific tasks (e.g., "how much RAM did this PDF OCR take?").
