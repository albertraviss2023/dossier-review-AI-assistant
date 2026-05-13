# Regulatory MCP Server

Real MCP server for the regulatory review workstation, built with the official Python MCP SDK.

## What it exposes

The server exposes independently callable, JSON-first regulatory tools for:

- vector search over dossier/guidance/example content
- deterministic reranking
- correct vs incorrect section examples
- WHO INN candidate lookup and similarity checks
- AWaRe / Reserve antimicrobial stewardship checks
- innovator patient-information fetch and generic comparison
- evidence packet construction
- findings-table generation
- health/status inspection

## Design rule

- JSON is used for all MCP tool inputs and outputs.
- Markdown is used only for human-facing summaries, chat rendering, report sections, and reviewer displays.
- Cached external sources are preserved as raw snapshot references plus normalized structured data.

## Local startup

Install dependencies:

```powershell
python -m pip install -e .
python -m pip install "mcp[cli]"
```

Start the MCP server:

```powershell
python -m regulatory_mcp_server.server
```

Default MCP endpoint:

- `http://127.0.0.1:8010/mcp`

## Local inspection

List tools and call the health tool:

```powershell
@'
import asyncio
import json
from regulatory_mcp_server.app import mcp

async def main():
    tools = await mcp.list_tools()
    print([tool.name for tool in tools])
    result = await mcp.call_tool("health_status", {})
    if isinstance(result, tuple):
        result = result[0]
    print(json.loads(result[0].text))

asyncio.run(main())
'@ | python -
```

Run the end-to-end tool sequence:

```powershell
python scripts/test_mcp_end_to_end.py
```

Run realistic simulations:

```powershell
python scripts/run_mcp_realistic_simulations.py
```

## Tests

Run the MCP test suite:

```powershell
python -m pytest regulatory_mcp_server/tests -q
```

## Tool examples

### Vector search

Input:

```json
{
  "query": "WHO AWaRe Watch escalation",
  "index": "knowledge_wiki",
  "filters": {},
  "top_k": 3
}
```

Output shape:

```json
{
  "status": "success",
  "data": {
    "results": [
      {
        "chunk_id": "string",
        "source": "knowledge_wiki",
        "text": "string",
        "score": 0.47,
        "metadata": {}
      }
    ]
  },
  "warnings": [],
  "source_refs": [],
  "audit": {}
}
```

### Findings table

Input:

```json
{
  "dossier_id": "DOS-MCP-001",
  "findings": [
    {
      "review_area": "patient_information",
      "finding": "Generic PIL does not align with innovator warnings.",
      "severity": "major",
      "violated_rule": "Generic patient information should align closely with innovator/reference material",
      "evidence_ref": "DOS-MCP-001:pil-1",
      "recommendation": "Align warnings and storage wording with the innovator reference.",
      "decision_trace": {
        "tool": "compare_generic_patient_information"
      }
    }
  ],
  "group_by": "review_area"
}
```

Output shape:

```json
{
  "status": "success",
  "data": {
    "markdown_table": "### Patient Information ...",
    "structured_table": []
  },
  "warnings": [],
  "source_refs": [],
  "audit": {}
}
```

## Security model

- no arbitrary shell execution
- no unvalidated file path access
- no secret values written to audit logs
- external access disabled by default
- allowlist for external domains
- invalid or blocked URLs rejected cleanly
- per-tool audit records in `state/audit/regulatory_mcp_tool_calls.jsonl`
- cache-first behavior for locally testable regulatory tools

## Integration with the main app

The main app integrates these MCP tools in the structured review path:

- naming review -> `fetch_who_inn_candidates`, `compute_inn_similarity`
- AMR stewardship -> `fetch_aware_reserve_reference`, `compute_antimicrobial_similarity`
- generic patient information review -> `fetch_innovator_patient_information`, `compare_generic_patient_information`
- evidence search -> `search_vector_database`, `rerank_search_results`
- section adequacy -> `get_section_examples`, `compare_current_section_to_examples`
- findings tables -> `generate_findings_table`

The app calls the MCP server in-process through a local adapter, so the exact same tool contracts are used in:

- unit tests
- end-to-end MCP sequence tests
- realistic simulations
- the main structured regulatory review workflow
