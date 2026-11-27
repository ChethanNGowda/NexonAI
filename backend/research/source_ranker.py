"""
JARVIS / PHOEBE - SOURCE RANKER & VERIFIER
==========================================
Evaluates retrieved sources for credibility, recency, relevance,
and cross-source consensus vs. contradiction.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

AUTHORITATIVE_DOMAINS = {
    "docs.", "github.com", "wikipedia.org", "arxiv.org", "python.org",
    "microsoft.com", "mozilla.org", "nist.gov", "nature.com", "ieee.org"
}


class SourceRanker:
    def score_source(self, source: Dict[str, Any], query_terms: List[str]) -> float:
        """Calculate quality and relevance score for a source."""
        score = 1.0
        url = source.get("url", "").lower()
        title = source.get("title", "").lower()
        text = source.get("text", "").lower()

        # Domain authority boost
        if any(dom in url for dom in AUTHORITATIVE_DOMAINS):
            score += 2.0

        # Term frequency boost
        for term in query_terms:
            t = term.lower()
            if len(t) < 3:
                continue
            if t in title:
                score += 1.5
            if t in text:
                score += min(text.count(t) * 0.1, 1.5)

        # Date recency bonus
        if source.get("date"):
            score += 0.5

        # Content richness
        if len(source.get("text", "")) > 400:
            score += 1.0

        return score

    def rank_sources(self, sources: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Rank and return sources sorted by credibility and relevance."""
        terms = [w for w in re.split(r"\W+", query) if len(w) > 2]
        scored = []
        for s in sources:
            sc = self.score_source(s, terms)
            s_copy = dict(s)
            s_copy["relevance_score"] = sc
            scored.append((sc, s_copy))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored]


class SourceVerifier:
    def detect_contradictions(self, sources: List[Dict[str, Any]]) -> List[str]:
        """
        Scan multiple sources for obvious numerical or date disagreements.
        """
        contradictions = []
        if len(sources) < 2:
            return contradictions

        # Simple cross-examination of publication years / dates
        dates = [s.get("date") for s in sources if s.get("date")]
        years = set()
        for d in dates:
            m = re.search(r"\b(20\d\d)\b", d)
            if m:
                years.add(m.group(1))

        if len(years) > 1 and max(int(y) for y in years) - min(int(y) for y in years) >= 2:
            contradictions.append(
                f"Information spans multiple years ({', '.join(sorted(years))}); check recent source dates."
            )

        return contradictions
