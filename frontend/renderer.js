// ===============================
// PHOEBE VOICE ASSISTANT
// ===============================

const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;

let recognition = null;
let listening = false;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();

    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => {
        listening = true;
        console.log("Phoebe is listening...");
    };

    recognition.onend = () => {
        listening = false;

        // Keep listening automatically
        setTimeout(() => {
            if (recognition && !listening) {
                try {
                    recognition.start();
                } catch (e) {}
            }
        }, 500);
    };

    recognition.onerror = (event) => {
        console.log("Voice error:", event.error);
    };

    recognition.onresult = (event) => {
        const result =
            event.results[event.results.length - 1][0].transcript
                .trim()
                .toLowerCase();

        console.log("You said:", result);

        handlePhoebeCommand(result);
    };

    try {
        recognition.start();
    } catch (e) {
        console.log("Could not start speech recognition.");
    }
} else {
    console.log("Speech recognition is not supported.");
}


// ===============================
// COMMAND HANDLER
// ===============================

function handlePhoebeCommand(command) {

    // Wake word
    if (
        command.includes("phoebe") ||
        command.includes("phoebe")
    ) {
        console.log("Phoebe activated!");

        speakPhoebe(
            "Hehe~ I'm here! What can I do for you?"
        );

        return;
    }

    if (command.includes("hello") || command.includes("hi")) {
        speakPhoebe(
            "Hello! I'm Phoebe~ 💙"
        );

        return;
    }

    if (
        command.includes("what can you do") ||
        command.includes("what can you") ||
        command.includes("help me")
    ) {
        speakPhoebe(
            "I can talk with you, control your computer, help with files, coding, and much more!"
        );

        return;
    }

    if (
        command.includes("who are you") ||
        command.includes("your name")
    ) {
        speakPhoebe(
            "I'm Phoebe, your Nexon AI assistant!"
        );

        return;
    }

    if (command.includes("stop listening")) {
        speakPhoebe(
            "Okay~ I'll be quiet for now."
        );

        if (recognition) {
            recognition.stop();
        }

        return;
    }
}


// ===============================
// PHOEBE SPEECH
// ===============================

function speakPhoebe(text) {

    console.log("Phoebe:", text);

    // Stop previous speech
    window.speechSynthesis.cancel();

    const speech = new SpeechSynthesisUtterance(text);

    speech.rate = 1.0;
    speech.pitch = 1.25;
    speech.volume = 1.0;

    speech.onstart = () => {
        phoebe.classList.remove("walking");
        phoebe.classList.add("talking");
    };

    speech.onend = () => {
        phoebe.classList.remove("talking");

        scheduleNextAction();
    };

    window.speechSynthesis.speak(speech);
}