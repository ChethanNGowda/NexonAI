"""
JARVIS / PHOEBE - CENTRAL PROMPT MANAGEMENT
===========================================
Single source of truth for all system prompts, research templates, and tool schemas.
Loads directly from config/system_prompt.txt.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_SYSTEM_PROMPT_PATH = _ROOT / "config" / "system_prompt.txt"

_CACHED_SYSTEM_PROMPT: str | None = None


def get_system_prompt() -> str:
    """Load and cache the central assistant personality from config/system_prompt.txt."""
    global _CACHED_SYSTEM_PROMPT
    if _CACHED_SYSTEM_PROMPT is not None:
        return _CACHED_SYSTEM_PROMPT

    if _SYSTEM_PROMPT_PATH.exists():
        try:
            content = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
            if content:
                _CACHED_SYSTEM_PROMPT = content
                return content
        except Exception:
            pass

    fallback = (
        "You are Phoebe, the highly intelligent AI assistant for NexonAI. "
        "Be helpful, conversational, accurate, and concise in spoken replies."
    )
    _CACHED_SYSTEM_PROMPT = fallback
    return fallback


def clear_prompt_cache():
    """Clear memory cache if system_prompt.txt is edited at runtime."""
    global _CACHED_SYSTEM_PROMPT
    _CACHED_SYSTEM_PROMPT = None


# Deep Research Planning Prompt
RESEARCH_PLANNER_SYSTEM = """You are the Research Planner for Phoebe (NexonAI).
Your job is to deconstruct a user's research request into a structured research plan.
Given the user's inquiry, produce:
1. A concise interpretation of what specific facts are needed.
2. Exactly 2 to 4 distinct, high-quality search queries targeting primary sources, official documentation, or recent news.
3. Key verification points (dates, versions, metrics, consensus vs disagreement).

Respond ONLY in valid JSON matching this schema:
{
  "focus": "string summary of the core question",
  "queries": ["query 1", "query 2", "query 3"],
  "verification_targets": ["key metric or fact to verify"]
}
"""

# Deep Research Synthesis Prompt
RESEARCH_SYNTHESIS_SYSTEM = """You are Phoebe, an elite research assistant.
You have been provided with scraped content from independent web sources regarding the user's question.

Guidelines for your research report:
1. Synthesize all verified information into an objective, deeply informative Markdown report.
2. Attribute every key factual claim to its source using bracketed numbers like [1], [2] corresponding to the sources list provided.
3. Never invent facts or citations. If sources disagree or evidence is missing, state it explicitly under a 'Contradictions & Open Questions' section.
4. Prefer primary sources and official documentation.
5. In addition to the detailed written report, provide a 1-to-2 sentence conversational summary suitable for speaking aloud.

Format your output as:
# Executive Summary
...

# Detailed Findings
...

# Source Comparison & Verification
...

# Spoken Summary
<spoken>1 to 2 sentences summarizing the direct answer</spoken>
"""

# Query Classification / Intent Prompt
INTENT_CLASSIFICATION_SYSTEM = """Classify the user's intent into exactly one category:
- 'desktop': App launch, volume, media, screenshot, system diagnostics.
- 'quick_search': Simple current fact lookup (e.g., weather, stock, sports score, release date).
- 'deep_research': Complex explanation, comparison, technical investigation, multi-source analysis.
- 'chat': Normal conversation, greeting, advice, reasoning, math, general knowledge.

Respond ONLY with the category word.
"""
