import os
import re
import sys
import json
import argparse
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.automation.system_control import (
    open_app,
    close_app,
    list_running_apps,
    open_user_folder,
    get_recent_files,
    open_latest_file,
    lock_workstation,
    minimize_all_windows,
    get_clipboard_text,
    set_clipboard_text,
    get_gpu_stats,
    get_all_disks,
    control_volume,
    control_media,
    search_web,
    search_youtube,
    open_url,
    take_screenshot,
    get_system_stats,
    format_stats_speech,
)
from backend.voice.tts import speak

# ============================================================
# JARVIS - CORE INTELLIGENCE & INTENT ROUTING ENGINE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPT_FILE = BASE_DIR / "config" / "system_prompt.txt"
DEFAULT_MODEL = os.getenv("JARVIS_AI_MODEL", "qwen3-vl:4b")

WAKE_WORDS = [
    "phoebe", "hey phoebe", "hi phoebe", "ok phoebe",
    "jarvis", "hey jarvis", "hi jarvis", "ok jarvis", "bob"
]

FALLBACK_SYSTEM_PROMPT = """
You are JARVIS, an advanced AI assistant inspired by Iron Man, serving Chethan on a local Windows PC.
Address the user naturally as 'sir'. Keep replies conversational, concise, and crisp (1-3 sentences),
ready to be spoken aloud through speakers. Never use markdown formatting or bullet points.
"""

# In-memory conversation context for multi-turn dialogue
_conversation_history = []


def load_system_prompt() -> str:
    """Load system prompt from config or return fallback."""
    try:
        content = PROMPT_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
    except OSError:
        pass
    return FALLBACK_SYSTEM_PROMPT.strip()


def check_wake_word(text: str) -> Tuple[bool, str]:
    """
    Check if utterance begins with or contains a wake word.
    Returns (has_wake_word, cleaned_prompt).
    """
    lower = text.lower().strip()

    for wake in WAKE_WORDS:
        pattern = rf"\b{re.escape(wake)}\b"
        if re.search(pattern, lower):
            # Remove wake word from text
            cleaned = re.sub(pattern, "", lower, flags=re.IGNORECASE).strip()
            # Clean leading punctuation
            cleaned = re.sub(r"^[,.!?\s]+", "", cleaned).strip()
            return True, cleaned

    return False, lower


def _authorize_or_block(action: str, target: str = "") -> Optional[Tuple[str, str]]:
    """Return an error tuple if blocked by AutomationGuard, else None."""
    from backend.automation.guard import get_automation_guard
    decision = get_automation_guard().authorize_safe_action(action, target)
    if not decision.allowed:
        return "blocked", decision.message
    return None


