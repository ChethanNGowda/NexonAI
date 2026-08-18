import os
import base64
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")

if not api_key:
    raise RuntimeError("ELEVENLABS_API_KEY is missing from .env")

client = ElevenLabs(api_key=api_key)

description = """
A cute young adult female anime-inspired desktop companion.
Small, bright, playful and charming voice with a soft high pitch.
Very expressive, energetic and cheerful, with a slightly mischievous
personality. Clear natural English pronunciation. She sounds adorable
and lively without sounding like a child. She can naturally express
excitement, curiosity, teasing, surprise, happiness and gentle calmness.
The voice should feel like a polished chibi game character and a friendly
AI companion.
"""

text = """
Hii~! I'm Phoebe! Ehehe~ it's nice to meet you!
I'm your little desktop companion, and I'll do my best to help you.
So... what are we doing today? ✨
"""

print("🎀 Creating Phoebe voice previews...")

result = client.text_to_voice.design(
    model_id="eleven_ttv_v3",
    voice_description=description,
    text=text
)

print(f"\nGenerated {len(result.previews)} previews.\n")

for i, preview in enumerate(result.previews, start=1):
    filename = f"phoebe_preview_{i}.mp3"

    audio = base64.b64decode(preview.audio_base_64)

    with open(filename, "wb") as f:
        f.write(audio)

    print(f"🎧 Preview {i}")
    print(f"   File: {filename}")
    print(f"   Generated Voice ID: {preview.generated_voice_id}")
    print()