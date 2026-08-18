import sys
from pathlib import Path
import edge_tts
import asyncio

# ============================================================
# PHOEBE — MICROSOFT EDGE TTS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = AUDIO_DIR / "phoebe_response.mp3"

# Microsoft voice
VOICE = "en-US-AnaNeural"


async def generate_voice(text: str):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE
    )

    await communicate.save(str(OUTPUT_FILE))


def main():

    if len(sys.argv) < 2:
        print("No text supplied.")
        return 1

    text = " ".join(sys.argv[1:]).strip()

    if not text:
        print("No text supplied.")
        return 1

    print(f"Generating voice using {VOICE}...")

    try:
        asyncio.run(generate_voice(text))

        print(f"Created: {OUTPUT_FILE}")
        return 0

    except Exception as e:
        print("ERROR: Microsoft TTS failed.")
        print(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())