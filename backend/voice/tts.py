"""JARVIS / PHOEBE - TEXT TO SPEECH & AUDIO PLAYBACK ENGINE.

Synthesizes speech using Microsoft Edge TTS (default) with optional ElevenLabs
support (when configured in local .env) and pyttsx3 offline fallback.
Provides thread-safe and cross-process playback locking to prevent overlapping audio.
stdout is strictly reserved for JSON IPC — all diagnostics go to stderr.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIO_DIR = BASE_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE = os.getenv("JARVIS_VOICE", "en-GB-RyanNeural")

AVAILABLE_EDGE_VOICES = [
    "en-GB-RyanNeural",
    "en-GB-ThomasNeural",
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-AnaNeural",
]

_playback_lock = threading.Lock()
_stop_event = threading.Event()
_is_speaking = False
_current_voice: str = DEFAULT_VOICE
_current_rate: float = 1.0   # multiplier; 1.0 = normal (0.5 - 2.0)
_current_volume: int = 100   # 0 - 100

_LOCK_FILE = AUDIO_DIR / ".tts_playback.lock"
_INTERRUPT_FILE = AUDIO_DIR / ".tts_interrupt"


def set_voice_id(voice_id: str) -> None:
    """Set the active TTS voice ID (e.g. 'en-GB-RyanNeural' or 'elevenlabs')."""
    global _current_voice
    cleaned = str(voice_id or "").strip()
    if cleaned:
        _current_voice = cleaned


def get_voice_id() -> str:
    """Return the currently configured TTS voice ID."""
    return _current_voice


def set_speech_rate(rate: float) -> None:
    """Set the speech playback rate multiplier (0.5 - 2.0; 1.0 = normal)."""
    global _current_rate
    _current_rate = max(0.5, min(2.0, float(rate)))


def set_speech_volume(volume: int) -> None:
    """Set output volume 0 - 100."""
    global _current_volume
    _current_volume = max(0, min(100, int(volume)))


def _signal_cross_process_interrupt() -> None:
    """Signal any other NexonAI Python process playing audio to stop."""
    try:
        _INTERRUPT_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _acquire_cross_process_lock(timeout: float = 3.0):
    """Acquire an OS-level advisory file lock so daemon & worker cannot overlap."""
    try:
        import msvcrt
        fh = open(_LOCK_FILE, "a+b")
        deadline = time.time() + timeout
        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return fh
            except OSError:
                if time.time() >= deadline:
                    fh.close()
                    return None
                time.sleep(0.05)
    except Exception:
        return None


def _release_cross_process_lock(fh) -> None:
    if fh is None:
        return
    try:
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass


def _play_audio_bytes(audio_bytes: bytes, audio_format: str = "mp3") -> None:
    """Play raw audio bytes through speakers without overlapping prior playback."""
    global _is_speaking

    # Signal any active playback (in-process or cross-process) to stop first
    _stop_event.set()
    _signal_cross_process_interrupt()
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass

    with _playback_lock:
        cross_fh = _acquire_cross_process_lock(timeout=2.5)
        _stop_event.clear()
        start_ts = time.time()
        try:
            import sounddevice as sd
            import soundfile as sf

            _is_speaking = True
            try:
                with io.BytesIO(audio_bytes) as buf:
                    data, sample_rate = sf.read(buf, dtype="float32")
            except Exception:
                with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    tmp_path.write_bytes(audio_bytes)
                    data, sample_rate = sf.read(str(tmp_path), dtype="float32")
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)

            if _current_volume != 100:
                data = data * (_current_volume / 100.0)

            sd.play(data, sample_rate)

            # Poll playback cleanly so interruption is immediate and never hangs
            duration = len(data) / float(sample_rate) if sample_rate else 0.0
            deadline = time.time() + duration + 1.0
            while time.time() < deadline:
                if _stop_event.is_set():
                    sd.stop()
                    break
                try:
                    if _INTERRUPT_FILE.exists():
                        ts = float(_INTERRUPT_FILE.read_text(encoding="utf-8").strip() or "0")
                        if ts > start_ts:
                            sd.stop()
                            break
                except Exception:
                    pass
                try:
                    stream = sd.get_stream()
                    if stream is None or not stream.active:
                        break
                except Exception:
                    pass
                time.sleep(0.04)
        except Exception as e:
            print(f"[TTS Playback Error]: {e}", file=sys.stderr)
        finally:
            _is_speaking = False
            _release_cross_process_lock(cross_fh)


async def _synthesize_edge_tts(text: str, voice: str, rate: float) -> Optional[bytes]:
    """Async Edge TTS synthesis. Returns raw MP3 bytes or None on failure."""
    try:
        import edge_tts

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
        print("[TTS] edge-tts not installed.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[TTS Edge Error]: {e}", file=sys.stderr)
        return None


def _synthesize_elevenlabs(text: str) -> Optional[bytes]:
    """Optional ElevenLabs TTS synthesis. Never logs credentials; returns None on fallback."""
    api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    voice_id = (
        os.getenv("ELEVENLABS_VOICE_ID")
        or os.getenv("PHOEBE_VOICE_ID")
        or os.getenv("BOB_VOICE_ID")
        or ""
    ).strip()

    if not api_key or not voice_id:
        print("[TTS] ElevenLabs credentials/voice ID not configured; falling back to Edge TTS.", file=sys.stderr)
        return None

    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        )
        if isinstance(audio_iter, (bytes, bytearray)):
            data = bytes(audio_iter)
        else:
            data = b"".join(chunk for chunk in audio_iter if chunk)
        if data:
            print("[TTS] Provider used: elevenlabs", file=sys.stderr)
            return data
        print("[TTS] ElevenLabs returned empty audio; falling back to Edge TTS.", file=sys.stderr)
        return None
    except ImportError:
        print("[TTS] elevenlabs package not installed; falling back to Edge TTS.", file=sys.stderr)
        return None
    except Exception as e:
        # Never echo raw exception if it could include headers/keys; log exception type only
        print(f"[TTS] ElevenLabs synthesis failed ({type(e).__name__}); falling back to Edge TTS.", file=sys.stderr)
        return None


def _run_edge_tts(text: str, voice: str, rate: float) -> Optional[bytes]:
    try:
        return asyncio.run(_synthesize_edge_tts(text, voice, rate))
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(_synthesize_edge_tts(text, voice, rate))
        except Exception as e:
            print(f"[TTS Loop Fallback Error]: {e}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"[TTS Edge Synthesis Error]: {e}", file=sys.stderr)
        return None


def speak(
    text: str,
    voice: Optional[str] = None,
    play_audio: bool = True,
    provider: Optional[str] = None,
) -> str:
    """
    Synthesize text with the selected voice and optionally play through speakers.
    Returns path to the generated audio file, or empty string on fallback/failure.
    stdout is never written — all diagnostics go to stderr.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return ""

    selected_voice = (voice or _current_voice or DEFAULT_VOICE).strip()
    selected_provider = (
        provider
        or ("elevenlabs" if selected_voice.lower() == "elevenlabs" else "")
        or os.getenv("JARVIS_TTS_PROVIDER", "edge_tts")
    ).strip().lower()

    out_file = AUDIO_DIR / "jarvis_response.mp3"

    # 1. Optional ElevenLabs provider (only when explicitly requested/configured)
    if selected_provider == "elevenlabs":
        audio_bytes = _synthesize_elevenlabs(clean_text)
        if audio_bytes:
            out_file.write_bytes(audio_bytes)
            if play_audio:
                _play_audio_bytes(audio_bytes, "mp3")
            return str(out_file)

    # 2. Default Microsoft Edge TTS
    edge_voice = DEFAULT_VOICE if selected_voice.lower() == "elevenlabs" else selected_voice
    audio_bytes = _run_edge_tts(clean_text, edge_voice, _current_rate)
    if audio_bytes:
        print(f"[TTS] Provider used: edge_tts ({edge_voice})", file=sys.stderr)
        out_file.write_bytes(audio_bytes)
        if play_audio:
            _play_audio_bytes(audio_bytes, "mp3")
        return str(out_file)

    print("[TTS] Edge TTS returned empty audio. Trying offline fallback...", file=sys.stderr)

    # 3. Offline pyttsx3 fallback
    try:
        import pyttsx3
        with _playback_lock:
            engine = pyttsx3.init()
            base_rate = engine.getProperty("rate") or 200
            engine.setProperty("rate", int(base_rate * _current_rate))
            engine.setProperty("volume", _current_volume / 100.0)
            if play_audio:
                engine.say(clean_text)
                engine.runAndWait()
        print("[TTS] Provider used: pyttsx3", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"[TTS pyttsx3 Fallback Error]: {e}", file=sys.stderr)

    return ""


def stop_audio() -> None:
    """Immediately stop any current audio playback (in-process & cross-process)."""
    global _is_speaking
    _stop_event.set()
    _signal_cross_process_interrupt()
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
