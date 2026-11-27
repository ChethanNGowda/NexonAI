"""
JARVIS — DESKTOP VOICE ASSISTANT RUNNER
========================================
Entry point for the NexonAI desktop companion.

Modes:
  --ipc           Run as a persistent IPC subprocess for Electron (JSON lines on stdout).
  --text          Interactive text console for testing without microphone.
  --always-listen Respond to all speech (no wake word required).
  --ask <text>    One-shot query and exit.
  --silent        Suppress startup greeting speech.

IPC Protocol (--ipc mode)
--------------------------
Daemon → Electron (stdout, one JSON object per line):
  {"event": "ready",    "message": "..."}
  {"event": "state",    "status": "listening|thinking|speaking|error", "detail": "..."}
  {"event": "heard",    "text": "..."}
  {"event": "response", "answer": "...", "action": "...", "markdown": "...", "sources": [...]}
  {"event": "error",    "message": "..."}
  {"event": "exit"}

Electron → Daemon (stdin, one JSON object per line):
  {"cmd": "stop_listening"}
  {"cmd": "interrupt_audio"}
  {"cmd": "set_voice",  "enabled": true}
  {"cmd": "set_model",  "model": "qwen3-vl:4b"}
  {"cmd": "set_rate",   "rate": 1.2}
  {"cmd": "set_volume", "volume": 80}
  {"cmd": "shutdown"}

stderr is reserved for diagnostic logging only — Electron never parses it.
stdout is reserved for machine-readable JSON IPC — no print() to stdout.
"""

import os
import sys
import time
import json
import argparse
import threading
import subprocess
from pathlib import Path

# ----------------------------------------------------------------
# Venv re-exec: if a .venv exists and we're not already inside it,
# re-execute inside it so dependencies are always available.
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"

if VENV_PYTHON.exists():
    try:
        curr = Path(sys.executable).resolve()
        venv = VENV_PYTHON.resolve()
        if curr != venv and "JARVIS_VENV_REEXEC" not in os.environ:
            env = dict(os.environ)
            env["JARVIS_VENV_REEXEC"] = "1"
            try:
                sys.exit(subprocess.call([str(VENV_PYTHON)] + sys.argv, env=env))
            except KeyboardInterrupt:
                sys.exit(0)
    except Exception:
        pass

# ----------------------------------------------------------------
# Ensure project root is in sys.path
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ----------------------------------------------------------------
# Configure stdout / stderr encoding for Windows
# ----------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


BANNER = r"""
======================================================================
     ___  ___  ______ _    _ _____ _____
    |_  |/ _ \ | ___ \ |  | |_   _/  ___|
      | / /_\ \| |_/ / |  | | | | \ `--.
      | |  _  ||    /| |/\| | | |  `--. \
  /\__/ / | | || |\ \\  /\  /_| |_/\__/ /
  \____/\_| |_/\_| \_|\/  \/ \___/\____/

   J.A.R.V.I.S. Desktop Voice Assistant (Nexon AI)
   Powered by Whisper STT | Ollama | Edge TTS
======================================================================
"""


# ----------------------------------------------------------------
# IPC helpers — all JSON output goes through these
# ----------------------------------------------------------------

_emit_lock = threading.Lock()


def _emit(obj: dict) -> None:
    """Write a JSON event line to stdout (the IPC channel), thread-safely."""
    try:
        line = json.dumps(obj, ensure_ascii=False)
        with _emit_lock:
            print(line, flush=True)
    except Exception:
        pass


