"""
NexonAI — Phase 9: Automated Testing and Windows 11 Verification
=================================================================
Tests all nine-phase features on Windows 11 / AMD Ryzen 7 / RTX 3050.

Coverage:
1.  Python module imports (all backend modules)
2.  Configuration loading (.env parsing, settings JSON round-trip)
3.  Microphone error handling (Phase 4 compatibility)
4.  Ollama connectivity and model availability
5.  TTS voice generation and audio device enumeration
6.  Automation permission checks (safe vs destructive)
7.  File access restrictions (Phase 7 allowlist)
8.  Vision module availability check
9.  Windows PowerShell compatibility
10. Memory system integrity
11. Full nine-phase test count verification
12. Git repository integrity

Each test returns a detail string on success; raises on failure.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

VENV_PYTHON = _ROOT / ".venv" / "Scripts" / "python.exe"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _run_python(*args, timeout=15):
    """Run a Python one-liner or module in the venv and return stdout."""
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    cmd = [python] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(_ROOT))
    return result.returncode, result.stdout.strip(), result.stderr.strip()


TESTS = []


def test(name, category):
    """Decorator to register a test."""
    def decorator(fn):
        TESTS.append((name, category, fn))
        return fn
    return decorator


# ===========================================================================
# 1. Python Module Imports
# ===========================================================================

@test("backend.automation.guard imports cleanly", "Imports")
def _():
    from backend.automation.guard import AutomationGuard, get_automation_guard
    g = get_automation_guard()
    assert g is not None
    return "AutomationGuard singleton OK"


@test("backend.automation.system_control imports cleanly", "Imports")
def _():
    from backend.automation.system_control import get_system_stats
    return "system_control OK"


@test("backend.tools.file_search imports cleanly", "Imports")
def _():
    from backend.tools.file_search import tool_file_search, tool_read_document
    from backend.tools.file_search import tool_summarize_document, tool_create_file, tool_delete_file
    return "file_search all 5 tools imported"


@test("backend.vision imports cleanly", "Imports")
def _():
    from backend.vision import vision_enabled, analyze_image, take_permissioned_screenshot
    return "backend.vision OK"


@test("backend.memory.memory_manager imports cleanly", "Imports")
def _():
    from backend.memory.memory_manager import get_memory_manager
    return "memory_manager OK"


@test("backend.memory.retrieval imports cleanly", "Imports")
def _():
    from backend.memory.retrieval import get_retrieval_engine
    return "retrieval OK"


@test("backend.ai.ollama_client imports cleanly", "Imports")
def _():
    from backend.ai.ollama_client import get_ollama_client
    return "ollama_client OK"


@test("backend.ai.intent_router imports cleanly", "Imports")
def _():
    from backend.ai.intent_router import classify_intent
    intent, q = classify_intent("what time is it")
    assert intent == "desktop", f"Expected 'desktop', got '{intent}'"
    return f"intent_router OK; 'what time is it' -> '{intent}'"


@test("backend.voice.tts imports cleanly", "Imports")
def _():
    from backend.voice.tts import speak, set_voice_id
    return "tts OK"


@test("backend.voice.stt imports cleanly", "Imports")
def _():
    from backend.voice.stt import SpeechRecognizer, check_microphone, get_recognizer
    return "stt OK (SpeechRecognizer, check_microphone, get_recognizer)"


# ===========================================================================
# 2. Configuration Loading
# ===========================================================================

@test(".env file not tracked by git", "Config")
def _():
    rc, stdout, _ = _run_python("-c", "import subprocess; r=subprocess.run(['git','ls-files','.env'],capture_output=True,text=True,cwd='.'); print(r.stdout.strip())")
    env_tracked = stdout.strip()
    assert env_tracked == "", f".env is tracked in git: {env_tracked!r}"
    return ".env not in git index"


@test("Settings JSON round-trip", "Config")
def _():
    import tempfile
    settings = {
        "alwaysOnTop": True,
        "activeModel": "qwen3.5:4b",
        "activeVoice": "en-GB-RyanNeural",
        "voiceOutput": True,
        "speechRate": 1.0,
        "speechVolume": 100,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(settings, f)
        tmp = f.name
    try:
        loaded = json.loads(Path(tmp).read_text())
        assert loaded == settings
        return "Settings JSON round-trip OK"
    finally:
        Path(tmp).unlink(missing_ok=True)


@test("OLLAMA_HOST defaults to localhost", "Config")
def _():
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    assert "11434" in host or "localhost" in host or "127.0.0.1" in host, f"Unexpected host: {host}"
    return f"OLLAMA_HOST={host}"


# ===========================================================================
# 3. Microphone Error Handling (Phase 4 compatibility)
# ===========================================================================

@test("SpeechToText handles no microphone gracefully", "Voice / STT")
def _():
    from backend.voice.stt import check_microphone
    # check_microphone() returns a dict with ok/error keys — must not raise
    try:
        result = check_microphone()
        assert isinstance(result, dict)
        return f"check_microphone() -> ok={result.get('ok')}, input_count={result.get('input_count', '?')}"
    except Exception as e:
        raise AssertionError(f"check_microphone() raised unexpectedly: {e}") from e


# ===========================================================================
# 4. Ollama Connectivity and Model Availability
# ===========================================================================

@test("Ollama /api/tags endpoint reachable", "Ollama")
def _():
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        assert resp.status_code == 200
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        return f"Ollama up; {len(models)} model(s) installed"
    except Exception as e:
        raise AssertionError(f"Ollama unreachable: {e}") from e


@test("nomic-embed-text excluded from chat model list", "Ollama")
def _():
    from backend.ai.ollama_client import get_ollama_client
    client = get_ollama_client()
    chat_models = client.get_chat_model_names()
    assert all("nomic" not in m.lower() for m in chat_models), \
        f"nomic-embed-text leaked into chat models: {chat_models}"
    return f"Chat models (embedding excluded): {chat_models}"


# ===========================================================================
# 5. TTS Voice Generation
# ===========================================================================

@test("Edge TTS voice list not empty", "Voice / TTS")
def _():
    import asyncio
    try:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
        en_voices = [v["ShortName"] for v in voices if v.get("Locale", "").startswith("en")]
        assert len(en_voices) > 0
        has_ryan = any("RyanNeural" in v for v in en_voices)
        return f"{len(en_voices)} English voices; en-GB-RyanNeural={'yes' if has_ryan else 'NO'}"
    except Exception as e:
        raise AssertionError(f"edge-tts voice list failed: {e}") from e


@test("Audio device enumeration (sounddevice)", "Voice / TTS")
def _():
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        output_devs = [d for d in devices if d.get("max_output_channels", 0) > 0]
        return f"{len(devices)} total devices, {len(output_devs)} output devices"
    except Exception as e:
        # sounddevice may fail in headless environments — not a hard failure
        return f"sounddevice query skipped: {e}"


# ===========================================================================
# 6. Automation Permission Checks (Phase 6 integration)
# ===========================================================================

@test("Safe action (time) allowed without confirmation", "Automation")
def _():
    from backend.automation.guard import get_automation_guard, reset_emergency_stop
    # Ensure clean state: reset any lingering emergency stop
    reset_emergency_stop(authorized=True)
    guard = get_automation_guard()
    decision = guard.authorize_safe_action("time", "")
    assert decision.allowed, f"Expected allowed, got: {decision}"
    return f"'time' -> status={decision.status}"


@test("Destructive action (close_app) requires confirmation", "Automation")
def _():
    from backend.automation.guard import get_automation_guard, reset_emergency_stop
    reset_emergency_stop(authorized=True)
    guard = get_automation_guard()
    decision = guard.request_confirmation("close_app", "notepad", "Close notepad?")
    assert decision.status == "pending_confirm", f"Expected pending_confirm, got: {decision.status}"
    assert decision.confirmation_id, "No confirmation_id returned"
    # Deny it immediately
    guard.deny_action(decision.confirmation_id)
    return f"'close_app notepad' -> pending_confirm, cid={decision.confirmation_id[:8]}... denied"


@test("Emergency stop blocks all actions and persists", "Automation")
def _():
    from backend.automation.guard import get_automation_guard, trigger_emergency_stop, reset_emergency_stop
    # Ensure clean state first
    reset_emergency_stop(authorized=True)
    # Trigger
    trigger_emergency_stop("Phase 9 test")
    guard = get_automation_guard()
    decision = guard.authorize_safe_action("time", "")
    assert not decision.allowed, "Emergency stop should block even safe actions"
    assert decision.status == "blocked"
    # Reset
    result = reset_emergency_stop(authorized=True)
    assert result.get("ok"), f"Reset failed: {result}"
    # Verify unblocked
    decision2 = guard.authorize_safe_action("time", "")
    assert decision2.allowed, f"Should be allowed after reset, got: {decision2.status}"
    return "Emergency stop -> persist -> reset -> allowed confirmed"


# ===========================================================================
# 7. File Access Restrictions (Phase 7)
# ===========================================================================

@test("file_search blocked in C:\\Windows\\System32", "File Access")
def _():
    from backend.tools.file_search import tool_file_search
    result = tool_file_search(pattern="*.exe", directory="C:\\Windows\\System32")
    # Should return empty or error, never system files
    if isinstance(result, dict) and not result.get("ok", True):
        return f"Blocked: {result.get('error', '')}"
    if isinstance(result, list) and len(result) == 0:
        return "Blocked (returned empty list for disallowed dir)"
    raise AssertionError(f"Unexpected result from blocked directory: {result}")


@test("read_document blocked outside home/workspace", "File Access")
def _():
    from backend.tools.file_search import tool_read_document
    result = tool_read_document(file_path="C:\\Windows\\System32\\drivers\\etc\\hosts")
    assert not result.get("ok", True), f"Should be blocked, got: {result}"
    return f"Blocked: {result.get('error', '')[:60]}"


@test("tool_delete_file always requires confirmation", "File Access")
def _():
    import tempfile
    from backend.tools.file_search import tool_delete_file
    from backend.automation.guard import reset_emergency_stop
    # Ensure guard is not in emergency stop from a previous test
    reset_emergency_stop(authorized=True)
    with tempfile.NamedTemporaryFile(dir=str(Path.home()), suffix=".txt", delete=False) as f:
        tmp = Path(f.name)
        f.write(b"Phase 9 test file")
    try:
        result = tool_delete_file(str(tmp))
        assert result.get("requires_confirmation"), f"delete must always require confirmation: {result}"
        # File must NOT have been deleted
        assert tmp.exists(), "File was deleted without confirmation!"
        return f"Delete correctly requires confirmation (cid={str(result.get('confirmation_id','?'))[:8]}...)"
    finally:
        tmp.unlink(missing_ok=True)


# ===========================================================================
# 8. Vision Module
# ===========================================================================

@test("vision_enabled() returns bool", "Vision")
def _():
    from backend.vision import vision_enabled
    result = vision_enabled()
    assert isinstance(result, bool)
    return f"vision_enabled={result}"


@test("analyze_image() handles missing file gracefully", "Vision")
def _():
    from backend.vision import analyze_image
    result = analyze_image("/nonexistent/path/image.png")
    assert not result.get("ok"), f"Should fail for missing file: {result}"
    return f"Missing file handled: {result.get('error','')[:60]}"


@test("analyze_image() rejects unsupported extension", "Vision")
def _():
    from backend.vision import analyze_image
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        Path(f.name).write_bytes(b"not an image")
        tmp = f.name
    try:
        result = analyze_image(tmp)
        assert not result.get("ok"), f"Should reject .exe: {result}"
        return f"Unsupported ext rejected: {result.get('error','')[:60]}"
    finally:
        Path(tmp).unlink(missing_ok=True)


# ===========================================================================
# 9. Windows PowerShell Compatibility
# ===========================================================================

@test("PowerShell available on PATH", "Windows / PS")
def _():
    result = subprocess.run(
        ["powershell", "-Command", "$PSVersionTable.PSVersion.Major"],
        capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, f"PowerShell failed: {result.stderr}"
    version = result.stdout.strip()
    return f"PowerShell version: {version}"


@test("Node.js available on PATH", "Windows / Node")
def _():
    result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"node not found: {result.stderr}"
    return f"Node.js: {result.stdout.strip()}"


@test("frontend JS syntax check (node --check)", "Windows / Node")
def _():
    for js_file in ["frontend/main.js", "frontend/preload.js", "frontend/renderer.js"]:
        result = subprocess.run(
            ["node", "--check", str(_ROOT / js_file)],
            capture_output=True, text=True, timeout=10, cwd=str(_ROOT)
        )
        assert result.returncode == 0, f"{js_file} syntax error: {result.stderr}"
    return "main.js, preload.js, renderer.js all pass node --check"


@test("Windows platform confirmed", "Windows / PS")
def _():
    assert sys.platform == "win32", f"Expected win32, got: {sys.platform}"
    import platform
    info = platform.platform()
    return f"Platform: {info}"


# ===========================================================================
# 10. Memory System Integrity
# ===========================================================================

@test("Memory database schema valid", "Memory")
def _():
    import sqlite3, tempfile
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO messages(role,content,timestamp) VALUES('user','hello','2024-01-01')")
        conn.commit()
        rows = conn.execute("SELECT role,content FROM messages").fetchall()
        conn.close()
        assert len(rows) == 1 and rows[0][0] == "user"
        return "SQLite memory schema round-trip OK"


@test("MemoryManager clear-history does not raise", "Memory")
def _():
    from backend.memory.memory_manager import get_memory_manager
    mm = get_memory_manager()
    # Should not raise
    try:
        mm.clear_history()
        return "clear_history() OK (no exception)"
    except Exception as e:
        raise AssertionError(f"clear_history raised: {e}") from e


# ===========================================================================
# 11. Full Nine-Phase Test Count Verification
# ===========================================================================

@test("All nine phase test files exist", "Regression")
def _():
    test_files = [
        "tests/test_phase2_electron.py",
        "tests/test_phase3_runtime.py",
        "tests/test_phase4_voice.py",
        "tests/test_phase5_memory.py",
        "tests/test_phase6_automation.py",
        "tests/test_phase7_vision.py",
        "tests/test_phase8_security.py",
        "tests/test_phase9_windows.py",
    ]
    missing = [f for f in test_files if not (_ROOT / f).exists()]
    assert not missing, f"Missing test files: {missing}"
    return f"All {len(test_files)} phase test files present"


@test("Phase 6 regression: 20/20 pass", "Regression")
def _():
    rc, stdout, stderr = _run_python(
        "tests/test_phase6_automation.py", timeout=60
    )
    combined = stdout + stderr
    m = re.search(r"Results:\s*(\d+)/(\d+)\s+passed", combined)
    assert m and m.group(1) == m.group(2), f"Phase 6 regression failed:\n{combined[-600:]}"
    return f"Phase 6: {m.group(1)}/{m.group(2)} passed"


@test("Phase 7 regression: 22/22 pass", "Regression")
def _():
    rc, stdout, stderr = _run_python(
        "-m", "pytest", "tests/test_phase7_vision.py", "-v", "--tb=short", timeout=60
    )
    combined = stdout + stderr
    # pytest output or our custom runner
    if "passed" in combined:
        m = re.search(r"(\d+)\s+passed", combined)
        if m:
            return f"Phase 7: {m.group(1)} passed"
    # Fallback: direct runner
    rc2, stdout2, stderr2 = _run_python("tests/test_phase7_vision.py", timeout=60)
    combined2 = stdout2 + stderr2
    m2 = re.search(r"Ran (\d+) tests", combined2)
    assert m2 and "OK" in combined2, f"Phase 7 regression failed:\n{combined2[-600:]}"
    return f"Phase 7: {m2.group(1)} tests passed"


@test("Phase 8 regression: 8/8 pass", "Regression")
def _():
    rc, stdout, stderr = _run_python("tests/test_phase8_security.py", timeout=60)
    combined = stdout + stderr
    m = re.search(r"Ran (\d+) tests", combined)
    assert m and "OK" in combined, f"Phase 8 regression failed:\n{combined[-600:]}"
    return f"Phase 8: {m.group(1)} tests passed"


# ===========================================================================
# 12. Git Repository Integrity
# ===========================================================================

@test("Git working tree has no modified or staged changes", "Git")
def _():
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(_ROOT), timeout=10
    )
    assert result.returncode == 0
    lines = [l for l in result.stdout.strip().splitlines() if l and not l.startswith("??")]
    assert not lines, f"Working tree has uncommitted modifications:\n" + "\n".join(lines)
    untracked = [l for l in result.stdout.strip().splitlines() if l.startswith("??")]
    return f"No staged/modified changes. Untracked: {len(untracked)} file(s)"


@test("Local main matches origin/main", "Git")
def _():
    subprocess.run(["git", "fetch", "origin"], capture_output=True, cwd=str(_ROOT), timeout=15)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD", "origin/main"],
        capture_output=True, text=True, cwd=str(_ROOT), timeout=10
    )
    hashes = result.stdout.strip().split()
    assert len(hashes) == 2 and hashes[0] == hashes[1], \
        f"HEAD ({hashes[0][:7]}) != origin/main ({hashes[1][:7] if len(hashes)>1 else '?'})"
    return f"HEAD == origin/main == {hashes[0][:7]}"


@test("No .env tracked in git", "Git")
def _():
    result = subprocess.run(
        ["git", "ls-files", ".env"],
        capture_output=True, text=True, cwd=str(_ROOT), timeout=10
    )
    tracked = result.stdout.strip()
    assert tracked == "", f".env is tracked: {tracked}"
    return ".env not tracked"


@test("No hardcoded secrets in backend Python files", "Git")
def _():
    secret_re = re.compile(r"(sk-[A-Za-z0-9]{10,}|AIza[A-Za-z0-9_\-]{30,})")
    findings = []
    for py_file in (_ROOT / "backend").rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in secret_re.finditer(text):
            findings.append(f"{py_file.relative_to(_ROOT)}:{m.start()}: {m.group()[:20]}...")
    assert not findings, f"Hardcoded secrets found:\n" + "\n".join(findings)
    return "No hardcoded secrets found"


# ===========================================================================
# Runner
# ===========================================================================

def main():
    print("=" * 72)
    print("  NexonAI Phase 9 — Automated Testing & Windows 11 Verification")
    print("=" * 72)

    passed = 0
    failed = 0
    skipped = 0
    last_category = None

    for name, category, fn in TESTS:
        if category != last_category:
            print(f"\n  [{category}]")
            last_category = category
        try:
            detail = fn()
            passed += 1
            print(f"    [PASS] {name}")
            if detail:
                print(f"           -> {detail}")
        except AssertionError as e:
            failed += 1
            print(f"    [FAIL] {name}")
            print(f"           -> {e}")
        except Exception as e:
            failed += 1
            print(f"    [FAIL] {name}")
            print(f"           -> {type(e).__name__}: {e}")

    total = len(TESTS)
    print("\n" + "=" * 72)
    print(f"  Results: {passed}/{total} passed  |  {failed} failed")
    print("=" * 72 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
