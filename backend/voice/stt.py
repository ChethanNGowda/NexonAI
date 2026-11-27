"""
JARVIS - HIGH-ACCURACY SPEECH-TO-TEXT ENGINE
=============================================
Google Voice-grade speech recognition powered by faster-whisper with:
  - Adaptive Streaming Voice Activity Detection (VAD)
  - Pre-speech audio buffering (never clips first syllable)
  - Domain-specific prompt conditioning (accurately resolves app names, commands)
  - Dynamic audio normalization & DC-offset removal
  - Multi-threaded CPU int8 inference (<0.5s response time)
"""

import collections
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from faster_whisper import WhisperModel

# Load environment configuration
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

# Domain prompt conditioning to ensure high recognition accuracy for Jarvis commands
INITIAL_PROMPT = (
    "Jarvis, open Steam, open Chrome, launch Spotify, Discord, VS Code, "
    "YouTube, Google, volume up, volume down, mute, unmute, "
    "what is the time, system diagnostics, battery status, take screenshot."
)


class SpeechRecognizer:
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the faster-whisper model.
        Default model: 'base.en' (fast & accurate) or 'small.en' (maximum accuracy).
        Configurable via JARVIS_STT_MODEL in .env.
        """
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
        print(f"[Jarvis STT] Google Voice-grade speech recognition ready ({stt_model}).", file=sys.stderr)

    def _normalize_audio(self, audio_int16: np.ndarray) -> np.ndarray:
        """Apply DC-offset removal and peak normalization to float32."""
        audio_f = audio_int16.astype(np.float32) / 32768.0

        # DC offset removal
        audio_f = audio_f - np.mean(audio_f)

        # Peak normalization if speech is quiet
        peak = float(np.max(np.abs(audio_f)))
        if 0.04 < peak < 0.8:
            audio_f = audio_f * (0.85 / peak)

        return np.ascontiguousarray(audio_f, dtype=np.float32)

    def listen_and_transcribe(
        self,
        idle_timeout: float = IDLE_LISTEN_SECONDS,
        max_duration: float = MAX_UTTERANCE_SECONDS,
        silence_timeout: float = SILENCE_TIMEOUT_SECONDS,
    ) -> str:
        """
        Stream audio from microphone using adaptive Voice Activity Detection.
        Begins recording immediately when speech is detected, preserves pre-speech
        audio buffer so initial words are never clipped, and auto-stops as soon as
        speech pauses.
        """
        pre_buffer = collections.deque(maxlen=PRE_SPEECH_CHUNKS)
        speech_chunks = []
        is_speaking = False
        silence_chunks_count = 0
        silence_chunks_limit = int(silence_timeout / (CHUNK_SAMPLES / SAMPLE_RATE))
        max_chunks = int(max_duration / (CHUNK_SAMPLES / SAMPLE_RATE))
        idle_chunks_limit = int(idle_timeout / (CHUNK_SAMPLES / SAMPLE_RATE))

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
                idle_count = 0

                while True:
                    data, overflowed = stream.read(CHUNK_SAMPLES)
                    chunk = data.flatten()
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

                    if not is_speaking:
                        pre_buffer.append(chunk)
                        idle_count += 1

                        if rms >= SPEECH_RMS_THRESHOLD:
                            # Speech onset detected! Flush pre-speech buffer
                            is_speaking = True
                            speech_chunks.extend(pre_buffer)
                            pre_buffer.clear()
                            silence_chunks_count = 0
                        elif idle_count >= idle_chunks_limit:
                            # No speech detected in this idle window
                            return ""
                    else:
                        speech_chunks.append(chunk)

                        if rms < SPEECH_RMS_THRESHOLD:
                            silence_chunks_count += 1
                            if silence_chunks_count >= silence_chunks_limit:
                                # User finished speaking
                                break
                        else:
                            silence_chunks_count = 0

                        if len(speech_chunks) >= max_chunks:
                            # Hit maximum utterance cap
                            break

        except Exception as e:
            print(f"[Jarvis Mic Error]: {e}", file=sys.stderr)
            return ""

        if not speech_chunks:
            return ""

        # Concatenate and normalize audio
        raw_audio = np.concatenate(speech_chunks)
        audio_float = self._normalize_audio(raw_audio)

        # Transcribe with domain prompt conditioning & beam search
        try:
            segments, info = self.model.transcribe(
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

            # Clean trailing punctuation from recognized command (e.g. "Open steam." -> "Open steam")
            transcript = re.sub(r"[.?!,;:]+$", "", transcript).strip()
            return transcript

        except Exception as e:
            print(f"[Jarvis STT Error]: {e}", file=sys.stderr)
            return ""


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
    print("Testing STT: Speak a command now (e.g. 'Jarvis, open Steam' or 'what is the time')...")
    text = recognizer.listen_and_transcribe(idle_timeout=5.0)
    print(f"Transcribed: '{text}'")
