const bob = document.getElementById("bob");
const speech = document.getElementById("speech");
const statusLabel = document.getElementById("status");
const minimizeBtn = document.getElementById("minimizeBtn");
const maximizeBtn = document.getElementById("maximizeBtn");
const closeBtn = document.getElementById("closeBtn");
const pinBtn = document.getElementById("pinBtn");
const settingsBtn = document.getElementById("settingsBtn");
const askForm = document.getElementById("askForm");
const askInput = document.getElementById("askInput");
const modelBadge = document.getElementById("modelBadge");

// Settings Drawer Elements
const settingsDrawer = document.getElementById("settingsDrawer");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const modelSelect = document.getElementById("modelSelect");
const voiceSelect = document.getElementById("voiceSelect");
const alwaysOnTopToggle = document.getElementById("alwaysOnTopToggle");
const voiceOutputToggle = document.getElementById("voiceOutputToggle");
const speechRateSlider = document.getElementById("speechRateSlider");
const speechRateValue = document.getElementById("speechRateValue");
const speechVolumeSlider = document.getElementById("speechVolumeSlider");
const speechVolumeValue = document.getElementById("speechVolumeValue");
const clearMemoryBtn = document.getElementById("clearMemoryBtn");

// Voice Controls UI
const listenToggleBtn = document.getElementById("listenToggleBtn");
const interruptSpeechBtn = document.getElementById("interruptSpeechBtn");
const reconnectVoiceBtn = document.getElementById("reconnectVoiceBtn");

// Mode buttons
const modeChat = document.getElementById("modeChat");
const modeSearch = document.getElementById("modeSearch");
const modeResearch = document.getElementById("modeResearch");

// Research UI
const researchPanel = document.getElementById("researchPanel");
const researchStepLabel = document.getElementById("researchStepLabel");
const researchDetail = document.getElementById("researchDetail");
const progressFill = document.getElementById("progressFill");
const cancelResearchBtn = document.getElementById("cancelResearchBtn");

// Sources Drawer
const sourcesDrawer = document.getElementById("sourcesDrawer");
const sourcesList = document.getElementById("sourcesList");
const closeDrawerBtn = document.getElementById("closeDrawerBtn");
const copyAnswerBtn = document.getElementById("copyAnswerBtn");

let actionTimer = null;
let currentMode = "chat"; // "chat" | "search" | "research"
let lastMarkdownReport = "";
let isWindowMaximized = false;
let daemonState = "loading"; // "loading" | "listening" | "idle" | "thinking" | "speaking" | "error"
let voiceControlBusy = false;

// Active User Settings State
let userSettings = {
    alwaysOnTop: true,
    activeModel: "qwen3-vl:4b",
    activeVoice: "en-GB-RyanNeural",
    voiceOutput: true,
    speechRate: 1.0,
    speechVolume: 100
};

const idleReplies = [
    "I'm here, ready whenever you need me.",
    "All systems nominal. What would you like to investigate?",
    "Say Phoebe or Jarvis if you need assistance.",
    "Standing by, sir."
];

const api = window.phoebe || window.jarvis || window.bob;

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

function setMode(mode) {
    currentMode = mode;
    modeChat.classList.toggle("active", mode === "chat");
    modeSearch.classList.toggle("active", mode === "search");
    modeResearch.classList.toggle("active", mode === "research");

    if (mode === "research") {
        askInput.placeholder = "Enter deep research topic...";
    } else if (mode === "search") {
        askInput.placeholder = "Search the live web...";
    } else {
        askInput.placeholder = "Ask Phoebe or say 'Phoebe' aloud...";
    }
}

modeChat.addEventListener("click", () => setMode("chat"));
modeSearch.addEventListener("click", () => setMode("search"));
modeResearch.addEventListener("click", () => setMode("research"));

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
    }, 4000 + Math.random() * 5000);
}

// ============================================================
// WINDOW CONTROLS (Maximize, Minimize, Pin, Close)
// ============================================================

minimizeBtn.addEventListener("click", () => {
    api?.minimize();
});

