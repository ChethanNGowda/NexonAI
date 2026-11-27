import os
import sys
import time
import argparse
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
            try:
                sys.exit(subprocess.call([str(VENV_PYTHON)] + sys.argv, env=env))
            except KeyboardInterrupt:
                sys.exit(0)
    except Exception:
        pass

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.core.assistant import process_query, check_wake_word
from backend.voice.tts import speak
from backend.voice.stt import SpeechRecognizer

# ============================================================
# JARVIS - DESKTOP VOICE ASSISTANT RUNNER
# ============================================================

BANNER = r"""
======================================================================
     ___  ___  ______ _    _ _____ _____ 
    |_  |/ _ \ | ___ \ |  | |_   _/  ___|
      | / /_\ \| |_/ / |  | | | | \ `--. 
      | |  _  ||    /| |/\| | | |  `--. \
  /\__/ / | | || |\ \\  /\  /_| |_/\__/ /
  \____/\_| |_/\_| \_|\/  \/ \___/\____/ 
                                         
   J.A.R.V.I.S. Desktop Voice Assistant (Nexon AI)
   Powered by Whisper STT | Ollama Qwen 8B | Edge TTS
======================================================================
"""


def ensure_mic_unmuted():
    """Ensure Windows microphone is unmuted and set to audible volume."""
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import comtypes
        from ctypes import POINTER
        mic = AudioUtilities.GetMicrophone()
        interface = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        vol = comtypes.cast(interface, POINTER(IAudioEndpointVolume))
        if vol.GetMute():
            print("[SYSTEM] Microphone was muted in Windows. Unmuting now...")
            vol.SetMute(0, None)
        level = vol.GetMasterVolumeLevelScalar()
        if level < 0.2:
            print("[SYSTEM] Microphone volume was very low. Boosting to 80%...")
            vol.SetMasterVolumeLevelScalar(0.8, None)
    except Exception:
        pass


def run_voice_loop(always_listen: bool = False, silent_greeting: bool = False):
    """Main hands-free voice loop."""
    print(BANNER)
    ensure_mic_unmuted()
    print("[SYSTEM] Initializing speech recognition...")
    recognizer = SpeechRecognizer()

    greeting = "Jarvis is online and ready, sir."
    print(f"\n[JARVIS] {greeting}")
    if not silent_greeting:
        speak(greeting, play_audio=True)

    print("\n----------------------------------------------------------------------")
    if always_listen:
        print("[MODE] Always Listen: Speak any command directly into the microphone.")
    else:
        print("[MODE] Wake-Word: Say 'Jarvis' followed by your command.")
        print("       Example: 'Jarvis, open Chrome' or 'Jarvis, what is the time?'")
    print("       Say 'Goodbye Jarvis' or press Ctrl+C to exit.")
    print("----------------------------------------------------------------------\n")

    while True:
        try:
            print("\r[LISTENING] Listening for speech... (Say 'Jarvis' or command)   ", end="", flush=True)
            transcript = recognizer.listen_and_transcribe()

            if not transcript or not transcript.strip():
                continue

            cleaned_text = transcript.strip()
            print(f"\n\n[USER] Heard: \"{cleaned_text}\"")

            # Check wake word
            has_wake, prompt = check_wake_word(cleaned_text)

            # If no wake word, check if it's a direct action command or always_listen is on
            if not has_wake and not always_listen:
                from backend.core.assistant import handle_fast_intent
                if handle_fast_intent(cleaned_text) is not None:
                    prompt = cleaned_text
                else:
                    print(f"[IDLE] Heard: \"{cleaned_text}\" (Say 'Jarvis' to activate)")
                    continue

            if not prompt:
                # User just said "Jarvis"
                ack = "Yes sir, I am listening."
                print(f"[JARVIS] {ack}\n")
                speak(ack, play_audio=True)
                continue

            print(f"[PROCESSING] \"{prompt}\"")
            result = process_query(prompt, play_speech=True)

            print(f"[JARVIS] {result['answer']}\n")

            if result.get("is_exit"):
                print("[SYSTEM] Jarvis shutting down. Have a good day, sir.")
                break

        except KeyboardInterrupt:
            print("\n\n[SYSTEM] Shutting down Jarvis voice assistant. Goodbye, sir.")
            break
        except Exception as e:
            print(f"\n[ERROR] An unexpected error occurred: {e}", file=sys.stderr)
            time.sleep(1)