def handle_fast_intent(query: str) -> Optional[Tuple[str, str]]:
    """
    Evaluate instant zero-latency actions through the centralized AutomationGuard.
    Returns (action_type, response_text) or None if no direct action matched.
    """
    from backend.automation.guard import (
        get_automation_guard,
        reset_emergency_stop,
        trigger_emergency_stop,
    )
    from backend.automation.system_control import (
        close_app_guarded,
        execute_approved_command_guarded,
        lock_workstation_guarded,
    )

    q = query.lower().strip(" \t\r\n.?!,;:'\"")
    guard = get_automation_guard()

    # 0. Emergency Stop & Confirmation Controls
    if q in {"emergency stop", "trigger emergency stop", "stop all automation", "halt automation"}:
        res = trigger_emergency_stop("User requested emergency stop")
        return "emergency_stop", res["message"]

    if q in {"reset emergency stop", "resume automation", "clear emergency stop"}:
        res = reset_emergency_stop(authorized=True)
        return "reset_emergency_stop", res["message"]

    confirm_match = re.match(r"^(?:confirm|yes proceed|approve)(?:\s+([a-f0-9]{6,16}))?$", q)
    if confirm_match and (confirm_match.group(1) or guard.get_latest_pending_id()):
        cid = confirm_match.group(1)
        decision = guard.confirm_action(confirmation_id=cid)
        return ("confirm_action" if decision.allowed else "blocked"), decision.message

    deny_match = re.match(r"^(?:deny|cancel action|abort|reject)(?:\s+([a-f0-9]{6,16}))?$", q)
    if deny_match and (deny_match.group(1) or guard.get_latest_pending_id()):
        cid = deny_match.group(1)
        decision = guard.deny_action(confirmation_id=cid)
        return "deny_action", decision.message

    # 1. Exit / Shutdown
    if q in {"exit", "quit", "goodbye", "bye", "shutdown", "sleep", "stop", "go to sleep"}:
        return "exit", "Goodbye sir. I will be here whenever you need me."

    # 2. Greetings
    if q in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        return "greeting", "Hello sir. All systems are operational. What can I do for you?"

    # 3. Identity
    if "who are you" in q or "your name" in q:
        return "identity", "I am JARVIS, your personal desktop artificial intelligence, sir."

    # 4. Time & Date
    if "time" in q and any(w in q for w in ["what", "tell", "current", "is", "whats", "now"]):
        blocked = _authorize_or_block("time", "system_clock")
        if blocked:
            return blocked
        stats = get_system_stats()
        return "time", f"It is currently {stats['time']}, sir."

    if any(w in q for w in ["date", "day is it", "what day", "today's date", "todays date"]):
        blocked = _authorize_or_block("date", "system_clock")
        if blocked:
            return blocked
        stats = get_system_stats()
        return "date", f"Today is {stats['date']}, sir."

    # 5. System & Battery Diagnostics
    if any(k in q for k in ["battery", "power level", "charging status", "how much charge"]):
        blocked = _authorize_or_block("battery", "power")
        if blocked:
            return blocked
        stats = get_system_stats()
        if stats.get("battery"):
            bat = stats["battery"]
            state = "plugged in and charging" if bat["plugged"] else "discharging"
            return "battery", f"The battery is currently at {bat['percent']} percent and {state}, sir."
        return "battery", "Battery information is unavailable on this device, sir."

    if any(k in q for k in ["system status", "hardware status", "system diagnostics", "cpu", "ram", "system stats", "performance"]):
        blocked = _authorize_or_block("diagnostics", "system")
        if blocked:
            return blocked
        stats = get_system_stats()
        return "diagnostics", format_stats_speech(stats)

    # 6. Volume Control
    if "volume up" in q or "raise volume" in q or "increase volume" in q or "louder" in q:
        ok, msg = control_volume("up")
        return "volume_up", msg

    if "volume down" in q or "lower volume" in q or "decrease volume" in q or "quieter" in q:
        ok, msg = control_volume("down")
        return "volume_down", msg

    if "mute" in q or "unmute" in q or "silence audio" in q:
        ok, msg = control_volume("mute")
        return "volume_mute", msg

    # 7. Media Controls
    if "pause music" in q or "pause" in q or "play music" in q or "resume music" in q:
        ok, msg = control_media("play_pause")
        return "media_toggle", msg

    if "next song" in q or "next track" in q or "skip song" in q or "skip track" in q:
        ok, msg = control_media("next")
        return "media_next", msg

    if "previous song" in q or "previous track" in q:
        ok, msg = control_media("previous")
        return "media_prev", msg

    # 8. Screenshot
    if "screenshot" in q or "capture screen" in q:
        blocked = _authorize_or_block("screenshot", "display")
        if blocked:
            return blocked
        ok, msg = take_screenshot()
        return "screenshot", msg

    # 8b. Spotify Direct Search & Play
    spotify_search = re.search(r"(?:play|search)\s+(.+?)\s+on spotify", q)
    if not spotify_search:
        spotify_search = re.search(r"spotify\s+(?:search|play)\s+(.+)", q)
    if spotify_search:
        track = spotify_search.group(1).strip(" \t\r\n.?!,;:'\"")
        try:
            os.startfile(f"spotify:search:{urllib.parse.quote(track) if 'urllib' in globals() else track}")
            return "spotify_search", f"Searching for '{track}' on Spotify, sir."
        except Exception as e:
            return "spotify_search", f"Could not open Spotify: {e}"

    # 8c. Discord Chat / Message Intent
    discord_post = re.search(r"(?:send message to discord|post to discord|discord message|send discord message|tell discord)\s*[:\s]\s*(.+)", q)
    if discord_post:
        msg_body = discord_post.group(1).strip()
        from backend.integrations.discord_client import send_discord_webhook
        res = send_discord_webhook(content=msg_body)
        if res.get("ok"):
            return "discord_post", f"Message posted to Discord: '{msg_body[:60]}', sir."
        else:
            # Fallback: copy to clipboard and open Discord
            set_clipboard_text(msg_body)
            open_app("discord")
            return "discord_post", f"Copied message to clipboard and opened Discord, sir. ({res.get('error', 'Webhook not set')})"

    # 9. Web & YouTube Search
    search_youtube_match = re.search(r"(?:search youtube for|play on youtube|youtube search|youtube)\s+(.+)", q)
    if search_youtube_match:
        target = search_youtube_match.group(1).strip(" \t\r\n.?!,;:'\"")
        ok, msg = search_youtube(target)
        return "youtube_search", msg

    search_google_match = re.search(r"(?:search google for|search for|google search|google)\s+(.+)", q)
    if search_google_match:
        target = search_google_match.group(1).strip(" \t\r\n.?!,;:'\"")
        ok, msg = search_web(target)
        return "google_search", msg

    # 10. Screen Lock & Desktop Minimization
    if any(k in q for k in ["lock pc", "lock screen", "lock workstation", "lock computer", "lock my pc"]):
        decision = lock_workstation_guarded()
        return ("confirm_required" if decision.status == "pending_confirm" else "blocked"), decision.message

    if any(k in q for k in ["show desktop", "minimize all", "minimize windows", "hide windows", "minimize all windows"]):
        blocked = _authorize_or_block("show_desktop", "windows")
        if blocked:
            return blocked
        ok, msg = minimize_all_windows()
        return "show_desktop", msg

    # 11. Clipboard Inspection
    if any(k in q for k in ["what is in my clipboard", "what's in my clipboard", "read clipboard", "clipboard content", "check clipboard"]):
        blocked = _authorize_or_block("clipboard", "clipboard")
        if blocked:
            return blocked
        clip = get_clipboard_text()
        if clip:
            preview = clip[:150] + ("..." if len(clip) > 150 else "")
            return "clipboard", f"The clipboard contains: {preview}, sir."
        return "clipboard", "The clipboard is currently empty, sir."

    # 12. Hardware, GPU & Storage Diagnostics
    if any(k in q for k in ["gpu", "graphics card", "gpu status", "vram", "gpu temperature", "video card"]):
        blocked = _authorize_or_block("gpu", "nvidia")
        if blocked:
            return blocked
        gpu = get_gpu_stats()
        if gpu:
            return "gpu", f"The {gpu['name']} is at {gpu['temperature_c']} degrees Celsius, utilizing {gpu['memory_used_mb']} megabytes of VRAM, sir."
        return "gpu", "NVIDIA GPU metrics are currently unavailable, sir."

    if any(k in q for k in ["storage", "disk space", "hard drive", "free space", "drive c"]):
        blocked = _authorize_or_block("storage", "disks")
        if blocked:
            return blocked
        disks = get_all_disks()
        if disks:
            d0 = disks[0]
            return "storage", f"Drive {d0['drive']} has {d0['free_gb']} gigabytes free out of {d0['total_gb']} gigabytes, sir."
        return "storage", "Storage information is unavailable, sir."

    if any(k in q for k in ["running apps", "active apps", "what is running", "what apps are running", "open apps"]):
        blocked = _authorize_or_block("running_apps", "processes")
        if blocked:
            return blocked
        apps = list_running_apps(limit=6)
        if apps:
            names = [a['name'].replace('.exe', '') for a in apps]
            return "running_apps", f"Active applications include: {', '.join(names)}, sir."
        return "running_apps", "No user applications currently active, sir."

    # 13. User Folder Shortcuts & Recent Files
    if any(k in q for k in ["open latest download", "open recent download", "open last download"]):
        blocked = _authorize_or_block("open_latest", "downloads")
        if blocked:
            return blocked
        ok, msg = open_latest_file("downloads")
        return "open_latest", msg

    if any(k in q for k in ["what did i download", "recent downloads", "my downloads list"]):
        blocked = _authorize_or_block("recent_downloads", "downloads")
        if blocked:
            return blocked
        recent = get_recent_files("downloads", limit=3)
        if recent:
            names = [r["name"] for r in recent]
            return "recent_downloads", f"Recent downloads include: {', '.join(names)}, sir."
        return "recent_downloads", "No recent downloads found, sir."

    folder_match = re.search(r"^(?:open|show)\s+(?:my\s+)?(downloads|desktop|documents|pictures|videos|music|development|myfiles)\s*(?:folder)?$", q)
    if folder_match:
        target_folder = folder_match.group(1).strip()
        blocked = _authorize_or_block("open_folder", target_folder)
        if blocked:
            return blocked
        ok, msg = open_user_folder(target_folder)
        return "open_folder", msg

    # 13b. Approved Command Execution (requires validation & confirmation)
    cmd_match = re.search(r"^(?:run command|execute command)\s+(.+)", query.strip(), flags=re.IGNORECASE)
    if cmd_match:
        raw_cmd = cmd_match.group(1).strip()
        decision = execute_approved_command_guarded(raw_cmd)
        return ("confirm_required" if decision.status == "pending_confirm" else "blocked"), decision.message

    # 14. Close / Terminate Application (requires confirmation)
    close_match = re.search(r"^(?:close|quit|kill|stop|terminate)\s+(.+)", q)
    if close_match:
        target_app = close_match.group(1).strip(" \t\r\n.?!,;:'\"")
        if target_app not in {"music", "video", "listening"}:
            decision = close_app_guarded(target_app)
            return ("confirm_required" if decision.status == "pending_confirm" else "blocked"), decision.message

    # 15. Open App or Launch Game
    open_match = re.search(r"^(?:open|launch|start|play)\s+(.+)", q)
    if open_match:
        target = open_match.group(1).strip(" \t\r\n.?!,;:'\"")
        if target.endswith(".com") or target.endswith(".org") or target.endswith(".net") or target.startswith("http"):
            ok, msg = open_url(target)
            return "open_url", msg
        ok, msg = open_app(target)
        return "open_app", msg

    return None


