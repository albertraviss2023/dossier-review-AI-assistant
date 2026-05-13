# Regulatory MCP Server

## Purpose

The project uses a real MCP server as the audited tool layer for structured regulatory review. It replaces the earlier mock wrapper with independently callable tools that can be:

- tested locally
- inspected by MCP-capable clients
- audited through JSON tool envelopes and audit logs
- reused inside the main dossier review workstation

## Server startup

```powershell
python -m regulatory_mcp_server.server
```

Default endpoint:

- `http://127.0.0.1:8010/mcp`

## Tool catalog

- `health_status`
- `search_vector_database`
- `rerank_search_results`
- `get_section_examples`
- `compare_current_section_to_examples`
- `fetch_who_inn_candidates`
- `compute_inn_similarity`
- `fetch_aware_reserve_reference`
- `compute_antimicrobial_similarity`
- `fetch_innovator_patient_information`
- `compare_generic_patient_information`
- `build_evidence_packet`
- `generate_findings_table`

## JSON vs Markdown rule

- MCP tools always accept and return JSON.
- Markdown is generated only for:
  - reviewer chat rendering
  - findings summary tables
  - report sections
  - simulation and audit summaries

## Main app integration

The structured dossier review path uses MCP tools directly:

- retrieval path: `search_vector_database` + `rerank_search_results`
- naming path: `fetch_who_inn_candidates` + `compute_inn_similarity`
- AMR path: `fetch_aware_reserve_reference` + `compute_antimicrobial_similarity`
- generic patient information path:
  - `fetch_innovator_patient_information`
  - `compare_generic_patient_information`
- section adequacy path:
  - `get_section_examples`
  - `compare_current_section_to_examples`
- findings summary path: `generate_findings_table`

The app uses an in-process adapter so the same MCP contracts are exercised in:

- MCP unit tests
- the end-to-end MCP sequence script
- realistic simulation runs
- the production review workflow

## Local validation commands

Unit and contract tests:

```powershell
python -m pytest regulatory_mcp_server/tests -q
```

End-to-end MCP sequence:

```powershell
python scripts/test_mcp_end_to_end.py
```

Realistic MCP + app simulations:

```powershell
python scripts/run_mcp_realistic_simulations.py
```

## Security model

- external source access disabled by default
- strict domain allowlist
- invalid URLs rejected
- blocked domains rejected
- audit log per tool call
- cache-first fixtures for local deterministic testing
- no shell execution
- no arbitrary path access
- no secret values written to audit logs

## Output conventions

Every tool output includes:

- `status`
- `data`
- `warnings`
- `source_refs`
- `audit`

The `audit` object includes:

- `tool_name`
- `timestamp`
- `request_id`
- `input_hash`

This allows the workstation to preserve decision traceability without exposing hidden chain-of-thought. The reviewer-facing UI should render only readable reasoning traces, findings summaries, and reports. The raw MCP envelopes remain available for audit and debug flows. 
