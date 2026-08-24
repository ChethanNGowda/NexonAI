import pyttsx3
import random
import datetime
import sys

# ============================================================
# PHOEBE TTS ENGINE
# ============================================================

class Phoebe:
    def __init__(self):
        print("🐾 Starting Phoebe...")

        try:
            self.engine = pyttsx3.init()
        except Exception as e:
            print(f"❌ Failed to initialize TTS: {e}")
            sys.exit(1)

        # Voice settings
        self.engine.setProperty("rate", 175)
        self.engine.setProperty("volume", 1.0)

        # Load voices
        self.voices = self.engine.getProperty("voices")

        self.select_voice()

        # Personality
        self.name = "Phoebe"

        self.greetings = [
            "Hello~!",
            "Hi there~!",
            "Hey! Phoebe here~!",
            "Hiiiii~!",
            "Hello, master~!",
            "Hey hey~! What are we doing today?"
        ]

        self.unknown_responses = [
            "Hmm... I don't know how to handle that yet~.",
            "I'm still learning that one!",
            "Ehehe... my brain hasn't learned that yet.",
            "I don't think I understand that command yet.",
            "That's outside my current abilities~.",
            "Give me some time to learn that!"
        ]

        self.confirmations = [
            "Got it~!",
            "Okay!",
            "Sure thing~!",
            "On it!",
            "Roger that~!",
            "Leave it to me!"
        ]

        print("\n🐾 Phoebe is ready!")

    # ========================================================
    # VOICE SELECTION
    # ========================================================

    def select_voice(self):

        if not self.voices:
            print("⚠️ No voices detected.")
            return

        print("\nAvailable voices:")

        for i, voice in enumerate(self.voices):
            print(f"  [{i}] {voice.name}")

        # Try to find a female voice
        preferred_keywords = [
            "female",
            "zira",
            "hazel",
            "susan",
            "aria",
            "samantha"
        ]

        selected_voice = None

        for voice in self.voices:

            voice_info = (
                voice.name + " " +
                getattr(voice, "id", "")
            ).lower()

            if any(keyword in voice_info for keyword in preferred_keywords):
                selected_voice = voice
                break

        # Fallback
        if selected_voice is None:
            selected_voice = self.voices[0]

        self.engine.setProperty(
            "voice",
            selected_voice.id
        )

        print(f"\n🎙️ Selected voice: {selected_voice.name}")

    # ========================================================
    # SPEAK
    # ========================================================

    def speak(self, text):

        print(f"🐾 Phoebe: {text}")

        try:
            self.engine.say(text)
            self.engine.runAndWait()

        except Exception as e:
            print(f"❌ TTS Error: {e}")

    # ========================================================
    # RESPONSE
    # ========================================================

    def process_command(self, text):

        command = text.lower().strip()

        # ----------------------------------------------------
        # EXIT
        # ----------------------------------------------------

        if command in ["exit", "quit", "stop", "bye"]:

            self.speak(
                "Okay~! I'll be waiting for you. Bye bye!"
            )

            return False

        # ----------------------------------------------------
        # GREETING
        # ----------------------------------------------------

        if any(word in command for word in [
            "hello",
            "hi",
            "hey",
            "hii"
        ]):

            self.speak(
                random.choice(self.greetings)
            )

            return True

        # ----------------------------------------------------
        # WHO ARE YOU
        # ----------------------------------------------------

        if "who are you" in command:

            self.speak(
                "I'm Phoebe, your Nexon AI assistant! "
                "I'm here to help you with your computer."
            )

            return True

        # ----------------------------------------------------
        # WHAT CAN YOU DO
        # ----------------------------------------------------

        if "what can you do" in command:

            self.speak(
                "I can help control your computer, "
                "work with files, understand code, "
                "assist with tasks, and eventually "
                "learn much more."
            )

            return True

        # ----------------------------------------------------
        # HELP
        # ----------------------------------------------------

        if command == "help":

            self.speak(
                "You can say hello, ask who I am, "
                "ask what I can do, ask for the time, "
                "or say exit to close me."
            )

            return True

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        if "time" in command:

            now = datetime.datetime.now()

            current_time = now.strftime("%I:%M %p")

            self.speak(
                f"It's {current_time} right now."
            )

            return True

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        if "date" in command or "today" in command:

            today = datetime.datetime.now()

            current_date = today.strftime(
                "%A, %d %B %Y"
            )

            self.speak(
                f"Today is {current_date}."
            )

            return True

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if "status" in command:

            self.speak(
                "All systems are running normally~. "
                "Phoebe is online and ready!"
            )

            return True

        # ----------------------------------------------------
        # THANK YOU
        # ----------------------------------------------------

        if any(word in command for word in [
            "thank you",
            "thanks"
        ]):

            self.speak(
                random.choice([
                    "You're welcome~!",
                    "Anytime!",
                    "Ehehe, no problem~!",
                    "Of course!"
                ])
            )

            return True

        # ----------------------------------------------------
        # COMPLIMENT
        # ----------------------------------------------------

        if any(word in command for word in [
            "good girl",
            "good job",
            "you're cute",
            "cute"
        ]):

            self.speak(
                random.choice([
                    "Ehehe~ thank you!",
                    "You're making me blush~!",
                    "Aww... thank you!",
                    "Hehe~ I'm glad you think so!"
                ])
            )

            return True

        # ----------------------------------------------------
        # UNKNOWN COMMAND
        # ----------------------------------------------------

        self.speak(
            random.choice(self.unknown_responses)
        )

        return True

    # ========================================================
    # MAIN LOOP
    # ========================================================

    def run(self):

        self.speak(
            "Phoebe online~! How can I help?"
        )

        while True:

            try:

                text = input("\nYou: ").strip()

                if not text:
                    continue

                if not self.process_command(text):
                    break

            except KeyboardInterrupt:

                print("\n")

                self.speak(
                    "Oh! You're shutting me down~. Bye bye!"
                )

                break

            except Exception as e:

                print(f"❌ Error: {e}")

                self.speak(
                    "Something went wrong, but I'm still here!"
                )


# ============================================================
# START PHOEBE
# ============================================================

if __name__ == "__main__":

    phoebe = Phoebe()
    phoebe.run()
