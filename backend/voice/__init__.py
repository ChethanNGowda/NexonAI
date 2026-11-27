"""NexonAI Voice Package — Speech-to-Text (Faster-Whisper) and Text-to-Speech (Edge TTS / optional ElevenLabs)."""

from backend.voice.stt import ListenResult, SpeechRecognizer, check_microphone, get_recognizer, listen_once
from backend.voice.tts import (
    AVAILABLE_EDGE_VOICES,
    get_voice_id,
    is_speaking,
    set_speech_rate,
    set_speech_volume,
    set_voice_id,
    speak,
    stop_audio,
)

__all__ = [
    "AVAILABLE_EDGE_VOICES",
    "ListenResult",
    "SpeechRecognizer",
    "check_microphone",
    "get_recognizer",
    "get_voice_id",
    "is_speaking",
    "listen_once",
    "set_speech_rate",
    "set_speech_volume",
    "set_voice_id",
    "speak",
    "stop_audio",
]
