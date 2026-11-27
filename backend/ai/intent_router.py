"""
JARVIS / PHOEBE - INTENT ROUTER
===============================
Classifies user queries into:
  - 'desktop': Fast zero-latency system control (apps, volume, media, stats)
  - 'deep_research': Multi-step investigation, comparison, technical research
  - 'quick_search': Current events, news, weather, quick web lookups
  - 'chat': Conversational AI reasoning, advice, explanation, assistance
"""

import re
from typing import Tuple


def classify_intent(query: str) -> Tuple[str, str]:
    """
    Classify query intent with priority rules.
    Returns (intent_type, cleaned_query).
    """
    q = query.strip()
    lower = q.lower().strip(" \t\r\n.?!,;:'\"")

    # 1. Deep Research Triggers
    deep_triggers = [
        r"^(?:deep research|research in detail|do research on|comprehensive report on|investigate)\s+(.+)",
        r"^(?:compare and analyze|multi-source research on|detailed comparison of)\s+(.+)",
    ]
    for pattern in deep_triggers:
        m = re.search(pattern, lower)
        if m:
            return "deep_research", m.group(1).strip()

    # 2. General Research & Comparison Triggers
    if any(k in lower for k in ["deep research", "research paper", "write a research report"]):
        return "deep_research", q

    # 3. Live Web Search & Daily News Triggers
    search_triggers = [
        r"^(?:search the web for|search for|google|web search)\s+(.+)",
        r"^(?:what is the latest on|current news about|latest updates on)\s+(.+)",
        r"^(?:news about|updates on)\s+(.+)",
    ]
    for pattern in search_triggers:
        m = re.search(pattern, lower)
        if m:
            return "quick_search", m.group(1).strip()

    # Daily news, sports & real-time world events
    news_keywords = [
        "daily news", "latest news", "today's news", "todays news", "news today",
        "top headlines", "news headlines", "world news", "tech news", "market news",
        "sports news", "sports updates", "cricket score", "cricket news", "ipl score",
        "football news", "football score", "premier league", "champions league", "la liga",
        "formula 1", "f1 race", "nba score", "tennis score", "match score",
        "what happened today", "what is happening today", "give me the news", "tell me the news",
        "weather in", "stock price of", "who won the", "score of", "who won"
    ]
    if any(k in lower for k in news_keywords):
        if lower in {"daily news", "news", "news today", "today's news", "todays news", "latest news", "give me the news", "tell me the news"}:
            return "quick_search", "top news headlines today"
        if lower in {"sports news", "latest sports news", "sports updates", "give me sports news"}:
            return "quick_search", "top sports news and scores today"
        return "quick_search", q

    # 4. Fast Desktop Intent check (pattern-only; avoids side effects before execution)
    desktop_prefixes = (
        "open ", "launch ", "start ", "play ", "close ", "quit ", "kill ", "stop ", "terminate ",
        "volume ", "raise volume", "lower volume", "increase volume", "decrease volume", "mute", "unmute",
        "pause", "resume music", "next song", "next track", "skip ", "previous song", "previous track",
        "screenshot", "capture screen", "lock pc", "lock screen", "lock workstation", "lock computer", "lock my pc",
        "show desktop", "minimize all", "minimize windows", "hide windows",
        "run command ", "execute command ",
        "emergency stop", "trigger emergency stop", "stop all automation", "halt automation",
        "reset emergency stop", "resume automation", "clear emergency stop",
        "confirm", "yes proceed", "approve", "deny", "cancel action", "abort", "reject",
        "what is in my clipboard", "what's in my clipboard", "read clipboard", "clipboard content", "check clipboard",
        "open latest download", "open recent download", "open last download",
        "what did i download", "recent downloads", "my downloads list",
    )
    desktop_exact = {"exit", "quit", "goodbye", "bye", "shutdown", "sleep", "stop", "go to sleep",
                     "hello", "hi", "hey", "good morning", "good afternoon", "good evening"}
    desktop_contains = (
        "who are you", "your name", "battery", "power level", "charging status", "how much charge",
        "system status", "hardware status", "system diagnostics", "system stats", "performance",
        "gpu", "graphics card", "vram", "video card", "storage", "disk space", "hard drive", "free space",
        "running apps", "active apps", "what is running", "what apps are running", "open apps",
        "search youtube for", "play on youtube", "youtube search", "search google for", "google search",
        "on spotify", "spotify search", "spotify play", "to discord", "discord message", "tell discord",
    )
    if (
        lower in desktop_exact
        or any(lower.startswith(p) for p in desktop_prefixes)
        or any(k in lower for k in desktop_contains)
        or ("time" in lower and any(w in lower for w in ("what", "tell", "current", "is", "whats", "now")))
        or any(w in lower for w in ("date", "day is it", "what day", "today's date", "todays date"))
    ):
        return "desktop", lower

    # 5. Default Conversational Chat
    return "chat", q
