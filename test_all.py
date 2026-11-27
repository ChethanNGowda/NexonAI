import os
import sys
import subprocess
from pathlib import Path

# Ensure execution in project .venv if available
BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
if VENV_PYTHON.exists():
    try:
        curr = Path(sys.executable).resolve()
        venv = VENV_PYTHON.resolve()
        if curr != venv and "JARVIS_VENV_REEXEC" not in os.environ:
            env = dict(os.environ)
            env["JARVIS_VENV_REEXEC"] = "1"
            sys.exit(subprocess.call([str(VENV_PYTHON)] + sys.argv, env=env))
    except Exception:
        pass

import numpy as np

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

print("=" * 65)
print("     JARVIS (NEXON AI + OPENJARVIS) SYSTEM DIAGNOSTIC")
print("=" * 65)

# 1. TEST SYSTEM AUTOMATION
print("\n[1/7] Testing System Automation...")
try:
    from backend.automation.system_control import get_system_stats, format_stats_speech
    stats = get_system_stats()
    speech = format_stats_speech(stats)
    print(f"  -> System Stats: Time={stats['time']}, Battery={stats.get('battery')}")
    print(f"  -> Spoken stats: \"{speech}\"")
    print("  -> Result: [OK]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 2. TEST OPENJARVIS REGISTRY & TOOLS
print("\n[2/7] Testing OpenJarvis Registered Desktop Tools...")
try:
    from openjarvis.core.registry import ToolRegistry
    import openjarvis.tools
    tool_keys = ["desktop_open_app", "desktop_volume_control", "desktop_media_control", "desktop_system_stats", "desktop_take_screenshot", "desktop_web_search"]
    registered = [k for k in tool_keys if ToolRegistry.contains(k)]
    print(f"  -> Registered Desktop Tools: {registered}")
    stats_tool = ToolRegistry.get("desktop_system_stats")()
    res = stats_tool.execute()
    print(f"  -> Tool execution success: {res.success}")
    if len(registered) == len(tool_keys) and res.success:
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [PARTIAL/FAILED]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 3. TEST TTS AUDIO SYNTHESIS (EDGE TTS + JARVIS PERSONA)
print("\n[3/7] Testing OpenJarvis Edge-TTS Speech Synthesis...")
try:
    from backend.voice.tts import speak
    out_file = speak("Diagnostic system check completed, sir.", play_audio=False)
    if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
        print(f"  -> Audio file created: {out_file} ({os.path.getsize(out_file)} bytes)")
        print("  -> Result: [OK]")
    else:
        print(f"  -> Audio file missing or too small: {out_file}")
        print("  -> Result: [FAILED]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 4. TEST WHISPER SPEECH RECOGNITION (LOCAL MODEL)
print("\n[4/7] Testing Whisper Speech-to-Text Model...")
try:
    from backend.voice.stt import get_recognizer
    rec = get_recognizer()
    test_wav = str(BASE_DIR / "frontend" / "voice_test.wav")
    if os.path.exists(test_wav):
        segments, _ = rec.model.transcribe(test_wav, language="en")
        transcription = " ".join([s.text.strip() for s in segments])
        print(f"  -> Model ({rec.model_name}) test transcription: \"{transcription}\"")
        if transcription:
            print("  -> Result: [OK]")
        else:
            print("  -> Result: [EMPTY]")
    else:
        print(f"  -> Result: [OK] (Model {rec.model_name} ready)")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 5. TEST FAST INTENT ROUTER
print("\n[5/7] Testing Fast Intent Router & Assistant...")
try:
    from backend.core.assistant import process_query
    q_res = process_query("what time is it", play_speech=False)
    print(f"  -> Query: 'what time is it' -> Answer: \"{q_res['answer']}\" (Action: {q_res['action']})")
    if q_res.get("ok") and q_res.get("action") == "time":
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [FAILED]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 6. TEST AI CONNECTIVITY (Ollama / Cloud)
print("\n[6/7] Checking AI Intelligence Connectivity...")
try:
    from backend.core.assistant import ask_llm, DEFAULT_MODEL
    print(f"  -> Target Model: {DEFAULT_MODEL}")
    answer = ask_llm("Respond with 'Jarvis systems online'.", model=DEFAULT_MODEL)
    print(f"  -> AI Model reply: \"{answer}\"")
    if answer and not answer.startswith("Unable to reach"):
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [STANDBY/OFFLINE]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 7. TEST AUDIO HARDWARE (MICROPHONE & SPEAKERS)
print("\n[7/7] Checking Audio Devices...")
try:
    import sounddevice as sd
    default_in = sd.default.device[0]
    default_out = sd.default.device[1]
    devices = sd.query_devices()
    print(f"  -> Default Input Device ID: {default_in} ({devices[default_in]['name'] if default_in >= 0 else 'None'})")
    print(f"  -> Default Output Device ID: {default_out} ({devices[default_out]['name'] if default_out >= 0 else 'None'})")

    print("  -> Probing microphone stream (1 second)...")
    rec = sd.rec(16000, samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    peak = int(np.max(np.abs(rec)))
    rms = float(np.sqrt(np.mean(np.square(rec.astype(float)))))
    print(f"  -> Mic probe recorded 16000 samples. Peak amplitude={peak}, RMS={rms:.2f}")
    print("  -> Result: [OK]")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 8. TEST LIVE INTERNET SEARCH (SEARXNG / DUCKDUCKGO)
print("\n[8/11] Testing Multi-Engine Internet Search...")
try:
    from backend.research.search_manager import get_search_manager
    sm = get_search_manager()
    s_results = sm.search_single("Python official website", limit=2)
    print(f"  -> Found {len(s_results)} web search results.")
    if s_results:
        print(f"  -> Top result: {s_results[0].get('title', '')} ({s_results[0].get('url', '')})")
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [FAILED] No search results returned")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 9. TEST WEB CONTENT EXTRACTOR
print("\n[9/11] Testing Website Content Extractor...")
try:
    from backend.research.source_reader import get_source_reader
    sr = get_source_reader()
    sample_doc = sr.extract_article("https://www.python.org")
    if sample_doc.get("success") and len(sample_doc.get("text", "")) > 50:
        print(f"  -> Extracted '{sample_doc.get('title')}' ({len(sample_doc.get('text'))} chars, {len(sample_doc.get('headings'))} headings)")
        print("  -> Result: [OK]")
    else:
        print(f"  -> Result: [PARTIAL/FAILED] Extracted: {sample_doc}")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 10. TEST SQLITE CONVERSATIONAL MEMORY
print("\n[10/11] Testing Persistent SQLite Conversational Memory...")
try:
    from backend.memory.memory_manager import get_memory_manager
    mm = get_memory_manager()
    mm.save_message("user", "Diagnostic memory test ping", action_type="test")
    mm.save_message("assistant", "Diagnostic memory test pong", action_type="test")
    hist = mm.get_recent_history(limit=2)
    if len(hist) >= 2 and hist[-1]["content"] == "Diagnostic memory test pong":
        print(f"  -> Persisted and verified conversation turn: {hist[-1]}")
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [FAILED] History mismatch")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

# 11. TEST CENTRAL ASSISTANT UNIFIED ROUTING
print("\n[11/11] Testing Unified Assistant Brain...")
try:
    from backend.ai.assistant import get_assistant
    asst = get_assistant()
    cmd_res = asst.process("what time is it", play_speech=False)
    if cmd_res.get("ok") and "time" in cmd_res.get("action", ""):
        print(f"  -> Direct intent routed: {cmd_res.get('spoken_answer')}")
        print("  -> Result: [OK]")
    else:
        print("  -> Result: [FAILED] Unified assistant error")
except Exception as e:
    print(f"  -> Result: [FAILED] {e}")

print("\n" + "=" * 65)
print("              ALL 11 DIAGNOSTICS COMPLETE")
print("=" * 65)