closeBtn.addEventListener("click", () => {
    api?.close();
});

if (maximizeBtn) {
    maximizeBtn.addEventListener("click", async () => {
        try {
            const res = await api?.maximize();
            isWindowMaximized = !!res?.isMaximized;
            maximizeBtn.textContent = isWindowMaximized ? "❐" : "□";
        } catch (e) {
            console.error("Maximize error:", e);
        }
    });
}

if (api?.onMaximizedChange && maximizeBtn) {
    api.onMaximizedChange((isMax) => {
        isWindowMaximized = isMax;
        maximizeBtn.textContent = isMax ? "❐" : "□";
    });
}

function updatePinButton(isPinned) {
    if (!pinBtn) return;
    if (isPinned) {
        pinBtn.classList.add("pinned");
        pinBtn.classList.remove("unpinned");
        pinBtn.title = "Always on Top: ON (Click to unpin)";
    } else {
        pinBtn.classList.add("unpinned");
        pinBtn.classList.remove("pinned");
        pinBtn.title = "Always on Top: OFF (Click to pin)";
    }
}

if (pinBtn) {
    pinBtn.addEventListener("click", async () => {
        try {
            const nextState = !userSettings.alwaysOnTop;
            const res = await api?.toggleAlwaysOnTop(nextState);
            userSettings.alwaysOnTop = res?.alwaysOnTop ?? nextState;
            updatePinButton(userSettings.alwaysOnTop);
            if (alwaysOnTopToggle) {
                alwaysOnTopToggle.checked = userSettings.alwaysOnTop;
            }
            await api?.saveSettings({ alwaysOnTop: userSettings.alwaysOnTop });
        } catch (e) {
            console.error("Pin toggle error:", e);
        }
    });
}

// ============================================================
// SETTINGS DRAWER & PERSISTENCE
// ============================================================

if (settingsBtn) {
    settingsBtn.addEventListener("click", () => {
        sourcesDrawer.classList.add("hidden");
        settingsDrawer.classList.toggle("hidden");
    });
}

if (closeSettingsBtn) {
    closeSettingsBtn.addEventListener("click", () => {
        settingsDrawer.classList.add("hidden");
    });
}

async function persistSettings(newVals) {
    userSettings = { ...userSettings, ...newVals };
    try {
        await api?.saveSettings(userSettings);
    } catch (e) {
        console.error("Save settings error:", e);
    }
}

async function initializeSettings() {
    try {
        const res = await api?.loadSettings();
        if (res?.settings) {
            userSettings = { ...userSettings, ...res.settings };
        }
    } catch (e) {
        console.error("Load settings error:", e);
    }

    // Apply to UI
    if (alwaysOnTopToggle) alwaysOnTopToggle.checked = !!userSettings.alwaysOnTop;
    if (voiceOutputToggle) voiceOutputToggle.checked = !!userSettings.voiceOutput;
    if (speechRateSlider) speechRateSlider.value = userSettings.speechRate || 1.0;
    if (speechRateValue) speechRateValue.textContent = `${Number(userSettings.speechRate || 1.0).toFixed(2)}x`;
    if (speechVolumeSlider) speechVolumeSlider.value = userSettings.speechVolume || 100;
    if (speechVolumeValue) speechVolumeValue.textContent = `${userSettings.speechVolume || 100}%`;
    if (modelBadge) modelBadge.textContent = userSettings.activeModel || "qwen3-vl:4b";
    if (voiceSelect && userSettings.activeVoice) voiceSelect.value = userSettings.activeVoice;

    updatePinButton(userSettings.alwaysOnTop);
}

