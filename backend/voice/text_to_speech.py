import asyncio
import edge_tts
import os

VOICE = "en-US-AnaNeural"

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__),
    "audio",
    "phoebe.mp3"
)


async def generate_voice(text: str):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    communicate = edge_tts.Communicate(
        text,
        VOICE,
        rate="+20%",
        pitch="+35Hz"
    )

    await communicate.save(OUTPUT_FILE)
    return OUTPUT_FILE


def speak(text: str):
    return asyncio.run(generate_voice(text))


if __name__ == "__main__":
    speak("Pheepi Chupi! Hello! I'm Nexon!")
    print(f"Voice generated successfully: {OUTPUT_FILE}")