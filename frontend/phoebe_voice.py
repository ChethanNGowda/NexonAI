import base64
import os

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs


load_dotenv()

api_key = os.getenv("ELEVENLABS_API_KEY")

if not api_key:
    raise RuntimeError("ELEVENLABS_API_KEY is missing from .env")

client = ElevenLabs(api_key=api_key)

description = """
A warm, friendly desktop companion voice.
Clear natural English pronunciation, upbeat delivery, and a calm helpful tone.
The voice should sound like a polished assistant character and a friendly AI
companion without sounding robotic.
"""

text = """
Hi! I'm Bob. It's nice to meet you!
I'm your little desktop companion, and I'll do my best to help you.
So... what are we doing today?
"""

print("Creating Bob voice previews...")

result = client.text_to_voice.design(
    model_id="eleven_ttv_v3",
    voice_description=description,
    text=text,
)

print(f"\nGenerated {len(result.previews)} previews.\n")

for i, preview in enumerate(result.previews, start=1):
    filename = f"bob_preview_{i}.mp3"
    audio = base64.b64decode(preview.audio_base_64)

    with open(filename, "wb") as f:
        f.write(audio)

    print(f"Preview {i}")
    print(f"   File: {filename}")
    print(f"   Generated Voice ID: {preview.generated_voice_id}")
    print()