// Dynamic Model Discovery from Ollama
async function loadInstalledModels() {
    try {
        const res = await api?.getModels();
        const models = res?.installed_models || [];

        if (modelSelect) {
            modelSelect.innerHTML = "";
            if (models.length === 0) {
                const opt = document.createElement("option");
                opt.value = userSettings.activeModel || "qwen3-vl:4b";
                opt.textContent = `${userSettings.activeModel || "qwen3-vl:4b"} (Default)`;
                modelSelect.appendChild(opt);
            } else {
                models.forEach((m) => {
                    const opt = document.createElement("option");
                    opt.value = m;
                    opt.textContent = m.includes("vl") ? `${m} (Vision)` : m;
                    modelSelect.appendChild(opt);
                });
            }

            if (userSettings.activeModel) {
                modelSelect.value = userSettings.activeModel;
            } else if (models.length > 0) {
                userSettings.activeModel = models[0];
                modelSelect.value = models[0];
            }
            if (modelBadge) modelBadge.textContent = userSettings.activeModel;
        }
    } catch (e) {
        console.log("Could not load models:", e);
    }
}

// Settings Change Listeners
if (modelSelect) {
    modelSelect.addEventListener("change", () => {
        const chosen = modelSelect.value;
        userSettings.activeModel = chosen;
        if (modelBadge) modelBadge.textContent = chosen;
        persistSettings({ activeModel: chosen });
    });
}

if (voiceSelect) {
    voiceSelect.addEventListener("change", () => {
        const chosenVoice = voiceSelect.value;
        userSettings.activeVoice = chosenVoice;
        persistSettings({ activeVoice: chosenVoice });
    });
}

if (alwaysOnTopToggle) {
    alwaysOnTopToggle.addEventListener("change", async () => {
        const flag = alwaysOnTopToggle.checked;
        userSettings.alwaysOnTop = flag;
        updatePinButton(flag);
        await api?.toggleAlwaysOnTop(flag);
        persistSettings({ alwaysOnTop: flag });
    });
}

if (voiceOutputToggle) {
    voiceOutputToggle.addEventListener("change", () => {
        const flag = voiceOutputToggle.checked;
        userSettings.voiceOutput = flag;
        persistSettings({ voiceOutput: flag });
    });
}

if (speechRateSlider) {
    speechRateSlider.addEventListener("input", () => {
        const rate = parseFloat(speechRateSlider.value);
        if (speechRateValue) speechRateValue.textContent = `${rate.toFixed(2)}x`;
        persistSettings({ speechRate: rate });
    });
}

if (speechVolumeSlider) {
    speechVolumeSlider.addEventListener("input", () => {
        const vol = parseInt(speechVolumeSlider.value, 10);
        if (speechVolumeValue) speechVolumeValue.textContent = `${vol}%`;
        persistSettings({ speechVolume: vol });
    });
}

if (clearMemoryBtn) {
    clearMemoryBtn.addEventListener("click", async () => {
        try {
            await api?.clearMemory();
            setBubble("Conversational memory has been cleared.");
            setStatus("Ready");
            settingsDrawer.classList.add("hidden");
        } catch (e) {
            console.error("Clear memory error:", e);
        }
    });
}

// Bootstrap settings & models
initializeSettings().then(() => loadInstalledModels());

// ============================================================
// RESEARCH PROGRESS & VOICE SUBSCRIPTIONS
// ============================================================

if (api?.onProgress) {
    api.onProgress(({ step, detail }) => {
        researchPanel.classList.remove("hidden");
        researchStepLabel.textContent = (step || "RESEARCH").toUpperCase();
        researchDetail.textContent = detail || "Investigating...";

        const progressMap = {
            understanding: "15%",
            planning: "30%",
            searching: "50%",
            reading: "70%",
            verifying: "85%",
            synthesizing: "95%",
            completed: "100%"
        };
        progressFill.style.width = progressMap[step] || "50%";
    });
}

