"""
JARVIS / PHOEBE - CITATION MANAGER & REPORT GENERATOR
=====================================================
Manages citation indices [1], [2], validates references against
retrieved sources, and formats Gemini-style research reports.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class CitationManager:
    def __init__(self, sources: List[Dict[str, Any]]):
        self.sources = sources
        self.indexed_sources: List[Dict[str, Any]] = []
        for idx, s in enumerate(sources, start=1):
            s_dict = dict(s)
            s_dict["citation_id"] = idx
            self.indexed_sources.append(s_dict)

    def get_source_by_index(self, index: int) -> Dict[str, Any] | None:
        if 1 <= index <= len(self.indexed_sources):
            return self.indexed_sources[index - 1]
        return None

    def format_sources_for_prompt(self, max_chars_per_source: int = 1500) -> str:
        """Format sources with index labels for the LLM synthesis prompt."""
        lines = []
        for s in self.indexed_sources:
            cid = s["citation_id"]
            title = s.get("title", "Source")
            url = s.get("url", "")
            date = s.get("date", "")
            date_str = f" ({date})" if date else ""
            text = s.get("text", "")[:max_chars_per_source]

            lines.append(f"--- SOURCE [{cid}] ---\nTitle: {title}{date_str}\nURL: {url}\nContent:\n{text}\n")
        return "\n".join(lines)

    def format_bibliography(self) -> str:
        """Render markdown bibliography with verified clickable URLs."""
        if not self.indexed_sources:
            return ""

        lines = ["\n### Verified Sources & Citations"]
        for s in self.indexed_sources:
            cid = s["citation_id"]
            title = s.get("title", s.get("url", "Link")).replace("[", "").replace("]", "")
            url = s.get("url", "#")
            date = f" ({s['date']})" if s.get("date") else ""
            lines.append(f"- **[{cid}]** [{title}]({url}){date}")
        return "\n".join(lines)

    def validate_citations(self, text: str) -> List[int]:
        """Extract all cited numbers [1], [2] and ensure they exist."""
        found = [int(m) for m in re.findall(r"\[(\d+)\]", text)]
        valid = [n for n in found if 1 <= n <= len(self.indexed_sources)]
        return sorted(list(set(valid)))


class ReportGenerator:
    @staticmethod
    def extract_spoken_summary(raw_text: str) -> Tuple[str, str]:
        """
        Extract <spoken>...</spoken> tags if present, or generate
        a clean 1-2 sentence spoken reply for Edge TTS.
        """
        spoken_match = re.search(r"<spoken>(.*?)</spoken>", raw_text, re.DOTALL | re.IGNORECASE)
        if spoken_match:
            spoken = spoken_match.group(1).strip()
            # Remove spoken tag from main text
            report = re.sub(r"<spoken>.*?</spoken>", "", raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
            return spoken, report

        # Fallback: take first clean sentence
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_text) if s.strip() and not s.strip().startswith("#")]
        spoken = " ".join(sentences[:2]) if sentences else "Here is what I found from the research, sir."
        return spoken, raw_text

    @classmethod
    def assemble_report(
        cls,
        raw_llm_output: str,
        citation_mgr: CitationManager,
        contradictions: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Assemble full research response dict with spoken text, markdown, and sources."""
        spoken, clean_report = cls.extract_spoken_summary(raw_llm_output)

        # Append contradictions section if detected
        if contradictions:
            contradiction_block = "\n\n### Contradictions & Discrepancies\n" + "\n".join(
                f"- {c}" for c in contradictions
            )
            clean_report += contradiction_block

        # Append verified bibliography
        clean_report += "\n\n" + citation_mgr.format_bibliography()

        return {
            "spoken_answer": spoken,
            "markdown_report": clean_report,
            "sources": citation_mgr.indexed_sources,
            "citations_used": citation_mgr.validate_citations(clean_report),
        }
