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
        """Compute embedding using local Ollama model."""
        return self.ollama.get_embedding(text)

    def find_relevant_context(
        self, query: str, candidate_texts: List[str], top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Rank candidate texts by semantic similarity to the query."""
        query_vec = self.embed_text(query)
        if not query_vec:
            # Fallback to keyword matching
            q_words = set(query.lower().split())
            scored = []
            for t in candidate_texts:
                match_count = sum(1 for w in q_words if w in t.lower())
                scored.append({"text": t, "score": float(match_count)})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]

        scored = []
        for text in candidate_texts:
            t_vec = self.embed_text(text)
            sim = cosine_similarity(query_vec, t_vec) if t_vec else 0.0
            scored.append({"text": text, "score": sim})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


_retrieval_instance: Optional[RetrievalEngine] = None


def get_retrieval_engine() -> RetrievalEngine:
    global _retrieval_instance
    if _retrieval_instance is None:
        _retrieval_instance = RetrievalEngine()
    return _retrieval_instance
