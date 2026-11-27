"""JARVIS - TEXT TO SPEECH & AUDIO PLAYBACK ENGINE.

Synthesizes speech using Microsoft Edge TTS (en-GB-RyanNeural by default)
with pyttsx3 offline fallback. Respects speech rate and volume from settings.
stdout is reserved for JSON IPC — all diagnostics go to stderr.
"""

from __future__ import annotations

import asyncio
import io
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
_current_rate: float = 1.0   # multiplier; 1.0 = normal
_current_volume: int = 100   # 0–100


def set_speech_rate(rate: float) -> None:
    """Set the speech playback rate multiplier (e.g. 1.2 = 20% faster)."""
    global _current_rate
    _current_rate = max(0.5, min(2.0, float(rate)))


def set_speech_volume(volume: int) -> None:
    """Set output volume 0–100."""
    global _current_volume
    _current_volume = max(0, min(100, int(volume)))


def _play_audio_bytes(audio_bytes: bytes, audio_format: str = "mp3") -> None:
    """Play raw audio bytes through speakers via sounddevice + soundfile."""
    global _is_speaking
    try:
        import sounddevice as sd
        import soundfile as sf

        _is_speaking = True
        try:
            with io.BytesIO(audio_bytes) as buf:
                data, sample_rate = sf.read(buf, dtype="float32")
        except Exception:
            # soundfile can't read mp3 from BytesIO on some platforms — write to temp
            with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                tmp_path.write_bytes(audio_bytes)
                data, sample_rate = sf.read(str(tmp_path), dtype="float32")
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        # Apply volume scaling
        if _current_volume != 100:
            data = data * (_current_volume / 100.0)

        sd.play(data, sample_rate)
        sd.wait()
    except Exception as e:
        print(f"[TTS Playback Error]: {e}", file=sys.stderr)
    finally:
        _is_speaking = False


async def _synthesize_edge_tts(text: str, voice: str, rate: float) -> Optional[bytes]:
    """Async Edge TTS synthesis. Returns raw MP3 bytes or None on failure."""
    try:
        import edge_tts

        # edge-tts rate format: "+20%" or "-10%"
        rate_pct = int((rate - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

        communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
        audio_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buf.write(chunk["data"])

        audio_bytes = audio_buf.getvalue()
        return audio_bytes if audio_bytes else None

    except ImportError:
        print("[TTS] edge-tts not installed. Install with: pip install edge-tts", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[TTS Edge Error]: {e}", file=sys.stderr)
        return None


def speak(text: str, voice: str = DEFAULT_VOICE, play_audio: bool = True) -> str:
    """
    Synthesize text with Jarvis voice and optionally play through speakers.
    Returns path to the generated audio file, or empty string on failure.
    stdout is never written — all messages go to stderr.
    """
    clean_text = text.strip()
    if not clean_text:
        return ""

    out_file = AUDIO_DIR / "jarvis_response.mp3"

    # 1. Try Microsoft Edge TTS
    try:
        audio_bytes = asyncio.run(
            _synthesize_edge_tts(clean_text, voice, _current_rate)
        )
        if audio_bytes:
            out_file.write_bytes(audio_bytes)
            if play_audio:
                _play_audio_bytes(audio_bytes, "mp3")
            return str(out_file)
        print("[TTS] Edge TTS returned empty audio. Trying offline fallback...", file=sys.stderr)
    except RuntimeError:
        # asyncio.run() can fail if there's already an event loop (e.g. inside async context)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            audio_bytes = loop.run_until_complete(
                _synthesize_edge_tts(clean_text, voice, _current_rate)
            )
            if audio_bytes:
                out_file.write_bytes(audio_bytes)
                if play_audio:
                    _play_audio_bytes(audio_bytes, "mp3")
                return str(out_file)
        except Exception as e:
            print(f"[TTS Loop Fallback Error]: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[TTS Edge Synthesis Error]: {e}", file=sys.stderr)

    # 2. Offline pyttsx3 fallback
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # Approximate rate: pyttsx3 default is ~200 wpm; apply our multiplier
        base_rate = engine.getProperty("rate") or 200
        engine.setProperty("rate", int(base_rate * _current_rate))
        engine.setProperty("volume", _current_volume / 100.0)
        if play_audio:
            engine.say(clean_text)
            engine.runAndWait()
        return ""
    except Exception as e:
        print(f"[TTS pyttsx3 Fallback Error]: {e}", file=sys.stderr)

    return ""


def stop_audio() -> None:
    """Immediately stop any current audio playback."""
    global _is_speaking
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass
    _is_speaking = False


def is_speaking() -> bool:
    """Return True if audio is currently being played."""
    return _is_speaking


if __name__ == "__main__":
    test_msg = sys.argv[1] if len(sys.argv) > 1 else "Jarvis voice system online and fully operational, sir."
    print(f"Testing Jarvis voice: '{test_msg}'", file=sys.stderr)
    speak(test_msg, play_audio=True)
    print("Speech test completed.", file=sys.stderr)
