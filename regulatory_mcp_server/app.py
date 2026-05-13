from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from regulatory_mcp_server.config import RegulatoryMCPSettings

settings = RegulatoryMCPSettings()

mcp = FastMCP(
    settings.server_name,
    instructions=(
        "Regulatory MCP server exposing auditable, schema-driven tools for "
        "pre-market authorization dossier review."
    ),
)

# Import tools to register them with the mcp instance
import regulatory_mcp_server.tools.aware_amr  # noqa: F401
import regulatory_mcp_server.tools.evidence_packet  # noqa: F401
import regulatory_mcp_server.tools.examples  # noqa: F401
import regulatory_mcp_server.tools.health  # noqa: F401
import regulatory_mcp_server.tools.inn_similarity  # noqa: F401
import regulatory_mcp_server.tools.knowledge_graph  # noqa: F401
import regulatory_mcp_server.tools.patient_info  # noqa: F401
import regulatory_mcp_server.tools.reports  # noqa: F401
import regulatory_mcp_server.tools.reranker  # noqa: F401
import regulatory_mcp_server.tools.vector_search  # noqa: F401
