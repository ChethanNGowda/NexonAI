"""
JARVIS / PHOEBE - WEB SEARCH & READING TOOLS
============================================
Registered tools for internet search and webpage extraction.
"""

from typing import Any, Dict, List
from backend.ai.tool_registry import global_registry
from backend.research.search_manager import get_search_manager
from backend.research.source_reader import get_source_reader


@global_registry.register(
    name="web_search",
    description="Search the web for current events, technical documentation, or real-time information.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search keywords or question to search for."},
            "limit": {"type": "integer", "description": "Maximum number of search results to retrieve (1-10).", "default": 5},
        },
        "required": ["query"],
    },
)
def tool_web_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    sm = get_search_manager()
    return sm.search_single(query, limit=limit)


@global_registry.register(
    name="read_webpage",
    description="Extract clean readable text and article content from a specific website URL.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The exact HTTP or HTTPS URL to read."},
        },
        "required": ["url"],
    },
)
def tool_read_webpage(url: str) -> Dict[str, Any]:
    reader = get_source_reader()
    return reader.extract_article(url)
