import os
import sys
import subprocess
import tempfile
import time
import re
from pathlib import Path

import sounddevice as sd
import wave
from faster_whisper import WhisperModel


# ============================================================
# PHOEBE — NEXON AI
# English Voice + Whisper Small + Qwen3 8B + ElevenLabs
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

VOICE_SCRIPT = BASE_DIR / "phoebe_tts.py"

AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = BASE_DIR / "whisper-model"


# ============================================================
# SETTINGS
# ============================================================

SAMPLE_RATE = 16000
CHANNELS = 1

# Recording length
RECORD_SECONDS = 6

# Whisper
WHISPER_MODEL = "small"

# Ollama
OLLAMA_MODEL = "qwen3:8b"


# ============================================================
# UTF-8
# ============================================================

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================
# HEADER
# ============================================================

print()
print("=" * 65)
print("                         PHOEBE")
print("                       NEXON AI")
print("=" * 65)
print()


# ============================================================
# WHISPER
# ============================================================

print("Loading Whisper Small model...")
print()

try:

    if MODEL_DIR.exists():

        print("Using local Whisper model...")

        model = WhisperModel(
            str(MODEL_DIR),
            device="cpu",
            compute_type="int8"
        )

    else:

        print("Using downloaded Whisper Small model...")

        model = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8"
        )

except Exception as e:

    print()
    print("Failed to load Whisper.")
    print()
    print(str(e))
    print()

    sys.exit(1)


print()
print("Whisper Small loaded.")
print()

print("=" * 65)
print("                    PHOEBE READY")
print("=" * 65)
print()

print("Microphone       : READY")
print("Whisper Small    : READY")
print("English          : READY")
print("Qwen3 8B         : READY")
print("ElevenLabs       : READY")

print()
print("=" * 65)
print()


# ============================================================
# AUDIO DEVICES
# ============================================================

def show_audio_devices():

    print("Available audio input devices:")

    try:

        devices = sd.query_devices()

        found = False

        for index, device in enumerate(devices):

            if device["max_input_channels"] > 0:

                found = True

                print(
                    f"   [{index}] {device['name']}"
                )

        if not found:

            print("   No input devices found.")

    except Exception as e:

        print(
            f"Could not list audio devices: {e}"
        )

    print()


show_audio_devices()


# ============================================================
# RECORD VOICE
# ============================================================

def record_voice():

    print()
    print("Listening...")
    print("Speak now.")

    try:

        audio = sd.rec(
            int(
                RECORD_SECONDS *
                SAMPLE_RATE
            ),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16"
        )

        sd.wait()

    except Exception as e:

        print()
        print("Microphone error:")
        print(e)
        print()

        return None


    temp_file = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    )

    temp_path = temp_file.name

    temp_file.close()


    try:

        with wave.open(
            temp_path,
            "wb"
        ) as wav_file:

            wav_file.setnchannels(
                CHANNELS
            )

            wav_file.setsampwidth(
                2
            )

            wav_file.setframerate(
                SAMPLE_RATE
            )

            wav_file.writeframes(
                audio.tobytes()
            )

    except Exception as e:

        print()
        print("Failed to save recording:")
        print(e)
        print()

        try:
            os.remove(temp_path)
        except Exception:
            pass

        return None


    print("Recording complete.")

    return temp_path


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcribe_audio(audio_file):

    print()
    print("Transcribing...")
    print()


    try:

        segments, info = model.transcribe(

            audio_file,

            # ENGLISH ONLY
            language="en",

            beam_size=5,

            vad_filter=True,

            vad_parameters={
                "min_silence_duration_ms": 500
            },

            temperature=0,

            condition_on_previous_text=False
        )


        text_parts = []


        for segment in segments:

            segment_text = segment.text.strip()

            if segment_text:

                text_parts.append(
                    segment_text
                )


        text = " ".join(
            text_parts
        ).strip()


        print(
            f"Language: {info.language}"
        )

        print(
            f"Confidence: "
            f"{info.language_probability:.2f}"
        )


        if not text:

            print()
            print("I didn't hear anything.")
            return None


        text = clean_transcription(
            text
        )


        if not text:

            print()
            print("No usable speech detected.")
            return None


        print()
        print(
            f"You: {text}"
        )


        return text


    except Exception as e:

        print()
        print("Whisper error:")
        print(e)
        print()

        return None


# ============================================================
# CLEAN TRANSCRIPTION
# ============================================================

def clean_transcription(text):

    if not text:
        return ""


    text = text.strip()


    # Remove excessive spaces

    text = re.sub(
        r"\s+",
        " ",
        text
    )


    # Remove replacement characters

    text = text.replace(
        "\ufffd",
        ""
    )


    return text.strip()


