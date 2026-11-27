"""
JARVIS / PHOEBE - EMBEDDINGS & RETRIEVAL ENGINE
===============================================
Computes vector embeddings via local Ollama (nomic-embed-text)
and performs hybrid semantic retrieval across past research.
"""

import math
from typing import Any, Dict, List, Optional
from backend.ai.ollama_client import get_ollama_client


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return dot / (mag1 * mag2)


class RetrievalEngine:
    def __init__(self):
        self.ollama = get_ollama_client()

    def embed_text(self, text: str) -> Optional[List[float]]:
        """Compute embedding using local Ollama model (returns None on failure/timeout)."""
        if not text or not text.strip():
            return None
        try:
            return self.ollama.get_embedding(text)
        except Exception:
            return None

    @staticmethod
    def _dedupe_candidates(candidate_texts: List[str]) -> List[str]:
        """Normalize and deduplicate candidate strings while preserving order."""
        seen = set()
        unique = []
        for raw in candidate_texts:
            cleaned = (raw or "").strip()
            if not cleaned:
                continue
            key = " ".join(cleaned.lower().split())
            if key not in seen:
                seen.add(key)
                unique.append(cleaned)
        return unique

    @staticmethod
    def _keyword_rank(query: str, unique_candidates: List[str], top_k: int) -> List[Dict[str, Any]]:
        """Fallback keyword-overlap ranking when embeddings are unavailable."""
        q_words = {w.strip(".,!?;:\"'()[]{}") for w in query.lower().split() if len(w.strip(".,!?;:\"'()[]{}")) > 2}
        if not q_words:
            q_words = {w for w in query.lower().split() if w}
        scored = []
        for text in unique_candidates:
            lower = text.lower()
            match_count = sum(1 for w in q_words if w in lower)
            if match_count > 0:
                scored.append({"text": text, "score": float(match_count)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def find_relevant_context(
        self,
        query: str,
        candidate_texts: List[str],
        top_k: int = 3,
        min_similarity: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """Rank candidate texts by semantic similarity, with keyword fallback."""
        clean_query = (query or "").strip()
        if not clean_query or top_k <= 0:
            return []

        unique_candidates = self._dedupe_candidates(candidate_texts)
        if not unique_candidates:
            return []

        query_vec = self.embed_text(clean_query)
        if not query_vec:
            return self._keyword_rank(clean_query, unique_candidates, top_k)

        scored = []
        any_embedded = False
        for text in unique_candidates:
            t_vec = self.embed_text(text)
            if t_vec:
                any_embedded = True
                sim = cosine_similarity(query_vec, t_vec)
                if sim >= min_similarity:
                    scored.append({"text": text, "score": sim})

        if not any_embedded:
            return self._keyword_rank(clean_query, unique_candidates, top_k)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


_retrieval_instance: Optional[RetrievalEngine] = None


def get_retrieval_engine() -> RetrievalEngine:
    global _retrieval_instance
    if _retrieval_instance is None:
        _retrieval_instance = RetrievalEngine()
    return _retrieval_instance
