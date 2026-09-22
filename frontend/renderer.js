const bob = document.getElementById("bob");
const speech = document.getElementById("speech");
const statusLabel = document.getElementById("status");
const minimizeBtn = document.getElementById("minimizeBtn");
const closeBtn = document.getElementById("closeBtn");
const askForm = document.getElementById("askForm");
const askInput = document.getElementById("askInput");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let listening = false;
let shouldListen = true;
let actionTimer = null;

const idleReplies = [
    "I'm here.",
    "Ready when you are.",
    "Say Bob if you need me.",
    "I'm keeping an eye on things."
];

function setStatus(text) {
    statusLabel.textContent = text;
}

function setBubble(text) {
    speech.textContent = text;
}

function setMood(mood) {
    bob.classList.remove("walking", "sitting", "jumping", "talking");
    bob.classList.add(mood);
}

function scheduleNextAction() {
    clearTimeout(actionTimer);

    actionTimer = setTimeout(() => {
        const actions = ["sitting", "walking", "jumping"];
        const mood = actions[Math.floor(Math.random() * actions.length)];

        setMood(mood);

        if (mood === "jumping") {
            setTimeout(() => setMood("sitting"), 950);
        }

        scheduleNextAction();
    }, 3000 + Math.random() * 4000);
}

function startRecognition() {
    if (!recognition || listening || !shouldListen) {
        return;
    }

    try {
        recognition.start();
    } catch (error) {
        console.log("Could not start speech recognition:", error.message);
    }
}

function stopRecognition() {
    shouldListen = false;

    if (recognition && listening) {
        recognition.stop();
    }

    listening = false;
    setStatus("Paused");
}

function setupRecognition() {
    if (!SpeechRecognition) {
        setStatus("Click Bob to talk");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => {
        listening = true;
        setStatus("Listening");
    };

    recognition.onend = () => {
        listening = false;

        if (shouldListen) {
            setStatus("Restarting");
            setTimeout(startRecognition, 700);
        }
    };

    recognition.onerror = (event) => {
        console.log("Voice error:", event.error);
        setStatus(event.error === "not-allowed" ? "Mic blocked" : "Voice retrying");
    };

    recognition.onresult = (event) => {
        const result = event.results[event.results.length - 1][0].transcript
            .trim()
            .toLowerCase();

        console.log("You said:", result);
        handleBobCommand(result);
    };

    startRecognition();
}

function handleBobCommand(command) {
    if (!command) {
        return;
    }

    if (command.includes("stop listening")) {
        speakBob("Okay, I'll stay quiet for now.");
        stopRecognition();
        return;
    }

    if (command.includes("start listening") || command.includes("wake up")) {
        shouldListen = true;
        startRecognition();
        speakBob("I'm listening again.");
        return;
    }

    if (command.includes("hello") || command.includes("hi")) {
        speakBob("Hello! I'm Bob.");
        return;
    }

    if (
        command.includes("what can you do") ||
        command.includes("what can you") ||
        command.includes("help me")
    ) {
        speakBob("I can listen, answer simple commands, and sit on your desktop while the Python assistant handles deeper voice tasks.");
        return;
    }

    if (command.includes("who are you") || command.includes("your name")) {
        speakBob("I'm Bob, your Nexon AI desktop companion.");
        return;
    }

    if (command.includes("bob")) {
        const prompt = command.replace(/\bbob\b/g, "").trim();

        if (!prompt) {
            speakBob("I'm here. What are we doing?");
            return;
        }

        askBackend(prompt);
    }
}

async function askBackend(message) {
    const text = message.trim();

    if (!text) {
        return;
    }

    setBubble("Thinking...");
    setStatus("Thinking");
    setMood("sitting");
    askInput.disabled = true;

    try {
        const result = await window.bob?.ask(text);

        if (!result?.ok) {
            speakBob(result?.error || "I could not answer that yet.");
            return;
        }

        speakBob(result.answer);
    } catch (error) {
        speakBob(`I hit a bridge error: ${error.message}`);
    } finally {
        askInput.disabled = false;
        askInput.focus();
    }
}

function speakBob(text) {
    console.log("Bob:", text);
    setBubble(text);

    if (!("speechSynthesis" in window)) {
        setMood("sitting");
        return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.2;
    utterance.volume = 1.0;

    utterance.onstart = () => {
        setMood("talking");
        setStatus("Speaking");
    };

    utterance.onend = () => {
        setMood("sitting");
        setStatus(shouldListen ? "Listening" : "Paused");
        scheduleNextAction();
    };

    window.speechSynthesis.speak(utterance);
}

bob.addEventListener("click", () => {
    const reply = idleReplies[Math.floor(Math.random() * idleReplies.length)];
    speakBob(reply);
});

minimizeBtn.addEventListener("click", () => {
    window.bob?.minimize();
});

closeBtn.addEventListener("click", () => {
    window.bob?.close();
});

askForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const message = askInput.value.trim();
    askInput.value = "";
    askBackend(message);
});

setMood("sitting");
setupRecognition();
scheduleNextAction();