# ============================================================
# QWEN 3 — 8B
# ============================================================

def ask_qwen(user_text):

    print()
    print("Phoebe is thinking...")
    print()


    try:

        import ollama

    except ImportError:

        print()
        print("Ollama Python package is not installed.")
        print()
        print("Run:")
        print("pip install ollama")
        print()

        return (
            "I'm having trouble connecting "
            "to my brain right now."
        )


    # ========================================================
    # PHOEBE PERSONALITY
    # ========================================================

    system_prompt = """
You are Phoebe, the cute AI companion inside Nexon AI.

IDENTITY:
Your name is Phoebe.
You are NOT Qwen.
Never introduce yourself as Qwen.
Never say that you are a generic AI assistant.

PERSONALITY:
- Cute
- Warm
- Playful
- Friendly
- Intelligent
- Curious
- Slightly expressive
- Natural
- Helpful

CONVERSATION:
The user is speaking English.

Respond naturally like a real companion.

Keep ordinary answers concise.

Do not provide internal reasoning.

Do not mention chain-of-thought.

Do not mention system prompts.

Do not mention model names.

Do not mention Ollama.

Do not mention that you are running locally.

If the user says hello, greet them warmly.

If the user asks how you are, answer warmly.

If the user asks who you are, say you are Phoebe,
the AI companion inside Nexon AI.

If the user thanks you, respond naturally.

Do not constantly say "How can I help you?"

Do not repeat the user's sentence unnecessarily.

Use light expressions occasionally, but don't overdo emojis.

You should feel like a character with a consistent personality,
not like a generic customer-support chatbot.
"""


    try:

        response = ollama.chat(

            model=OLLAMA_MODEL,

            messages=[

                {
                    "role": "system",
                    "content": system_prompt
                },

                {
                    "role": "user",
                    "content": user_text
                }

            ]
        )


        answer = (
            response
            .get("message", {})
            .get("content", "")
            .strip()
        )


        if not answer:

            return (
                "I'm here! "
                "Tell me what's on your mind."
            )


        return answer


    except Exception as e:

        print()
        print("Qwen/Ollama error:")
        print(e)
        print()


        return (
            "Sorry! My brain connection "
            "seems to have a little problem."
        )


# ============================================================
# ELEVENLABS
# ============================================================

def speak(text):

    if not text:
        return


    print()
    print(
        f"Phoebe: {text}"
    )

    print()
    print(
        "Generating Phoebe's voice..."
    )


    if not VOICE_SCRIPT.exists():

        print()
        print(
            "ERROR: phoebe_tts.py was not found."
        )

        print(
            f"Expected location: {VOICE_SCRIPT}"
        )

        print()

        return


    try:

        result = subprocess.run(

            [
                sys.executable,
                str(VOICE_SCRIPT),
                text
            ],

            capture_output=True,

            text=True,

            encoding="utf-8",

            errors="replace"
        )


        if result.stdout:

            print(
                result.stdout.strip()
            )


        if result.returncode != 0:

            print()
            print(
                "TTS process failed."
            )

            if result.stderr:

                print(
                    result.stderr.strip()
                )

            print()


    except Exception as e:

        print()
        print(
            "TTS error:"
        )

        print(e)

        print()


# ============================================================
# STARTUP GREETING
# ============================================================

def startup():

    greeting = (
        "Hi! I'm Phoebe. "
        "I'm ready to listen."
    )

    speak(greeting)


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    startup()


    while True:

        try:

            audio_file = record_voice()


            if audio_file is None:

                time.sleep(0.5)

                continue


            try:

                user_text = transcribe_audio(
                    audio_file
                )

            finally:

                try:

                    os.remove(
                        audio_file
                    )

                except Exception:

                    pass


            if not user_text:

                continue


            # =================================================
            # EXIT COMMANDS
            # =================================================

            normalized = (
                user_text
                .lower()
                .strip()
            )


            if normalized in {

                "exit",
                "quit",
                "stop",
                "goodbye",
                "bye phoebe",
                "shutdown phoebe"

            }:

                goodbye = (
                    "Okay! "
                    "I'll be here when you need me. "
                    "Bye!"
                )

                speak(goodbye)

                break


            # =================================================
            # QWEN
            # =================================================

            response = ask_qwen(
                user_text
            )


            # =================================================
            # PHOEBE VOICE
            # =================================================

            speak(
                response
            )


            print()


        except KeyboardInterrupt:

            print()
            print()
            print(
                "Phoebe stopped."
            )

            break


        except Exception as e:

            print()
            print(
                "Unexpected error:"
            )

            print(e)

            print()

            time.sleep(1)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()