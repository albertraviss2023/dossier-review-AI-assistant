from __future__ import annotations

import logging
from pathlib import Path

from regulatory_mcp_server.app import mcp, settings
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


LOGGER = logging.getLogger("regulatory_mcp_server")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging(settings.log_level)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.audit_log_path).parent.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Starting Regulatory MCP Server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
