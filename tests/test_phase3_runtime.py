"""
Phase 3 Test Suite — Python Runtime Integration
================================================
Tests:
  1.  Python interpreter reachable
  2.  Daemon start → {event: ready} emitted on stdout
  3.  IPC stdout contains only valid JSON lines (no non-JSON pollution)
  4.  Daemon handles stdin {"cmd": "shutdown"} and exits cleanly (code 0)
  5.  Invalid JSON on stdin → daemon stays alive (no crash)
  6.  One-shot worker: assistant.py --ask (JSON response with spoken_answer)
  7.  One-shot worker: assistant.py --models (list of Ollama models)
  8.  One-shot worker: assistant.py --health (ollama_connected field)
  9.  TTS module: speak() does not write to stdout
  10. STT module: SpeechRecognizer importable (no mic hardware required)
  11. Settings JSON round-trip (write / read / validate)
  12. jarvis.py AST syntax (no parse errors)
  13. Node.js: frontend/main.js syntax
  14. Node.js: frontend/preload.js syntax
  15. Node.js: frontend/renderer.js syntax

Design: Tests 2-5 share ONE daemon process (loaded once) to avoid 4× Whisper
cold-start overhead. The daemon is started before group and shut down after.
"""

import json
import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PY) if VENV_PY.exists() else sys.executable

JARVIS  = str(ROOT / "jarvis.py")
ASST    = str(ROOT / "backend" / "ai" / "assistant.py")
TIMEOUT = 60   # seconds — covers Whisper cold load (~35s) + margin

PASS = "[OK]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results: list[tuple[str, str, str]] = []


def _reg(label: str):
    """Decorator: run the function as a named test; record pass/fail."""
    def deco(fn):
        try:
            detail = fn()
            results.append((label, PASS, detail or ""))
        except AssertionError as e:
            results.append((label, FAIL, str(e)))
        except Exception as e:
            results.append((label, FAIL, f"Exception: {type(e).__name__}: {e}"))
        return fn
    return deco


def _ipc_env() -> dict:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


# ─────────────────────────────────────────────────────────────────────────────
# Shared daemon fixture — started once, reused for tests 2-5
# ─────────────────────────────────────────────────────────────────────────────

