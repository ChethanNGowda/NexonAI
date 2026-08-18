import sounddevice as sd
import numpy as np
import wave
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CHANNELS = 1
DURATION = 5
OUTPUT_FILE = "voice_test.wav"

print("🎤 Speak now for 5 seconds...")

audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=CHANNELS,
    dtype="int16"
)

sd.wait()

print("✅ Recording finished.")

with wave.open(OUTPUT_FILE, "wb") as wav:
    wav.setnchannels(CHANNELS)
    wav.setsampwidth(2)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(audio.tobytes())

print("🧠 Loading Whisper...")

model = WhisperModel(
    "whisper-model",
    device="cpu",
    compute_type="int8"
)

print("🔎 Transcribing...")

segments, info = model.transcribe(
    OUTPUT_FILE,
    beam_size=5
)

text = ""

for segment in segments:
    text += segment.text

print()
print("🐾 Phoebe heard:")
print(text.strip())
print()