def ask_llm(prompt: str, model: str = DEFAULT_MODEL, provider: Optional[str] = None) -> str:
    """Query configured AI provider (Ollama, OpenAI, Claude, Gemini, OpenRouter) with history."""
    global _conversation_history

    messages = [{"role": "system", "content": load_system_prompt()}]

    # Include recent context (last 6 messages)
    for turn in _conversation_history[-6:]:
        messages.append(turn)

    messages.append({"role": "user", "content": prompt})

    # 1. Try unified client connector
    try:
        from backend.ai.clients import chat as multi_chat
        content = multi_chat(messages, provider=provider, model=model if model != DEFAULT_MODEL else None)
        if content and not content.startswith("Ollama error:"):
            _conversation_history.append({"role": "user", "content": prompt})
            _conversation_history.append({"role": "assistant", "content": content})
            return content
    except Exception:
        pass

    # 2. Try direct Ollama
    try:
        import ollama
        ollama_msgs = [dict(m) for m in messages]
        if ollama_msgs and ollama_msgs[-1].get("role") == "user":
            ollama_msgs.append({"role": "assistant", "content": "</think>"})

        response = ollama.chat(model=model, messages=ollama_msgs, options={"num_predict": 150, "temperature": 0.5})
        content = response.get("message", {}).get("content", "").strip()
        if not content:
            content = response.get("message", {}).get("thinking", "").strip()

        if "<think>" in content:
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()
            else:
                content = re.sub(r"^<think>\s*", "", content).strip()

        if content:
            _conversation_history.append({"role": "user", "content": prompt})
            _conversation_history.append({"role": "assistant", "content": content})
            return content

        return "I am online, sir, but unable to generate a response at this moment."
    except Exception as e:
        return f"Unable to reach the local brain: {e}. Please ensure Ollama is running or configure an API key in your .env file, sir."


