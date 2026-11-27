"""
JARVIS / PHOEBE - HIGH-ACCURACY SPEECH-TO-TEXT ENGINE
======================================================
Speech recognition powered by faster-whisper with:
  - Adaptive Streaming Voice Activity Detection (VAD)
  - Pre-speech audio buffering (never clips first syllable)
  - Domain-specific prompt conditioning
  - Dynamic audio normalization & DC-offset removal
  - Structured microphone diagnostics & error classification
  - stdout is reserved for JSON IPC — all diagnostics go to stderr.
"""

import collections
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SAMPLES = 1600  # 100ms chunks at 16kHz
PRE_SPEECH_CHUNKS = 4  # 400ms pre-roll rolling buffer
SPEECH_RMS_THRESHOLD = 90.0  # RMS floor for speech detection
SILENCE_TIMEOUT_SECONDS = 0.65  # Trailing silence before ending utterance
MAX_UTTERANCE_SECONDS = 8.0  # Max single command duration
IDLE_LISTEN_SECONDS = 1.2  # Max wait if no speech begins

INITIAL_PROMPT = (
    "Phoebe, Jarvis, open Steam, open Chrome, launch Spotify, Discord, VS Code, "
    "YouTube, Google, volume up, volume down, mute, unmute, "
    "what is the time, system diagnostics, battery status, take screenshot."
)


@dataclass
class ListenResult:
    ok: bool
    text: str = ""
    status: str = "ok"          # "ok" | "silence" | "error"
    error_code: str = ""        # "no_input_device" | "permission_denied" | "device_disconnected" | "stream_error" | "transcription_failed"
    error_message: str = ""


def classify_mic_exception(exc: Exception) -> tuple[str, str]:
    """Classify a sounddevice/PortAudio exception into a structured code and user message."""
    raw = str(exc).lower()
    if any(k in raw for k in ("permission", "access denied", "access is denied", "not allowed", "privacy")):
        return (
            "permission_denied",
            "Microphone access was denied. Please allow microphone permissions in Windows Privacy Settings.",
        )
    if any(k in raw for k in ("no default input", "no input device", "invalid number of channels", "-9996", "device unavailable")):
        return (
            "no_input_device",
            "No active microphone was detected. Please connect or enable an input device.",
        )
    if any(k in raw for k in ("disconnected", "unplugged", "invalid device", "-9999", "host error")):
        return (
            "device_disconnected",
            "The microphone was disconnected or became unavailable.",
        )
    return (
        "stream_error",
        "Audio input stream failed. Check your microphone connection and try again.",
    )


def check_microphone() -> Dict[str, Any]:
    """Inspect available audio input devices without recording audio."""
    try:
        devices = sd.query_devices()
        inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        if not inputs:
            return {
                "ok": False,
                "error_code": "no_input_device",
                "error_message": "No active microphone was detected. Please connect or enable an input device.",
                "input_count": 0,
            }
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
        default_name = ""
        if isinstance(default_in, int) and 0 <= default_in < len(devices):
            default_name = devices[default_in].get("name", "")
        elif inputs:
            default_name = inputs[0].get("name", "")
        return {
            "ok": True,
            "input_count": len(inputs),
            "default_device": default_name,
        }
    except Exception as exc:
        code, msg = classify_mic_exception(exc)
        return {
            "ok": False,
            "error_code": code,
            "error_message": msg,
            "input_count": 0,
        }


