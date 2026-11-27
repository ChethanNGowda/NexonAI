"""JARVIS - TEXT TO SPEECH & AUDIO PLAYBACK ENGINE (OpenJarvis Unified Bridge)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIO_DIR = BASE_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural")

_is_speaking = False


def _play_audio_bytes(audio_bytes: bytes, audio_format: str = "mp3") -> None:
    """Play audio bytes through speakers using sounddevice and soundfile."""
    global _is_speaking
    import io
    import sounddevice as sd
    import soundfile as sf

    try:
        _is_speaking = True
        with io.BytesIO(audio_bytes) as buf:
            data, sample_rate = sf.read(buf, dtype="float32")
            sd.play(data, sample_rate)
            sd.wait()
    except Exception:
        # Fallback to temp file if direct stream reading fails on format
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tmp_path.write_bytes(audio_bytes)
            data, sample_rate = sf.read(str(tmp_path), dtype="float32")
            sd.play(data, sample_rate)
            sd.wait()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    finally:
        _is_speaking = False


def speak(text: str, voice: str = DEFAULT_VOICE, play_audio: bool = True) -> str:
    """
    Synthesize text with Jarvis voice and play directly through speakers.
    Returns path to the generated audio file.
    """
    clean_text = text.strip()
    if not clean_text:
        return ""

    out_file = AUDIO_DIR / "jarvis_response.mp3"

    try:
        from openjarvis.speech._tts_discovery import get_tts_backend
        backend = get_tts_backend("edge_tts")
        if backend is not None:
            result = backend.synthesize(clean_text, voice_id=voice)
            out_file.write_bytes(result.audio)
            if play_audio:
                _play_audio_bytes(result.audio, result.format)
            return str(out_file)
    except Exception as e:
        print(f"[Speech Synthesis Warning]: {e}. Trying direct fallback...", file=sys.stderr)

    # Fallback to offline pyttsx3
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 185)
        if play_audio:
            engine.say(clean_text)
            engine.runAndWait()
        return ""
    except Exception as e:
        print(f"[TTS Fallback Error]: {e}", file=sys.stderr)
        return ""


def stop_audio():
    """Immediately stop any current audio playback."""
    global _is_speaking
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass
    _is_speaking = False


def is_speaking() -> bool:
    """Return True if Jarvis is currently speaking."""
    return _is_speaking


if __name__ == "__main__":
    test_msg = sys.argv[1] if len(sys.argv) > 1 else "Jarvis voice system online and fully operational, sir."
    print(f"Testing Jarvis voice: '{test_msg}'")
    speak(test_msg, play_audio=True)
    print("Speech test completed.")
