"""
JARVIS / PHOEBE - DEEP RESEARCH QUERY PLANNER
============================================
Deconstructs complex multi-part user inquiries into structured research queries
focusing on primary sources, official documentation, and key verification points.
"""

import json
import logging
import re
from typing import Any, Dict, List

from backend.ai.ollama_client import get_ollama_client
from backend.ai.prompts import RESEARCH_PLANNER_SYSTEM

logger = logging.getLogger(__name__)


class QueryPlanner:
    def __init__(self):
        self.ollama = get_ollama_client()

    def plan_research(self, user_inquiry: str) -> Dict[str, Any]:
        """
        Produce a research plan with 2 to 4 search queries targeting
        different aspects of the question.
        """
        # Quick heuristic fallback queries in case LLM is offline or busy
        sanitized = re.sub(r"[^\w\s-]", "", user_inquiry).strip()
        default_queries = [
            sanitized,
            f"{sanitized} documentation",
            f"{sanitized} latest updates",
        ]

        if not self.ollama.is_available():
            return {
                "focus": user_inquiry,
                "queries": default_queries[:2],
                "verification_targets": ["overview", "official source"],
            }

        try:
            data = self.ollama.generate_json(
                prompt=f"Research topic: \"{user_inquiry}\"",
                system_instruction=RESEARCH_PLANNER_SYSTEM,
                max_tokens=300,
            )

            queries = data.get("queries", [])
            if not isinstance(queries, list) or not queries:
                queries = default_queries

            return {
                "focus": data.get("focus", user_inquiry),
                "queries": [q for q in queries if isinstance(q, str)][:4],
                "verification_targets": data.get("verification_targets", ["overview"]),
            }
        except Exception as e:
            logger.warning("Query planning failed, using heuristics: %s", e)
            return {
                "focus": user_inquiry,
                "queries": default_queries[:3],
                "verification_targets": ["overview"],
            }


_planner_instance: QueryPlanner | None = None


def get_query_planner() -> QueryPlanner:
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = QueryPlanner()
    return _planner_instance