def ask_ollama(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Query local Ollama LLM (backwards compatible alias)."""
    return ask_llm(prompt, model=model)


def process_query(text: str, play_speech: bool = True, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """
    Full pipeline: processes intent, executes action or LLM query, and speaks result.
    """
    clean_text = text.strip()
    if not clean_text:
        return {"ok": False, "error": "No input received."}

    # Check for direct fast actions
    fast_result = handle_fast_intent(clean_text)

    if fast_result is not None:
        action_type, answer = fast_result
    else:
        # Route through Unified AI Brain (Live Web Search / Deep Research / Ollama with Memory)
        try:
            from backend.ai.assistant import UnifiedAssistant
            unified = UnifiedAssistant()
            u_res = unified.process(clean_text, play_speech=False, model_override=model)
            action_type = u_res.get("action", "llm")
            answer = u_res.get("spoken_answer") or u_res.get("markdown_report") or ""
            if not answer:
                answer = ask_llm(clean_text, model=model)
        except Exception:
            action_type = "llm"
            answer = ask_llm(clean_text, model=model)

    audio_path = ""
    if play_speech and answer:
        audio_path = speak(answer, play_audio=True)

    is_exit = (action_type == "exit")

    return {
        "ok": True,
        "action": action_type,
        "query": clean_text,
        "answer": answer,
        "audio_path": audio_path,
        "is_exit": is_exit,
    }


def main():
    parser = argparse.ArgumentParser(description="JARVIS Core Assistant")
    parser.add_argument("--ask", type=str, help="Process a user question or command")
    parser.add_argument("--speak", action="store_true", help="Speak the response aloud via TTS")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--health", action="store_true", help="Check assistant status")
    args = parser.parse_args()

    if args.health:
        stats = get_system_stats()
        print(json.dumps({"ok": True, "status": "nominal", "model": args.model, "stats": stats}))
        return 0

    if not args.ask:
        print(json.dumps({"ok": False, "error": "No prompt supplied."}))
        return 1

    result = process_query(args.ask, play_speech=args.speak, model=args.model)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