def _log(msg: str) -> None:
    """Write a diagnostic line to stderr only."""
    print(f"[JARVIS] {msg}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------
# Stdin command reader (runs in a daemon thread during --ipc mode)
# ----------------------------------------------------------------

class _StdinCommandReader(threading.Thread):
    """Reads JSON commands from stdin and stores them in a queue."""

    def __init__(self):
        super().__init__(daemon=True, name="stdin-cmd-reader")
        self._commands: list[dict] = []
        self._lock = threading.Lock()
        self._shutdown_requested = threading.Event()

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
                action = cmd.get("cmd", "")
                req_id = cmd.get("request_id") or cmd.get("id")
                if action == "ping":
                    _emit({"event": "pong", "request_id": req_id})
                    continue
                if action == "interrupt_audio":
                    try:
                        from backend.voice.tts import stop_audio
                        stop_audio()
                    except Exception:
                        pass
                    if req_id is not None:
                        _emit({"event": "ack", "request_id": req_id, "cmd": action})
                    continue
                with self._lock:
                    self._commands.append(cmd)
                if req_id is not None and action in {
                    "stop_listening", "start_listening", "set_voice", "set_model", "set_rate", "set_volume"
                }:
                    _emit({"event": "ack", "request_id": req_id, "cmd": action})
                if action == "shutdown":
                    self._shutdown_requested.set()
                    break
            except json.JSONDecodeError:
                _log(f"[StdinReader] Invalid JSON command: {line!r}")
        self._shutdown_requested.set()

    def drain(self) -> list[dict]:
        """Return and clear all pending commands."""
        with self._lock:
            cmds = list(self._commands)
            self._commands.clear()
        return cmds

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested.is_set()


# ----------------------------------------------------------------
# Microphone control helpers
# ----------------------------------------------------------------

def _ensure_mic_unmuted() -> None:
    """Attempt to unmute the Windows microphone via pycaw."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import comtypes
        from ctypes import POINTER
        mic = AudioUtilities.GetMicrophone()
        if mic is None:
            return
        interface = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        vol = comtypes.cast(interface, POINTER(IAudioEndpointVolume))
        if vol.GetMute():
            _log("Microphone was muted — unmuting now.")
            vol.SetMute(0, None)
        level = vol.GetMasterVolumeLevelScalar()
        if level < 0.2:
            _log("Microphone volume very low — boosting to 80%.")
            vol.SetMasterVolumeLevelScalar(0.8, None)
    except Exception:
        pass


# ----------------------------------------------------------------
# Voice loop — text console mode (testing without microphone)
# ----------------------------------------------------------------

def run_text_mode() -> None:
    print(BANNER, file=sys.stderr)
    print("[MODE] Text Console. Type commands or questions.\n", file=sys.stderr)

    from backend.core.assistant import process_query, check_wake_word
    while True:
        try:
            user_input = input("You > ").strip()
            if not user_input:
                continue
            _, prompt = check_wake_word(user_input)
            query = prompt or user_input
            result = process_query(query, play_speech=True)
            print(f"Jarvis > {result.get('answer', '')}\n", file=sys.stderr)
            if result.get("is_exit"):
                break
        except (KeyboardInterrupt, EOFError):
            print("\n[SYSTEM] Exiting text mode.", file=sys.stderr)
            break


# ----------------------------------------------------------------
# Standard (non-IPC) voice loop
# ----------------------------------------------------------------

def run_voice_loop(always_listen: bool = False, silent_greeting: bool = False) -> None:
    print(BANNER, file=sys.stderr)
    _ensure_mic_unmuted()
    _log("Initializing speech recognition...")

    from backend.core.assistant import process_query, check_wake_word, handle_fast_intent
    from backend.voice.stt import SpeechRecognizer
    from backend.voice.tts import speak

    recognizer = SpeechRecognizer()
    greeting = "Jarvis is online and ready, sir."
    _log(greeting)
    if not silent_greeting:
        speak(greeting, play_audio=True)

    while True:
        try:
            print("\r[LISTENING] Listening...   ", end="", file=sys.stderr, flush=True)
            transcript = recognizer.listen_and_transcribe()
            if not transcript:
                continue
            cleaned = transcript.strip()
            _log(f'Heard: "{cleaned}"')

            has_wake, prompt = check_wake_word(cleaned)
            if not has_wake and not always_listen:
                if handle_fast_intent(cleaned) is not None:
                    prompt = cleaned
                else:
                    continue

            if not prompt:
                ack = "Yes sir, I am listening."
                _log(ack)
                speak(ack, play_audio=True)
                continue

            _log(f'Processing: "{prompt}"')
            result = process_query(prompt, play_speech=True)
            _log(f"Response: {result.get('answer', '')}")
            if result.get("is_exit"):
                break

        except KeyboardInterrupt:
            _log("Shutting down. Goodbye, sir.")
            break
        except Exception as e:
            _log(f"Unexpected error: {e}")
            time.sleep(1)


# ----------------------------------------------------------------
# IPC voice loop — the core of Electron integration
# ----------------------------------------------------------------

def run_voice_loop_ipc(always_listen: bool = False, silent_greeting: bool = False) -> None:
    """
    Persistent voice loop running as a child process of Electron.
    - All JSON events go to stdout (the IPC channel).
    - All diagnostics go to stderr.
    - Stdin carries JSON commands from Electron (rate, volume, model, shutdown…).
    - Crashes inside the loop are caught and reported; the loop continues.
    - Responds to {"cmd": "shutdown"} from Electron for clean exit.
    """
    _ensure_mic_unmuted()

    # Import lazily so errors don't prevent the process from starting
    try:
        from backend.core.assistant import check_wake_word, handle_fast_intent
        from backend.ai.assistant import get_assistant
        from backend.voice.stt import SpeechRecognizer
        from backend.voice.tts import speak, stop_audio, set_speech_rate, set_speech_volume
    except Exception as e:
        _emit({"event": "error", "message": f"Import failure: {e}"})
        _log(f"Import failure: {e}")
        return

    # Settings from environment / defaults
    voice_enabled = True
    listening_enabled = True
    current_model: str | None = None

    # Start stdin command reader
    cmd_reader = _StdinCommandReader()
    cmd_reader.start()

    # Initialise STT
    try:
        _emit({"event": "state", "status": "loading", "detail": "Initializing speech recognition..."})
        recognizer = SpeechRecognizer()
    except Exception as e:
        _emit({"event": "error", "message": f"STT init failed: {e}"})
        _log(f"STT init failed: {e}")
        return

    # Ready
    greeting = "Phoebe is online and listening, sir."
    _emit({"event": "ready", "message": greeting})
    if not silent_greeting and voice_enabled:
        try:
            speak(greeting, play_audio=True)
        except Exception:
            pass

    _emit({"event": "state", "status": "listening"})

    while True:
        # --- Process pending stdin commands ---
        for cmd in cmd_reader.drain():
            action = cmd.get("cmd", "")
            req_id = cmd.get("request_id") or cmd.get("id")
            if action == "shutdown":
                if req_id is not None:
                    _emit({"event": "ack", "request_id": req_id, "cmd": action})
                _emit({"event": "exit"})
                return
            elif action == "stop_listening":
                listening_enabled = False
                _emit({"event": "state", "status": "idle", "detail": "Listening paused."})
            elif action == "start_listening":
                listening_enabled = True
                _emit({"event": "state", "status": "listening", "detail": "Listening resumed."})
            elif action == "set_voice":
                voice_enabled = bool(cmd.get("enabled", True))
                _log(f"Voice output {'enabled' if voice_enabled else 'disabled'}.")
            elif action == "set_model":
                current_model = cmd.get("model") or None
                _log(f"Model set to: {current_model}")
            elif action == "set_rate":
                try:
                    set_speech_rate(float(cmd.get("rate", 1.0)))
                except Exception:
                    pass
            elif action == "set_volume":
                try:
                    set_speech_volume(int(cmd.get("volume", 100)))
                except Exception:
                    pass

        # Clean shutdown requested via stdin
        if cmd_reader.shutdown_requested:
            _emit({"event": "exit"})
            return

        if not listening_enabled:
            time.sleep(0.25)
            continue

        # --- Listen for speech ---
        try:
            transcript = recognizer.listen_and_transcribe()
        except Exception as e:
            _emit({"event": "error", "message": f"Microphone error: {e}"})
            _log(f"Microphone error: {e}")
            time.sleep(1)
            continue

        if not transcript or not transcript.strip():
            continue

        cleaned = transcript.strip()
        _emit({"event": "heard", "text": cleaned})

        # --- Wake word check ---
        try:
            has_wake, prompt = check_wake_word(cleaned)
        except Exception:
            has_wake, prompt = False, cleaned

        if not has_wake and not always_listen:
            try:
                if handle_fast_intent(cleaned) is not None:
                    prompt = cleaned
                else:
                    _emit({"event": "state", "status": "listening",
                           "detail": f"No wake word in: '{cleaned}'"})
                    continue
            except Exception:
                _emit({"event": "state", "status": "listening"})
                continue

        # Wake word only (no actual query)
        if not prompt:
            ack = "Yes sir, I am listening."
            _emit({"event": "response", "answer": ack, "action": "wake_ack",
                   "markdown": ack, "sources": []})
            if voice_enabled:
                try:
                    speak(ack, play_audio=True)
                except Exception:
                    pass
            _emit({"event": "state", "status": "listening"})
            continue

        # --- Process query ---
        _emit({"event": "state", "status": "thinking", "detail": prompt})
        try:
            assistant = get_assistant()
            res = assistant.process(
                prompt,
                play_speech=voice_enabled,
                model_override=current_model,
            )
            answer = (res.get("spoken_answer") or res.get("markdown_report")
                      or "Understood, sir.")
            _emit({
                "event": "response",
                "answer": answer,
                "action": res.get("action", "chat"),
                "markdown": res.get("markdown_report", answer),
                "sources": res.get("sources", []),
            })
            _emit({"event": "state", "status": "listening"})

            if res.get("is_exit"):
                _emit({"event": "exit"})
                return

        except KeyboardInterrupt:
            _emit({"event": "exit"})
            return
        except Exception as e:
            _emit({"event": "error", "message": str(e)})
            _log(f"Processing error: {e}")
            _emit({"event": "state", "status": "listening"})
            time.sleep(1)


# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS Voice Assistant")
    parser.add_argument("--always-listen", action="store_true",
                        help="Respond to all speech (no wake word required)")
    parser.add_argument("--text", action="store_true",
                        help="Run in interactive text mode (no microphone)")
    parser.add_argument("--ipc", action="store_true",
                        help="Run as Electron IPC subprocess (JSON stream on stdout)")
    parser.add_argument("--ask", type=str,
                        help="Execute a single query and exit")
    parser.add_argument("--silent", action="store_true",
                        help="Suppress startup greeting speech")
    args = parser.parse_args()

    if args.ask:
        # One-shot mode: used by the Electron 'assistant:ask' IPC handler
        try:
            from backend.core.assistant import process_query, check_wake_word
            _, prompt = check_wake_word(args.ask)
            query = prompt or args.ask
            result = process_query(query, play_speech=not args.silent)
            # Emit JSON to stdout for Electron to parse
            print(json.dumps(result), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)
        return

    if args.ipc:
        run_voice_loop_ipc(
            always_listen=args.always_listen,
            silent_greeting=args.silent,
        )
    elif args.text:
        run_text_mode()
    else:
        run_voice_loop(
            always_listen=args.always_listen,
            silent_greeting=args.silent,
        )


if __name__ == "__main__":
    main()
