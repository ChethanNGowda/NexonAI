"""Edge TTS backend — high-quality zero-cost neural speech synthesis via Microsoft Edge TTS with offline Windows SAPI fallback."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import List

from openjarvis.core.registry import TTSRegistry
from openjarvis.speech.tts import TTSBackend, TTSResult

logger = logging.getLogger(__name__)

DEFAULT_EDGE_VOICE = "en-GB-RyanNeural"  # Jarvis persona


def _run_async(coro):
    """Run an async coroutine synchronously, handling nested event loops if necessary."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return loop.run_until_complete(coro)


async def _synthesize_edge_tts(text: str, voice: str, rate_str: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def _synthesize_offline_sapi(text: str) -> bytes:
    """Offline Windows SAPI / pyttsx3 speech fallback generating WAV/PCM bytes."""
    try:
        import tempfile
        import pyttsx3
        from pathlib import Path

        engine = pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            engine.save_to_file(text, str(tmp_path))
            engine.runAndWait()
            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                return tmp_path.read_bytes()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    except Exception as e:
        logger.warning("Offline SAPI fallback failed: %s", e)
    return b""


@TTSRegistry.register("edge_tts")
class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge TTS backend with Jarvis voice and offline SAPI fallback."""

    backend_id = "edge_tts"

    def __init__(self, *, default_voice: str = DEFAULT_EDGE_VOICE) -> None:
        self.default_voice = default_voice

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
        output_format: str = "mp3",
    ) -> TTSResult:
        voice = voice_id or self.default_voice
        pct_change = int(round((speed - 1.0) * 100))
        rate_str = f"{pct_change:+d}%"

        try:
            audio_bytes = _run_async(_synthesize_edge_tts(text, voice, rate_str))
            if audio_bytes:
                return TTSResult(
                    audio=audio_bytes,
                    format="mp3",
                    voice_id=voice,
                    sample_rate=24000,
                    metadata={"backend": "edge_tts", "rate": rate_str},
                )
        except Exception as e:
            logger.warning("Edge TTS online synthesis failed: %s. Falling back to offline voice...", e)

        # Fallback to offline SAPI
        wav_bytes = _synthesize_offline_sapi(text)
        if wav_bytes:
            return TTSResult(
                audio=wav_bytes,
                format="wav",
                voice_id="sapi5",
                sample_rate=22050,
                metadata={"backend": "sapi_offline"},
            )

        raise RuntimeError("Failed to synthesize speech using Edge TTS or offline fallback.")

    def available_voices(self) -> List[str]:
        return [
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-AriaNeural",
        ]

    def health(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            try:
                import pyttsx3
                return True
            except ImportError:
                return False


__all__ = ["EdgeTTSBackend"]
