# Regulatory MCP Tools Testing Guide

This document provides realistic test cases for verifying the readiness and functionality of the Regulatory MCP tools using the **MCP Inspector** or any standard MCP debugger.

## 🚀 Getting Started

### 1. Start the MCP Server
Use `uv` to run the server in stdio mode (required for the Inspector):
```powershell
uv run main.py
```

### 2. Launch the MCP Inspector
In a separate terminal, launch the inspector to interact with the tools visually:
```powershell
npx @modelcontextprotocol/inspector uv run main.py
```

---

## 🧪 Realistic Test Scenarios

### 1. AMR Stewardship (AWaRe)
**Tool:** `fetch_aware_reserve_reference`
*   **Goal:** Verify the system correctly identifies a high-priority "Reserve" antibiotic.
*   **Input:** 
    *   `active_ingredient`: "colistin"
*   **Expected Readiness:** Should return `aware_category: "Reserve"` and `reserve_related: true`.

**Tool:** `compute_antimicrobial_similarity`
*   **Goal:** Test the logic for stewardship flags.
*   **Input:**
    *   `active_ingredient`: "colistin"
    *   `aware_reference`: (Use the output from the previous step)
*   **Expected Readiness:** Should return `stewardship_flag: "required_control"` and a clear recommendation for controlled handling.

---

### 2. Patient Information Extraction
**Tool:** `fetch_innovator_patient_information`
*   **Goal:** Verify extraction of paracetamol reference data.
*   **Input:**
    *   `active_ingredient`: "paracetamol"
*   **Expected Readiness:** Should return structured sections (Indications, Dosage, Warnings) and a `reference_product` name.

**Tool:** `compare_generic_patient_information`
*   **Goal:** Test the "gap analysis" logic between generic and innovator text.
*   **Input:**
    *   `innovator_pil_sections`: (Use sections from the fetch tool)
    *   `current_pil_sections`: `[{"section_name": "warnings", "text": "Take with water."}]`
    *   `comparison_dimensions`: `["warnings"]`
*   **Expected Readiness:** Should return `overall_alignment: "not_aligned"` because the generic text is missing critical innovator safety warnings.

---

### 3. Naming & WHO INN Review
**Tool:** `fetch_who_inn_candidates`
*   **Goal:** Check for name conflicts.
*   **Input:**
    *   `active_ingredient`: "amoxicillin"
    *   `proposed_name`: "Amoxi-Clean"
*   **Expected Readiness:** Should identify "amoxicillin" as a candidate and provide the stem/prefix metadata.

**Tool:** `compute_inn_similarity`
*   **Goal:** Test orthographic similarity scoring.
*   **Input:**
    *   `proposed_name`: "Amoxi-Clean"
    *   `inn_candidates`: `["amoxicillin"]`
*   **Expected Readiness:** Should provide a similarity score and a `decision_effect` (e.g., "can_continue" or "requires_justification").

---

### 4. Evidence Discovery (Vector Search)
**Tool:** `search_vector_database`
*   **Goal:** Test the retrieval of regulatory guidance.
*   **Input:**
    *   `query`: "What are the requirements for a generic PIL?"
    *   `index`: "knowledge_wiki"
    *   `top_k`: 3
*   **Expected Readiness:** Should return relevant chunks from the local `knowledge_wiki.json` with citations.

**Tool:** `reranker_search_results`
*   **Goal:** Test the ability to prioritize "Dossier" content over general guidance.
*   **Input:**
    *   `query`: "dosage instructions"
    *   `candidate_results`: (Use output from search tool)
    *   `rerank_criteria`: `["current dossier applicability"]`
*   **Expected Readiness:** Results with `source: "dossier_section"` should move higher in the list.

---

### 5. Reporting & Aggregation
**Tool:** `build_evidence_packet`
*   **Goal:** Verify that all previous tool outputs can be combined for the judgment layer.
*   **Input:**
    *   `dossier_id`: "TEST-001"
    *   `tool_results`: (A map of results from the tools above)
*   **Expected Readiness:** Should return a structured `EvidencePacket` with `ready_for_judgment: true`.

---

## 🛠 Troubleshooting the Debugger
- **"Unknown Tool":** Ensure you restarted the server after any code changes.
- **"Validation Error":** Check that the JSON you are pasting into the debugger matches the tool's argument names (e.g., use `active_ingredient` not `ingredient`).
- **"Connection Refused":** Ensure no other process is holding the stdio stream or the port (if using HTTP).