def run_text_mode():
    """Interactive text console for testing without a microphone."""
    print(BANNER)
    print("[MODE] Text Console Mode. Type your commands or queries.\n")

    while True:
        try:
            user_input = input("You > ").strip()
            if not user_input:
                continue

            has_wake, prompt = check_wake_word(user_input)
            query = prompt if prompt else user_input

            result = process_query(query, play_speech=True)
            print(f"Jarvis > {result['answer']}\n")

            if result.get("is_exit"):
                break
        except (KeyboardInterrupt, EOFError):
            print("\n[SYSTEM] Exiting text mode. Goodbye, sir.")
            break


def run_voice_loop_ipc(always_listen: bool = False, silent_greeting: bool = False):
    """Voice loop designed to run as a subprocess for Electron, communicating via JSON lines."""
    import json
    ensure_mic_unmuted()
    recognizer = SpeechRecognizer()

    greeting = "Phoebe is online and listening, sir."
    print(json.dumps({"event": "ready", "message": greeting}), flush=True)
    if not silent_greeting:
        speak(greeting, play_audio=True)

    print(json.dumps({"event": "state", "status": "listening"}), flush=True)

    while True:
        try:
            transcript = recognizer.listen_and_transcribe()
            if not transcript or not transcript.strip():
                continue

            cleaned_text = transcript.strip()
            print(json.dumps({"event": "heard", "text": cleaned_text}), flush=True)

            has_wake, prompt = check_wake_word(cleaned_text)
            if not has_wake and not always_listen:
                from backend.core.assistant import handle_fast_intent
                if handle_fast_intent(cleaned_text) is not None:
                    prompt = cleaned_text
                else:
                    print(json.dumps({"event": "state", "status": "listening", "detail": f"Heard '{cleaned_text}'"}), flush=True)
                    continue

            if not prompt:
                ack = "Yes sir, I am listening."
                print(json.dumps({"event": "response", "answer": ack, "action": "wake_ack"}), flush=True)
                speak(ack, play_audio=True)
                print(json.dumps({"event": "state", "status": "listening"}), flush=True)
                continue

            print(json.dumps({"event": "state", "status": "thinking", "prompt": prompt}), flush=True)

            # Route through unified assistant brain
            from backend.ai.assistant import get_assistant
            res = get_assistant().process(prompt, play_speech=True)

            answer = res.get("spoken_answer") or res.get("markdown_report") or "Understood, sir."
            print(json.dumps({
                "event": "response",
                "answer": answer,
                "action": res.get("action", "chat"),
                "markdown": res.get("markdown_report", answer),
                "sources": res.get("sources", []),
            }), flush=True)

            print(json.dumps({"event": "state", "status": "listening"}), flush=True)

            if res.get("is_exit"):
                break
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(json.dumps({"event": "error", "message": str(e)}), flush=True)
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="JARVIS Voice Assistant")
    parser.add_argument("--always-listen", action="store_true", help="Respond to all speech without requiring 'Jarvis' wake word")
    parser.add_argument("--text", action="store_true", help="Run in interactive text mode instead of voice")
    parser.add_argument("--ipc", action="store_true", help="Run in IPC JSON stream mode for Electron companion")
    parser.add_argument("--ask", type=str, help="Execute a single command or query and exit")
    parser.add_argument("--silent", action="store_true", help="Suppress initial startup greeting speech")
    args = parser.parse_args()

    if args.ask:
        has_wake, prompt = check_wake_word(args.ask)
        query = prompt if prompt else args.ask
        result = process_query(query, play_speech=not args.silent)
        print(f"Jarvis > {result['answer']}")
        return

    if args.ipc:
        run_voice_loop_ipc(always_listen=args.always_listen, silent_greeting=args.silent)
    elif args.text:
        run_text_mode()
    else:
        run_voice_loop(always_listen=args.always_listen, silent_greeting=args.silent)


if __name__ == "__main__":
    main()
