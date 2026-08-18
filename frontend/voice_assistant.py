import pyttsx3

engine = pyttsx3.init()

engine.setProperty("rate", 175)
engine.setProperty("volume", 1.0)

voices = engine.getProperty("voices")

print("Available voices:")

for i, voice in enumerate(voices):
    print(i, voice.name)

# Use the first available voice for now
if voices:
    engine.setProperty("voice", voices[0].id)

print("\n🐾 Phoebe is ready!")

while True:

    text = input("\nYou: ")

    if text.lower() in ["exit", "quit", "stop"]:
        print("Phoebe: Bye~!")
        engine.say("Bye!")
        engine.runAndWait()
        break

    if not text.strip():
        continue

    if "hello" in text.lower():
        response = "Hello! I'm Phoebe~"

    elif "who are you" in text.lower():
        response = "I'm Phoebe, your Nexon AI assistant!"

    elif "what can you do" in text.lower():
        response = "I can help you control your computer, work with files, coding, and much more!"

    else:
        response = "Hmm... I'm still learning that one!"

    print("Phoebe:", response)

    engine.say(response)
    engine.runAndWait()