function updateVoiceControlsUI(state) {
    daemonState = state;
    if (!listenToggleBtn || !interruptSpeechBtn || !reconnectVoiceBtn) return;

    listenToggleBtn.classList.remove("listening-active");

    if (state === "error") {
        listenToggleBtn.textContent = "Voice Offline";
        listenToggleBtn.disabled = true;
        interruptSpeechBtn.disabled = true;
        reconnectVoiceBtn.classList.remove("hidden");
        reconnectVoiceBtn.disabled = false;
        return;
    }

    if (state === "mic_error") {
        listenToggleBtn.textContent = "Stop Listening";
        listenToggleBtn.disabled = false;
        interruptSpeechBtn.disabled = true;
        reconnectVoiceBtn.classList.remove("hidden");
        reconnectVoiceBtn.disabled = false;
        return;
    }

    reconnectVoiceBtn.classList.add("hidden");

    if (state === "loading") {
        listenToggleBtn.textContent = "Loading Voice...";
        listenToggleBtn.disabled = true;
        interruptSpeechBtn.disabled = true;
    } else if (state === "listening") {
        listenToggleBtn.textContent = "Stop Listening";
        listenToggleBtn.classList.add("listening-active");
        listenToggleBtn.disabled = false;
        interruptSpeechBtn.disabled = true;
    } else if (state === "idle") {
        listenToggleBtn.textContent = "Start Listening";
        listenToggleBtn.disabled = false;
        interruptSpeechBtn.disabled = true;
    } else if (state === "thinking") {
        listenToggleBtn.textContent = "Stop Listening";
        listenToggleBtn.disabled = false;
        interruptSpeechBtn.disabled = true;
    } else if (state === "speaking") {
        listenToggleBtn.textContent = "Stop Listening";
        listenToggleBtn.disabled = false;
        interruptSpeechBtn.disabled = false;
    }
}

if (listenToggleBtn) {
    listenToggleBtn.addEventListener("click", async () => {
        if (voiceControlBusy || daemonState === "loading" || daemonState === "error") return;
        voiceControlBusy = true;
        listenToggleBtn.disabled = true;
        try {
            if (daemonState === "idle") {
                await api?.startListening?.();
                updateVoiceControlsUI("listening");
                setStatus("Listening");
            } else {
                await api?.stopListening?.();
                updateVoiceControlsUI("idle");
                setStatus("Paused");
            }
        } catch (e) {
            console.error("Listen toggle failed:", e);
            updateVoiceControlsUI("error");
        } finally {
            voiceControlBusy = false;
        }
    });
}

if (interruptSpeechBtn) {
    interruptSpeechBtn.addEventListener("click", async () => {
        if (voiceControlBusy || daemonState !== "speaking") return;
        voiceControlBusy = true;
        interruptSpeechBtn.disabled = true;
        try {
            await api?.interruptAudio?.();
            setMood("sitting");
            updateVoiceControlsUI("listening");
            setStatus("Listening");
        } catch (e) {
            console.error("Interrupt speech failed:", e);
        } finally {
            voiceControlBusy = false;
        }
    });
}

if (reconnectVoiceBtn) {
    reconnectVoiceBtn.addEventListener("click", async () => {
        if (voiceControlBusy) return;
        voiceControlBusy = true;
        reconnectVoiceBtn.disabled = true;
        reconnectVoiceBtn.textContent = "Reconnecting...";
        try {
            await api?.restartDaemon?.();
            updateVoiceControlsUI("loading");
            setStatus("Reconnecting...");
        } catch (e) {
            console.error("Reconnect failed:", e);
            updateVoiceControlsUI("error");
        } finally {
            reconnectVoiceBtn.textContent = "Reconnect";
            voiceControlBusy = false;
        }
    });
}

