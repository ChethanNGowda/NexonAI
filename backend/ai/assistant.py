"""
JARVIS / PHOEBE - UNIFIED CENTRAL AI ASSISTANT BRAIN
====================================================
The central orchestrator for NexonAI combining:
  - Local Ollama AI intelligence (qwen3-vl:4b / qwen3.5:4b / qwen3:8b)
  - Zero-latency Windows desktop automation & OpenJarvis tools
  - Gemini-style Deep Research with verified citations & SearXNG search
  - Persistent conversational memory & preferences (SQLite)
  - Natural British voice synthesis via Microsoft Edge TTS
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Pre-load truststore for Windows HTTPS certs
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from backend.ai.intent_router import classify_intent
from backend.ai.ollama_client import get_ollama_client
from backend.ai.prompts import get_system_prompt
from backend.core.assistant import handle_fast_intent
from backend.memory.memory_manager import get_memory_manager
from backend.research.research_agent import get_research_agent
from backend.voice.tts import speak, set_speech_rate, set_speech_volume

logger = logging.getLogger(__name__)


class CentralAssistant:
    def __init__(self):
        self.ollama = get_ollama_client()
        self.memory = get_memory_manager()
        self.research_agent = get_research_agent()

    def process(
        self,
        query: str,
        play_speech: bool = True,
        force_mode: Optional[str] = None,  # "chat", "quick_search", "deep_research"
        progress_callback: Optional[Callable[[str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified processing pipeline:
        Routes intent, executes action/research/LLM, persists to memory, and produces TTS speech.
        """
        clean_text = query.strip()
        if not clean_text:
            return {"ok": False, "error": "No input received."}

        # Determine mode / intent
        if force_mode:
            intent_type = force_mode
            cleaned_query = clean_text
        else:
            intent_type, cleaned_query = classify_intent(clean_text)

        # 1. Desktop Automation (Instant Zero-Latency Execution)
        if intent_type == "desktop":
            fast_res = handle_fast_intent(clean_text)
            if fast_res is not None:
                action_name, answer = fast_res
                audio_path = ""
                if play_speech and answer:
                    audio_path = speak(answer, play_audio=True)

                self.memory.save_message("user", clean_text, action_type=action_name)
                self.memory.save_message("assistant", answer, action_type=action_name)

                return {
                    "ok": True,
                    "action": action_name,
                    "query": clean_text,
                    "spoken_answer": answer,
                    "markdown_report": answer,
                    "sources": [],
                    "audio_path": audio_path,
                    "is_exit": (action_name == "exit"),
                }

        # 2. Deep Research / Quick Search Workflow
        if intent_type in {"deep_research", "quick_search"}:
            mode = "deep" if intent_type == "deep_research" else "quick"
            research_res = self.research_agent.run_research(
                inquiry=cleaned_query,
                mode=mode,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

            spoken_text = research_res.get("spoken_answer", "")
            markdown = research_res.get("markdown_report", "")
            sources = research_res.get("sources", [])

            audio_path = ""
            if play_speech and spoken_text:
                audio_path = speak(spoken_text, play_audio=True)

            # Persist research report and conversation turns
            self.memory.save_message("user", clean_text, action_type=intent_type)
            self.memory.save_message("assistant", spoken_text, action_type=intent_type)
            self.memory.save_research_report(clean_text, spoken_text, markdown, sources)

            return {
                "ok": True,
                "action": intent_type,
                "query": clean_text,
                "spoken_answer": spoken_text,
                "markdown_report": markdown,
                "sources": sources,
                "audio_path": audio_path,
                "is_exit": False,
            }

        # 3. Conversational AI Chat via Local Ollama
        system_instruction = get_system_prompt()
        history = self.memory.get_recent_history(limit=6)

        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": clean_text})

        answer = self.ollama.chat(
            messages=messages,
            model=model_override,
            temperature=0.5,
            max_tokens=250,
        )

        audio_path = ""
        if play_speech and answer:
            audio_path = speak(answer, play_audio=True)

        self.memory.save_message("user", clean_text, action_type="chat")
        self.memory.save_message("assistant", answer, action_type="chat")

        return {
            "ok": True,
            "action": "chat",
            "query": clean_text,
            "spoken_answer": answer,
            "markdown_report": answer,
            "sources": [],
            "audio_path": audio_path,
            "is_exit": False,
        }


_central_assistant: Optional[CentralAssistant] = None


def get_assistant() -> CentralAssistant:
    global _central_assistant
    if _central_assistant is None:
        _central_assistant = CentralAssistant()
    return _central_assistant


UnifiedAssistant = CentralAssistant


def main():
    parser = argparse.ArgumentParser(description="Phoebe / Jarvis Central Assistant")
    parser.add_argument("--ask", type=str, help="Process a user query or command")
    parser.add_argument("--research", type=str, help="Run deep research on a topic")
    parser.add_argument("--speak", action="store_true", help="Play audio response aloud")
    parser.add_argument("--rate", type=float, default=None, help="Speech rate multiplier (0.5-2.0)")
    parser.add_argument("--volume", type=int, default=None, help="Speech volume (0-100)")
    parser.add_argument("--model", type=str, default=None, help="Ollama model override")
    parser.add_argument("--models", action="store_true", help="List installed local Ollama models")
    parser.add_argument("--clear-memory", action="store_true", help="Clear conversational memory")
    parser.add_argument("--health", action="store_true", help="System health diagnostic")
    args = parser.parse_args()

    if args.rate is not None:
        set_speech_rate(args.rate)
    if args.volume is not None:
        set_speech_volume(args.volume)

    assistant = get_assistant()

    if args.models:
        models = assistant.ollama.get_installed_model_names()
        print(json.dumps({"ok": True, "installed_models": models}))
        return 0

    if args.clear_memory:
        assistant.memory.clear_all()
        print(json.dumps({"ok": True, "message": "Memory cleared."}))
        return 0

    if args.health:
        from backend.automation.system_control import get_system_stats
        stats = get_system_stats()
        ollama_ok = assistant.ollama.is_available()
        print(json.dumps({
            "ok": True,
            "assistant": "Phoebe / Jarvis",
            "ollama_connected": ollama_ok,
            "stats": stats,
        }))
        return 0

    if args.research:
        def on_prog(step, detail):
            print(f"[PROGRESS] {step}: {detail}", file=sys.stderr)

        res = assistant.process(
            args.research,
            play_speech=args.speak,
            force_mode="deep_research",
            progress_callback=on_prog,
            model_override=args.model,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.ask:
        res = assistant.process(args.ask, play_speech=args.speak, model_override=args.model)
        print(json.dumps(res))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