class SpeechRecognizer:
    def __init__(self, model_name: Optional[str] = None):
        """Initialize the faster-whisper model."""
        stt_model = model_name or os.getenv("JARVIS_STT_MODEL", "base.en").strip()
        threads = min(6, os.cpu_count() or 4)

        print(f"[Jarvis STT] Initializing speech engine with model '{stt_model}' ({threads} CPU threads)...", file=sys.stderr)
        self.model = WhisperModel(
            stt_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=threads,
        )
        self.model_name = stt_model
        self.last_error: Optional[Dict[str, str]] = None
        print(f"[Jarvis STT] Google Voice-grade speech recognition ready ({stt_model}).", file=sys.stderr)

    def _normalize_audio(self, audio_int16: np.ndarray) -> np.ndarray:
        """Apply DC-offset removal and peak normalization to float32."""
        audio_f = audio_int16.astype(np.float32) / 32768.0
        audio_f = audio_f - np.mean(audio_f)
        peak = float(np.max(np.abs(audio_f)))
        if 0.04 < peak < 0.8:
            audio_f = audio_f * (0.85 / peak)
        return np.ascontiguousarray(audio_f, dtype=np.float32)

    def listen_and_transcribe_result(
        self,
        idle_timeout: float = IDLE_LISTEN_SECONDS,
        max_duration: float = MAX_UTTERANCE_SECONDS,
        silence_timeout: float = SILENCE_TIMEOUT_SECONDS,
    ) -> ListenResult:
        """Listen for a single utterance and return a structured ListenResult."""
        self.last_error = None

        pre_check = check_microphone()
        if not pre_check.get("ok"):
            code = pre_check.get("error_code", "no_input_device")
            msg = pre_check.get("error_message", "Microphone unavailable.")
            self.last_error = {"code": code, "message": msg}
            print(f"[Jarvis Mic Error] ({code}): {msg}", file=sys.stderr)
            return ListenResult(ok=False, status="error", error_code=code, error_message=msg)

        pre_buffer = collections.deque(maxlen=PRE_SPEECH_CHUNKS)
        speech_chunks = []
        is_speaking = False
        silence_chunks_count = 0
        overflow_count = 0
        silence_chunks_limit = int(silence_timeout / (CHUNK_SAMPLES / SAMPLE_RATE))
        max_chunks = int(max_duration / (CHUNK_SAMPLES / SAMPLE_RATE))
        idle_chunks_limit = int(idle_timeout / (CHUNK_SAMPLES / SAMPLE_RATE))

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
                idle_count = 0

                while True:
                    data, overflowed = stream.read(CHUNK_SAMPLES)
                    if overflowed:
                        overflow_count += 1
                    chunk = data.flatten()
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

                    if not is_speaking:
                        pre_buffer.append(chunk)
                        idle_count += 1

                        if rms >= SPEECH_RMS_THRESHOLD:
                            is_speaking = True
                            speech_chunks.extend(pre_buffer)
                            pre_buffer.clear()
                            silence_chunks_count = 0
                        elif idle_count >= idle_chunks_limit:
                            return ListenResult(ok=True, text="", status="silence")
                    else:
                        speech_chunks.append(chunk)

                        if rms < SPEECH_RMS_THRESHOLD:
                            silence_chunks_count += 1
                            if silence_chunks_count >= silence_chunks_limit:
                                break
                        else:
                            silence_chunks_count = 0

                        if len(speech_chunks) >= max_chunks:
                            break

        except Exception as e:
            code, msg = classify_mic_exception(e)
            self.last_error = {"code": code, "message": msg}
            print(f"[Jarvis Mic Error] ({code}): {e}", file=sys.stderr)
            return ListenResult(ok=False, status="error", error_code=code, error_message=msg)

        if overflow_count > 10:
            print(f"[Jarvis Mic Warning]: {overflow_count} audio buffer overflows occurred.", file=sys.stderr)

        if not speech_chunks:
            return ListenResult(ok=True, text="", status="silence")

        raw_audio = np.concatenate(speech_chunks)
        audio_float = self._normalize_audio(raw_audio)

        try:
            segments, _info = self.model.transcribe(
                audio_float,
                language="en",
                beam_size=5,
                best_of=5,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={
                    "min_speech_duration_ms": 200,
                    "min_silence_duration_ms": 300,
                    "threshold": 0.45,
                },
                initial_prompt=INITIAL_PROMPT,
            )

            text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
            transcript = " ".join(text_parts).strip()
            transcript = re.sub(r"[.?!,;:]+$", "", transcript).strip()

            if not transcript:
                return ListenResult(ok=True, text="", status="silence")

            return ListenResult(ok=True, text=transcript, status="ok")

        except Exception as e:
            msg = "Speech recognition failed while processing audio."
            self.last_error = {"code": "transcription_failed", "message": msg}
            print(f"[Jarvis STT Error] ({type(e).__name__}): {e}", file=sys.stderr)
            return ListenResult(
                ok=False,
                status="error",
                error_code="transcription_failed",
                error_message=msg,
            )

    def listen_and_transcribe(
        self,
        idle_timeout: float = IDLE_LISTEN_SECONDS,
        max_duration: float = MAX_UTTERANCE_SECONDS,
        silence_timeout: float = SILENCE_TIMEOUT_SECONDS,
    ) -> str:
        """Backwards-compatible helper returning transcribed text or empty string."""
        res = self.listen_and_transcribe_result(
            idle_timeout=idle_timeout,
            max_duration=max_duration,
            silence_timeout=silence_timeout,
        )
        return res.text if res.ok else ""


_recognizer_instance = None


def get_recognizer() -> SpeechRecognizer:
    global _recognizer_instance
    if _recognizer_instance is None:
        _recognizer_instance = SpeechRecognizer()
    return _recognizer_instance


def listen_once() -> str:
    """Convenience helper to listen for one utterance and return text."""
    recognizer = get_recognizer()
    return recognizer.listen_and_transcribe()


if __name__ == "__main__":
    recognizer = get_recognizer()
    print("Testing STT: Speak a command now (e.g. 'Jarvis, open Steam' or 'what is the time')...", file=sys.stderr)
    text = recognizer.listen_and_transcribe(idle_timeout=5.0)
    print(f"Transcribed: '{text}'", file=sys.stderr)
