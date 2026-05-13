from __future__ import annotations

from typing import Any
from .router import GlossaryTool

class MCPRegistry:
    """Mock MCP Registry for the Dossier Assistant."""
    def __init__(self) -> None:
        self.glossary = GlossaryTool()
        self.tools = {
            "lookup_glossary": self.lookup_glossary,
        }

    def lookup_glossary(self, query: str) -> dict[str, Any]:
        """MCP Tool: Resolve regulatory acronyms in a query."""
        resolved = self.glossary.resolve(query)
        # Identify which acronyms were resolved
        found = [acronym for acronym in self.glossary.glossary.keys() if acronym.lower() in query.lower()]
        return {
            "original_query": query,
            "resolved_query": resolved,
            "resolved_acronyms": found,
            "status": "success" if found else "no_acronyms_found"
        }

    def call_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found in MCP registry")
        return self.tools[name](**kwargs)

mcp_registry = MCPRegistry()