class DaemonFixture:
    def __init__(self):
        self.proc = None
        self._buf = b""
        self._events: list[dict] = []
        self._non_json: list[str] = []
        self.ready = False

    def start(self) -> bool:
        """Spawn the daemon and drain stdout until {event:ready} or timeout."""
        self.proc = subprocess.Popen(
            [PYTHON, JARVIS, "--ipc", "--silent"],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_ipc_env(),
        )
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return False   # crashed before ready
            chunk = self.proc.stdout.read1(4096)
            if not chunk:
                time.sleep(0.05)
                continue
            self._buf += chunk
            lines = self._buf.split(b"\n")
            self._buf = lines.pop()
            for raw in lines:
                s = raw.strip().decode("utf-8", errors="replace")
                if not s:
                    continue
                try:
                    evt = json.loads(s)
                    self._events.append(evt)
                    if evt.get("event") == "ready":
                        self.ready = True
                        return True
                except json.JSONDecodeError:
                    self._non_json.append(s)
        return False   # timeout

    def drain_briefly(self, seconds: float = 2.0) -> None:
        """Read stdout for a short period to collect any extra events."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.proc is None or self.proc.poll() is not None:
                break
            chunk = self.proc.stdout.read1(4096)
            if not chunk:
                time.sleep(0.05)
                continue
            self._buf += chunk
            lines = self._buf.split(b"\n")
            self._buf = lines.pop()
            for raw in lines:
                s = raw.strip().decode("utf-8", errors="replace")
                if not s:
                    continue
                try:
                    self._events.append(json.loads(s))
                except json.JSONDecodeError:
                    self._non_json.append(s)

    def send(self, cmd: dict) -> None:
        try:
            if self.proc and self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.write(json.dumps(cmd).encode() + b"\n")
                self.proc.stdin.flush()
        except Exception:
            pass

    def shutdown(self, timeout: float = 8.0) -> int:
        if self.proc is None:
            return 0
        self.send({"cmd": "shutdown"})
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            rc = -1
        self.proc = None
        return rc


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

@_reg("Python interpreter reachable")
def test_python():
    r = subprocess.run([PYTHON, "--version"], capture_output=True, text=True, timeout=5)
    assert r.returncode == 0, f"Python exited {r.returncode}"
    return r.stdout.strip() or r.stderr.strip()


# Boot the shared daemon once for tests 2-5
print("[setup] Starting shared daemon (Whisper cold load, please wait)...", flush=True)
_daemon = DaemonFixture()
_daemon_started = _daemon.start()


@_reg("Daemon start → {event: ready}")
def test_daemon_ready():
    assert _daemon_started, "Daemon failed to reach ready state within timeout"
    assert _daemon.ready, "No {event:ready} received"
    # Find the ready event
    evt = next((e for e in _daemon._events if e.get("event") == "ready"), None)
    assert evt is not None
    return f"message='{evt.get('message', '')}'"


@_reg("IPC stdout contains only JSON lines")
def test_stdout_json_only():
    assert _daemon_started, "Daemon did not start — cannot verify stdout"
    # Drain a little more stdout to catch any lazy prints
    _daemon.drain_briefly(1.5)
    if _daemon._non_json:
        raise AssertionError(f"Non-JSON on stdout: {_daemon._non_json[:3]}")
    return f"All {len(_daemon._events)} events are valid JSON"


@_reg("Invalid stdin command → daemon stays alive")
def test_invalid_stdin_no_crash():
    assert _daemon_started, "Daemon did not start"
    # Send two garbage lines
    _daemon.send({"THIS_IS_GARBAGE": True, "broken": "nope"})  # valid JSON but unknown cmd — OK
    try:
        if _daemon.proc and _daemon.proc.stdin:
            _daemon.proc.stdin.write(b"NOT JSON AT ALL!!!\n")
            _daemon.proc.stdin.write(b"{broken_json\n")
            _daemon.proc.stdin.flush()
    except Exception:
        pass
    time.sleep(1.5)
    assert _daemon.proc is not None, "Daemon object lost"
    assert _daemon.proc.poll() is None, \
        f"Daemon crashed on bad stdin (code={_daemon.proc.poll()})"
    return "Daemon survived invalid stdin commands"


@_reg("Request-response correlation (ping/pong + stop/start listening)")
def test_daemon_correlation_and_controls():
    assert _daemon_started, "Daemon did not start"
    _daemon.send({"cmd": "ping", "request_id": "req-42"})
    _daemon.send({"cmd": "stop_listening", "request_id": "req-43"})
    _daemon.send({"cmd": "set_rate", "rate": 1.25, "request_id": "req-44"})
    _daemon.send({"cmd": "set_volume", "volume": 85, "request_id": "req-45"})
    _daemon.send({"cmd": "interrupt_audio", "request_id": "req-46"})
    _daemon.send({"cmd": "start_listening", "request_id": "req-47"})
    _daemon.drain_briefly(2.5)
    pong = next((e for e in _daemon._events if e.get("event") == "pong" and e.get("request_id") == "req-42"), None)
    assert pong is not None, f"Did not receive correlated pong for req-42. Events: {_daemon._events[-6:]}"
    acks = {e.get("request_id") for e in _daemon._events if e.get("event") == "ack"}
    assert {"req-43", "req-44", "req-45", "req-46", "req-47"}.issubset(acks), f"Missing acks: {acks}"
    return "Correlated pong + 5 control acks verified"


@_reg("Daemon shutdown via stdin {cmd: shutdown}")
def test_daemon_shutdown():
    assert _daemon_started, "Daemon did not start — cannot test shutdown"
    rc = _daemon.shutdown(timeout=10)
    assert rc == 0, f"Daemon exited with code {rc} (expected 0)"
    return f"Clean exit (code={rc})"


# ── One-shot worker tests ─────────────────────────────────────────────────────

@_reg("One-shot worker: assistant.py --ask 'what time is it' --rate 1.2 --volume 80")
def test_worker_ask():
    r = subprocess.run(
        [PYTHON, ASST, "--ask", "what time is it", "--rate", "1.2", "--volume", "80"],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=TIMEOUT, env=_ipc_env(),
    )
    out = r.stdout.strip()
    assert out, f"No stdout from worker. stderr={r.stderr[:300]}"
    # Find last JSON object in stdout
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            obj = json.loads(line)
            assert obj.get("ok") is True, f"Response not ok: {obj}"
            return f"answer='{str(obj.get('spoken_answer', obj.get('answer', '')))[:60]}'"
    raise AssertionError(f"No JSON object in stdout: {out[:200]}")


@_reg("One-shot worker: assistant.py --models")
def test_worker_models():
    r = subprocess.run(
        [PYTHON, ASST, "--models"],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=TIMEOUT, env=_ipc_env(),
    )
    out = r.stdout.strip()
    assert out, f"No stdout. stderr={r.stderr[:200]}"
    obj = json.loads(out)
    assert obj.get("ok") is True
    return f"models={obj.get('installed_models', [])}"


@_reg("One-shot worker: assistant.py --health")
def test_worker_health():
    r = subprocess.run(
        [PYTHON, ASST, "--health"],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=TIMEOUT, env=_ipc_env(),
    )
    out = r.stdout.strip()
    assert out, f"No stdout. stderr={r.stderr[:200]}"
    obj = json.loads(out)
    assert obj.get("ok") is True
    return f"ollama_connected={obj.get('ollama_connected')}"


# ── TTS / STT module tests ────────────────────────────────────────────────────

@_reg("TTS module: speak() writes nothing to stdout")
def test_tts_stdout_clean():
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "from backend.voice.tts import speak\n"
        "speak('Hello sir.', play_audio=False)\n"
        "# If we reach here with no stdout output the test passes\n"
    )
    r = subprocess.run(
        [PYTHON, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=20, env=_ipc_env(),
    )
    assert not r.stdout.strip(), f"speak() wrote to stdout: {r.stdout.strip()!r}"
    return "stdout clean"


@_reg("STT module importable (no mic required)")
def test_stt_import():
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "from backend.voice.stt import SpeechRecognizer\n"
        "print('OK', flush=True)\n"
    )
    r = subprocess.run(
        [PYTHON, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=15, env=_ipc_env(),
    )
    assert "OK" in r.stdout, f"Import failed. stderr={r.stderr[:300]}"
    return "SpeechRecognizer importable"


@_reg("Settings JSON round-trip")
def test_settings_roundtrip():
    sample = {"alwaysOnTop": False, "voiceOutput": True, "speechRate": 1.3,
               "speechVolume": 75, "activeModel": "qwen3-vl:4b"}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = Path(f.name)
        json.dump(sample, f)
    try:
        loaded = json.loads(tmp.read_text())
        assert loaded["alwaysOnTop"] is False
        assert abs(loaded["speechRate"] - 1.3) < 0.001
        assert loaded["speechVolume"] == 75
        assert loaded["activeModel"] == "qwen3-vl:4b"
        return "All fields round-tripped correctly"
    finally:
        tmp.unlink(missing_ok=True)


@_reg("jarvis.py AST syntax check")
def test_jarvis_syntax():
    code = (
        "import ast\n"
        "ast.parse(open('jarvis.py', encoding='utf-8').read())\n"
        "print('SYNTAX_OK', flush=True)\n"
    )
    r = subprocess.run(
        [PYTHON, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True,
        timeout=10, env=_ipc_env(),
    )
    assert "SYNTAX_OK" in r.stdout, f"Syntax error: {r.stderr[:300]}"
    return "jarvis.py parses cleanly"


# ── Node.js syntax checks ─────────────────────────────────────────────────────

def _node_check(js_path: Path) -> str:
    if not js_path.exists():
        return SKIP
    r = subprocess.run(
        ["node", "-c", str(js_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, r.stderr[:200]
    return "OK"


@_reg("Node.js: frontend/main.js syntax")
def test_node_main():
    return _node_check(ROOT / "frontend" / "main.js")


@_reg("Node.js: frontend/preload.js syntax")
def test_node_preload():
    return _node_check(ROOT / "frontend" / "preload.js")


@_reg("Node.js: frontend/renderer.js syntax")
def test_node_renderer():
    p = ROOT / "frontend" / "renderer.js"
    if not p.exists():
        results[-1] = (results[-1][0], SKIP, "File not found")
        return
    return _node_check(p)


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 70)
    print("              NEXONAI PHASE 3 TEST SUITE")
    print("=" * 70)

    passed = failed = skipped = 0
    for name, status, detail in results:
        tag = {"[OK]": "PASS", "[FAIL]": "FAIL", "[SKIP]": "SKIP"}.get(status, status)
        line = f"  [{tag}] {name}"
        if detail:
            line += f"\n         → {detail}"
        print(line)
        if status == PASS:    passed  += 1
        elif status == FAIL:  failed  += 1
        else:                 skipped += 1

    print()
    print("=" * 70)
    total = passed + failed + skipped
    print(f"  Results: {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped")
    print("=" * 70)
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