if (api?.onVoiceEvent) {
    api.onVoiceEvent((evt) => {
        console.log("[Voice Event]:", evt);

        if (evt.event === "ready") {
            updateVoiceControlsUI("listening");
            setBubble(evt.message || "Phoebe is listening...");
            setStatus("Listening");
        } else if (evt.event === "heard") {
            setBubble(`Heard: "${evt.text}"`);
            setStatus("Heard");
            setMood("talking");
        } else if (evt.event === "error") {
            setStatus("Voice Error");
            if (evt.message) setBubble(evt.message);
        } else if (evt.event === "state") {
            const st = evt.status || "listening";
            updateVoiceControlsUI(st);
            if (st === "thinking") {
                setStatus("Thinking");
                setMood("sitting");
                setBubble("Thinking...");
            } else if (st === "listening") {
                setStatus("Listening");
            } else if (st === "idle") {
                setStatus("Paused");
                setMood("sitting");
            } else if (st === "speaking") {
                setStatus("Speaking");
                setMood("talking");
            } else if (st === "mic_error") {
                setStatus("Mic Unavailable");
                setMood("sitting");
                if (evt.detail) setBubble(evt.detail);
            } else if (st === "error") {
                setStatus("Voice Offline");
                setMood("sitting");
            }
        } else if (evt.event === "response") {
            setBubble(evt.answer);
            setMood("talking");
            lastMarkdownReport = evt.markdown || evt.answer;

            if (evt.sources && evt.sources.length > 0) {
                renderSources(evt.sources);
            }

            setTimeout(() => {
                setMood("sitting");
                scheduleNextAction();
            }, 4000);
        }
    });
}

cancelResearchBtn.addEventListener("click", async () => {
    try {
        await api?.cancel();
        researchPanel.classList.add("hidden");
        setStatus("Cancelled");
        setBubble("Research was cancelled.");
    } catch (e) {
        console.error("Cancel failed:", e);
    }
});

closeDrawerBtn.addEventListener("click", () => {
    sourcesDrawer.classList.add("hidden");
});

copyAnswerBtn.addEventListener("click", () => {
    if (lastMarkdownReport) {
        navigator.clipboard.writeText(lastMarkdownReport);
        copyAnswerBtn.textContent = "Copied!";
        setTimeout(() => { copyAnswerBtn.textContent = "Copy"; }, 2000);
    }
});

function renderSources(sources) {
    sourcesList.innerHTML = "";
    if (!sources || sources.length === 0) {
        sourcesDrawer.classList.add("hidden");
        return;
    }

    sources.forEach((s) => {
        const li = document.createElement("li");
        const idx = s.citation_id || "•";
        const title = s.title || s.url || "Source";
        const dateStr = s.date ? ` (${s.date})` : "";

        li.innerHTML = `<strong>[${idx}]</strong> <a href="${s.url}" target="_blank">${title}</a>${dateStr}`;
        sourcesList.appendChild(li);
    });

    sourcesDrawer.classList.remove("hidden");
}

async function askBackend(message) {
    const text = message.trim();
    if (!text) return;

    setBubble("Investigating...");
    setStatus("Thinking");
    setMood("sitting");
    askInput.disabled = true;

    try {
        let result;
        const options = {
            model: userSettings.activeModel,
            voiceOutput: userSettings.voiceOutput
        };

        if (currentMode === "research") {
            researchPanel.classList.remove("hidden");
            progressFill.style.width = "10%";
            result = await api?.research(text, options);
        } else {
            result = await api?.ask(text, options);
        }

        researchPanel.classList.add("hidden");

        if (!result?.ok) {
            const err = result?.error || "I could not complete that request, sir.";
            setBubble(err);
            setStatus("Ready");
            return;
        }

        const spoken = result.spoken_answer || result.answer || "Here are the findings, sir.";
        lastMarkdownReport = result.markdown_report || spoken;

        setBubble(spoken);
        setMood("talking");
        setStatus("Ready");

        if (result.sources && result.sources.length > 0) {
            renderSources(result.sources);
        }

        setTimeout(() => {
            setMood("sitting");
            scheduleNextAction();
        }, 3500);

    } catch (error) {
        researchPanel.classList.add("hidden");
        setBubble(`Bridge error: ${error.message}`);
        setStatus("Error");
    } finally {
        askInput.disabled = false;
        askInput.focus();
    }
}

bob.addEventListener("click", () => {
    const reply = idleReplies[Math.floor(Math.random() * idleReplies.length)];
    setBubble(reply);
});

askForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const msg = askInput.value.trim();
    askInput.value = "";
    askBackend(msg);
});

setMood("sitting");
setStatus("Ready");
scheduleNextAction();
