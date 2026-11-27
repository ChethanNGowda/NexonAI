"""
JARVIS - Multi-AI Client Connector
====================================
Supports routing queries to multiple AI providers:
  - Ollama (local, default)   -> qwen3:8b or any local model
  - OpenAI                    -> gpt-4o, gpt-4o-mini
  - Anthropic Claude          -> claude-3-5-sonnet, claude-3-haiku
  - Google Gemini             -> gemini-1.5-flash, gemini-1.5-pro
  - OpenRouter                -> any model via OpenAI-compatible API

Configuration via environment variables in .env:
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
  GOOGLE_API_KEY=...
  OPENROUTER_API_KEY=...
  JARVIS_AI_CLIENT=ollama  # default: "ollama" | "openai" | "claude" | "gemini" | "openrouter"
  JARVIS_AI_MODEL=qwen3:8b # optional model override
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Load .env from project root
from dotenv import load_dotenv
_ROOT = Path(__file__).resolve().parent.parent.parent
_env_path = _ROOT / ".env"
_env_frontend = _ROOT / "frontend" / ".env"
load_dotenv(dotenv_path=_env_path)
load_dotenv(dotenv_path=_env_frontend, override=False)


JARVIS_CLIENT = os.getenv("JARVIS_AI_CLIENT", "ollama").lower().strip()
JARVIS_MODEL  = os.getenv("JARVIS_AI_MODEL", "").strip()

DEFAULT_MODELS = {
    "ollama":      "qwen3-vl:4b",
    "openai":      "gpt-4o-mini",
    "claude":      "claude-3-5-haiku-20241022",
    "gemini":      "gemini-1.5-flash",
    "openrouter":  "openai/gpt-4o-mini",
}


def _detect_ollama_model() -> str:
    """Auto-detect downloaded Ollama model from local instance."""
    try:
        import urllib.request
        import json
        req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        data = json.loads(req.read().decode())
        names = [m.get("name", "") for m in data.get("models", [])]
        for pref in ["qwen3-vl:4b", "qwen3.5:4b", "qwen3:8b"]:
            for n in names:
                if pref in n:
                    return n
        for n in names:
            if "embed" not in n:
                return n
    except Exception:
        pass
    return "qwen3-vl:4b"


def _resolve_model(provider: str) -> str:
    if JARVIS_MODEL:
        return JARVIS_MODEL
    if provider == "ollama":
        return _detect_ollama_model()
    return DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def _clean_response(content: str) -> str:
    import re
    if not content:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content)
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1]
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned)
    return cleaned.strip()


def _chat_ollama(messages: list, model: str) -> str:
    try:
        import ollama
        # For reasoning models (e.g. qwen3, qwen3.5, deepseek), append an assistant prefill '</think>'
        # if the last message is a user message, so the model immediately outputs the answer without wasting tokens thinking.
        ollama_msgs = [dict(m) for m in messages]
        if ollama_msgs and ollama_msgs[-1].get("role") == "user":
            ollama_msgs.append({"role": "assistant", "content": "</think>"})

        resp = ollama.chat(model=model, messages=ollama_msgs, options={"num_predict": 150, "temperature": 0.5})
        raw = resp.get("message", {}).get("content", "").strip()
        if not raw:
            # Fallback to thinking or raw if content was empty
            raw = resp.get("message", {}).get("thinking", "").strip()
        return _clean_response(raw)
    except Exception as e:
        return f"Ollama error: {e}"


def _chat_openai(messages: list, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "OpenAI API key not set. Add OPENAI_API_KEY to your .env file, sir."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI error: {e}"


def _chat_claude(messages: list, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "Anthropic API key not set. Add ANTHROPIC_API_KEY to your .env file, sir."
    try:
        import anthropic
        # Separate system prompt from conversation messages
        system_content = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_content += m["content"] + "\n"
            else:
                conv_messages.append({"role": m["role"], "content": m["content"]})

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_content.strip() or "You are JARVIS, a helpful AI assistant.",
            messages=conv_messages,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Claude error: {e}"


def _chat_gemini(messages: list, model: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return "Google API key not set. Add GOOGLE_API_KEY to your .env file, sir."
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        system_instruction = "\n".join(system_parts) if system_parts else None

        gmodel = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_instruction,
        )

        # Build history from conversation (skip system messages)
        history = []
        conv = [m for m in messages if m["role"] != "system"]
        for m in conv[:-1]:
            role = "user" if m["role"] == "user" else "model"
            history.append({"role": role, "parts": [m["content"]]})

        chat = gmodel.start_chat(history=history)
        last_user = conv[-1]["content"] if conv else "Hello"
        resp = chat.send_message(last_user)
        return resp.text.strip()
    except Exception as e:
        return f"Gemini error: {e}"


def _chat_openrouter(messages: list, model: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "OpenRouter API key not set. Add OPENROUTER_API_KEY to your .env file, sir."
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "https://nexon-jarvis.local", "X-Title": "Jarvis AI"},
        )
        resp = client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenRouter error: {e}"


PROVIDER_MAP = {
    "ollama":     _chat_ollama,
    "openai":     _chat_openai,
    "claude":     _chat_claude,
    "anthropic":  _chat_claude,
    "gemini":     _chat_gemini,
    "google":     _chat_gemini,
    "openrouter": _chat_openrouter,
}


def chat(
    messages: list,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Send messages to the configured AI provider and return the response.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        provider: Override provider ('ollama','openai','claude','gemini','openrouter').
        model: Override model name.

    Returns:
        str: AI response content.
    """
    provider = (provider or JARVIS_CLIENT).lower().strip()
    model = model or _resolve_model(provider)

    fn = PROVIDER_MAP.get(provider)
    if fn is None:
        return f"Unknown AI provider '{provider}'. Choose from: {', '.join(PROVIDER_MAP.keys())}, sir."

    return fn(messages, model)


def list_providers() -> list:
    """Return list of supported AI provider names."""
    return list(set(PROVIDER_MAP.keys()))


def active_provider() -> dict:
    """Return info about the current active provider and model."""
    p = JARVIS_CLIENT
    m = _resolve_model(p)
    return {"provider": p, "model": m}


if __name__ == "__main__":
    info = active_provider()
    print(f"Active provider: {info['provider']} | Model: {info['model']}")
    test_messages = [
        {"role": "system", "content": "You are JARVIS, a helpful AI assistant. Keep replies to one sentence."},
        {"role": "user", "content": "Who are you?"},
    ]
    print("Testing:", chat(test_messages))
