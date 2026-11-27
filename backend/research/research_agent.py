"""
JARVIS / PHOEBE - GEMINI-STYLE DEEP RESEARCH AGENT
==================================================
Autonomous multi-step research workflow:
  1. Understand question & break down into sub-queries (Planner)
  2. Search multiple sources across engines (SearchManager)
  3. Scrape and extract clean text (SourceReader)
  4. Rank sources by credibility, recency, and relevance (SourceRanker)
  5. Verify claims and detect discrepancies (SourceVerifier)
  6. Synthesize comprehensive report with citations (ReportGenerator)
  7. Provide ultra-concise spoken voice summary for Edge TTS
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.ai.ollama_client import get_ollama_client
from backend.ai.prompts import RESEARCH_SYNTHESIS_SYSTEM
from backend.research.citation_manager import CitationManager, ReportGenerator
from backend.research.query_planner import get_query_planner
from backend.research.search_manager import get_search_manager
from backend.research.source_ranker import SourceRanker, SourceVerifier
from backend.research.source_reader import get_source_reader

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(self):
        self.ollama = get_ollama_client()
        self.search_mgr = get_search_manager()
        self.reader = get_source_reader()
        self.planner = get_query_planner()
        self.ranker = SourceRanker()
        self.verifier = SourceVerifier()

    def run_research(
        self,
        inquiry: str,
        mode: str = "standard",  # "quick", "standard", "deep"
        progress_callback: Optional[Callable[[str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Execute research with real-time progress events.
        Modes:
          - 'quick': Single search query, fast summary
          - 'standard': 2-3 queries, source reading, verified citations
          - 'deep': Multi-angle planning, comprehensive source extraction, verification
        """

        def update(step: str, detail: str):
            if progress_callback:
                progress_callback(step, detail)

        if cancel_check and cancel_check():
            return {"cancelled": True, "answer": "Research cancelled by user."}

        mode = mode.lower().strip()
        update("understanding", f"Analyzing inquiry: '{inquiry[:60]}...'")

        # 1. Planning Step
        if mode == "quick":
            queries = [inquiry]
        else:
            update("planning", "Generating targeted research queries...")
            plan = self.planner.plan_research(inquiry)
            queries = plan.get("queries", [inquiry])
            if mode == "standard":
                queries = queries[:2]

        if cancel_check and cancel_check():
            return {"cancelled": True, "answer": "Research cancelled."}

        # 2. Search Step
        update("searching", f"Searching web with {len(queries)} research queries...")
        search_results = self.search_mgr.search_multi_queries(
            queries, max_total=6 if mode == "deep" else 4
        )

        if not search_results:
            # Fallback if search returned no direct links
            return {
                "ok": False,
                "spoken_answer": "I searched the web, sir, but could not retrieve matching sources at this time.",
                "markdown_report": f"No web sources found for: {inquiry}",
                "sources": [],
                "citations_used": [],
            }

        if cancel_check and cancel_check():
            return {"cancelled": True, "answer": "Research cancelled."}

        # 3. Source Reading Step
        urls_to_read = [r["url"] for r in search_results if r.get("url")]
        update("reading", f"Reading content from {len(urls_to_read[:4])} relevant websites...")

        extracted_sources = self.reader.read_sources(
            urls_to_read, max_sources=4 if mode == "deep" else 2
        )

        # Merge snippets as fallback if extraction was empty
        if not extracted_sources:
            extracted_sources = [
                {
                    "url": r["url"],
                    "title": r.get("title", ""),
                    "text": r.get("snippet", ""),
                    "date": r.get("publishedDate", ""),
                    "success": True,
                }
                for r in search_results[:3]
            ]

        # 4. Ranking & Verification Step
        update("verifying", "Evaluating source authority and cross-checking facts...")
        ranked_sources = self.ranker.rank_sources(extracted_sources, inquiry)
        contradictions = self.verifier.detect_contradictions(ranked_sources)

        if cancel_check and cancel_check():
            return {"cancelled": True, "answer": "Research cancelled."}

        # 5. Synthesis Step
        update("synthesizing", "Synthesizing comprehensive research report with citations...")
        citation_mgr = CitationManager(ranked_sources)
        prompt_sources = citation_mgr.format_sources_for_prompt()

        user_prompt = (
            f"User Inquiry: {inquiry}\n\n"
            f"Retrieved Web Sources:\n{prompt_sources}\n\n"
            "Produce the research report following all synthesis instructions, with exact [n] citations and a <spoken> summary."
        )

        messages = [
            {"role": "system", "content": RESEARCH_SYNTHESIS_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        raw_synthesis = self.ollama.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=600 if mode == "deep" else 350,
        )

        # 6. Assembly Step
        final_data = ReportGenerator.assemble_report(
            raw_synthesis, citation_mgr, contradictions=contradictions
        )
        final_data["ok"] = True
        final_data["mode"] = mode
        final_data["queries_used"] = queries

        update("completed", "Research completed successfully.")
        return final_data


_agent_instance: Optional[ResearchAgent] = None


def get_research_agent() -> ResearchAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ResearchAgent()
    return _agent_instance
