const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

let win;
let currentChildProcess = null;
let voiceDaemon = null;

const ROOT_DIR = path.dirname(__dirname);
const VENV_PYTHON = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");
const PYTHON_COMMAND = process.env.NEXON_PYTHON || (fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : "python");
const ASSISTANT_API = path.join(ROOT_DIR, "backend", "ai", "assistant.py");
const JARVIS_SCRIPT = path.join(ROOT_DIR, "jarvis.py");

// Persistent Settings Configuration
const SETTINGS_FILE = path.join(app.getPath("userData"), "phoebe_settings.json");
const DEFAULT_SETTINGS = {
    alwaysOnTop: true,
    activeModel: "qwen3-vl:4b",
    voiceOutput: true,
    speechRate: 1.0,
    speechVolume: 100
};

function loadSettingsSync() {
    try {
        if (fs.existsSync(SETTINGS_FILE)) {
            const raw = fs.readFileSync(SETTINGS_FILE, "utf-8");
            return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
        }
    } catch (e) {
        console.error("Failed to load settings:", e.message);
    }
    return { ...DEFAULT_SETTINGS };
}

function saveSettingsSync(settings) {
    try {
        fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2), "utf-8");
        return true;
    } catch (e) {
        console.error("Failed to save settings:", e.message);
        return false;
    }
}

function createWindow() {
    const initialSettings = loadSettingsSync();

    win = new BrowserWindow({
        title: "Phoebe - NexonAI",
        width: 360,
        height: 520,
        frame: false,
        transparent: true,
        alwaysOnTop: initialSettings.alwaysOnTop !== false,
        resizable: true,
        minWidth: 320,
        minHeight: 420,
        hasShadow: true,
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    win.loadFile(path.join(__dirname, "index.html"));

    win.on("maximize", () => {
        if (win && !win.isDestroyed()) {
            win.webContents.send("window:maximized_change", true);
        }
    });

    win.on("unmaximize", () => {
        if (win && !win.isDestroyed()) {
            win.webContents.send("window:maximized_change", false);
        }
    });

    win.on("closed", () => {
        win = null;
        stopVoiceDaemon();
    });
}

function startVoiceDaemon() {
    if (voiceDaemon) return;

    console.log("[SYSTEM] Starting hands-free voice loop daemon...");
    try {
        voiceDaemon = spawn(PYTHON_COMMAND, [JARVIS_SCRIPT, "--ipc", "--silent"], {
            cwd: ROOT_DIR,
            windowsHide: true,
            env: { ...process.env, PYTHONIOENCODING: "utf-8" }
        });

        let lineBuffer = "";

        voiceDaemon.stdout.on("data", (chunk) => {
            lineBuffer += chunk.toString("utf-8");
            const lines = lineBuffer.split("\n");
            lineBuffer = lines.pop(); // Keep trailing incomplete segment

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith("{")) continue;

                try {
                    const evt = JSON.parse(trimmed);
                    if (win && !win.isDestroyed()) {
                        win.webContents.send("voice:event", evt);
                    }
                } catch (e) {
                    console.log("[Voice IPC Parse Error]:", e.message, trimmed);
                }
            }
        });

        voiceDaemon.stderr.on("data", (chunk) => {
            console.error("[Voice Daemon STDERR]:", chunk.toString("utf-8"));
        });

        voiceDaemon.on("close", (code) => {
            console.log(`[Voice Daemon] Exited with code ${code}`);
            voiceDaemon = null;
        });

        voiceDaemon.on("error", (err) => {
            console.error("[Voice Daemon Error]:", err.message);
            voiceDaemon = null;
        });
    } catch (e) {
        console.error("Could not start voice daemon:", e);
    }
}

function stopVoiceDaemon() {
    if (voiceDaemon) {
        try {
            voiceDaemon.kill();
        } catch (e) {}
        voiceDaemon = null;
    }
}

app.whenReady().then(() => {
    createWindow();
    startVoiceDaemon();
});

ipcMain.on("window:minimize", () => {
    if (win) win.minimize();
});

ipcMain.handle("window:maximize", () => {
    if (!win) return { isMaximized: false };
    if (win.isMaximized()) {
        win.unmaximize();
    } else {
        win.maximize();
    }
    return { isMaximized: win.isMaximized() };
});

ipcMain.handle("window:is_maximized", () => {
    return { isMaximized: win ? win.isMaximized() : false };
});

ipcMain.handle("window:toggle_always_on_top", (_event, flag) => {
    if (!win) return { alwaysOnTop: false };
    const current = win.isAlwaysOnTop();
    const nextState = typeof flag === "boolean" ? flag : !current;
    win.setAlwaysOnTop(nextState);

    // Save state
    const currentSettings = loadSettingsSync();
    currentSettings.alwaysOnTop = nextState;
    saveSettingsSync(currentSettings);

    return { alwaysOnTop: win.isAlwaysOnTop() };
});

ipcMain.handle("window:get_always_on_top", () => {
    return { alwaysOnTop: win ? win.isAlwaysOnTop() : true };
});

ipcMain.on("window:close", () => {
    if (currentChildProcess) {
        try { currentChildProcess.kill(); } catch (e) {}
    }
    stopVoiceDaemon();
    app.quit();
});

// Settings Management
ipcMain.handle("settings:load", async () => {
    return { ok: true, settings: loadSettingsSync() };
});

ipcMain.handle("settings:save", async (_event, newSettings) => {
    if (!newSettings || typeof newSettings !== "object") {
        return { ok: false, error: "Invalid settings format" };
    }
    const current = loadSettingsSync();
    const merged = { ...current, ...newSettings };
    const saved = saveSettingsSync(merged);

    if (win && !win.isDestroyed() && typeof merged.alwaysOnTop === "boolean") {
        win.setAlwaysOnTop(merged.alwaysOnTop);
    }
    return { ok: saved, settings: merged };
});

ipcMain.on("bob:minimize", () => { if (win) win.minimize(); });
ipcMain.on("bob:close", () => {
    stopVoiceDaemon();
    app.quit();
});

// Ask Assistant (Conversation / Fast actions)
ipcMain.handle("assistant:ask", async (_event, payload) => {
    let text = "";
    let options = {};
    if (typeof payload === "string") {
        text = payload.trim();
    } else if (payload && typeof payload === "object") {
        text = String(payload.message || payload.query || "").trim();
        options = payload;
    }
    if (!text) return { ok: false, error: "Please ask a question, sir." };

    const settings = loadSettingsSync();
    const args = ["--ask", text];

    const modelToUse = options.model || settings.activeModel;
    if (modelToUse) {
        args.push("--model", String(modelToUse));
    }

    const shouldSpeak = typeof options.voiceOutput === "boolean" ? options.voiceOutput : settings.voiceOutput;
    if (shouldSpeak) {
        args.push("--speak");
    }

    return runAssistantProcess(args);
});

// Deep Research (with real-time progress events)
ipcMain.handle("assistant:research", async (_event, payload) => {
    let text = "";
    let options = {};
    if (typeof payload === "string") {
        text = payload.trim();
    } else if (payload && typeof payload === "object") {
        text = String(payload.query || payload.message || "").trim();
        options = payload;
    }
    if (!text) return { ok: false, error: "Please specify a research topic, sir." };

    const settings = loadSettingsSync();
    const args = ["--research", text];

    const modelToUse = options.model || settings.activeModel;
    if (modelToUse) {
        args.push("--model", String(modelToUse));
    }

    const shouldSpeak = typeof options.voiceOutput === "boolean" ? options.voiceOutput : settings.voiceOutput;
    if (shouldSpeak) {
        args.push("--speak");
    }

    return runAssistantProcess(args);
});

// Cancel active operation
ipcMain.handle("assistant:cancel", async () => {
    if (currentChildProcess) {
        try {
            currentChildProcess.kill();
            currentChildProcess = null;
            return { ok: true, message: "Operation cancelled." };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    }
    return { ok: true, message: "No active process." };
});

// Get installed Ollama models
ipcMain.handle("assistant:get_models", async () => {
    return runAssistantProcess(["--models"]);
});

// Clear conversation memory
ipcMain.handle("assistant:clear_memory", async () => {
    return runAssistantProcess(["--clear-memory"]);
});

// Health check
ipcMain.handle("assistant:health", async () => {
    return runAssistantProcess(["--health"]);
});

// Aliases for compatibility
ipcMain.handle("bob:ask", (_e, msg) => runAssistantProcess(["--ask", String(msg || "").trim()]));
ipcMain.handle("jarvis:ask", (_e, msg) => runAssistantProcess(["--ask", String(msg || "").trim()]));

app.on("window-all-closed", () => {
    stopVoiceDaemon();
    app.quit();
});

function runAssistantProcess(args) {
    return new Promise((resolve) => {
        if (currentChildProcess) {
            try { currentChildProcess.kill(); } catch (e) {}
        }

        const child = spawn(PYTHON_COMMAND, [ASSISTANT_API, ...args], {
            cwd: ROOT_DIR,
            windowsHide: true,
            env: { ...process.env, PYTHONIOENCODING: "utf-8" }
        });

        currentChildProcess = child;
        let stdoutData = "";
        let stderrData = "";

        child.stdout.on("data", (data) => {
            stdoutData += data.toString("utf-8");
        });

        child.stderr.on("data", (data) => {
            const lines = data.toString("utf-8").split("\n");
            for (const line of lines) {
                const trimmed = line.trim();
                stderrData += trimmed + "\n";
                const match = trimmed.match(/^\[PROGRESS\]\s+([^:]+):\s*(.*)$/);
                if (match && win && !win.isDestroyed()) {
                    win.webContents.send("research:progress", {
                        step: match[1].trim(),
                        detail: match[2].trim()
                    });
                }
            }
        });

        child.on("close", (code) => {
            currentChildProcess = null;
            const cleanStdout = stdoutData.trim();

            if (!cleanStdout) {
                resolve({
                    ok: false,
                    error: stderrData.trim() || `Process exited with code ${code}`
                });
                return;
            }

            try {
                const jsonMatch = cleanStdout.match(/(\{[\s\S]*\})$/);
                const jsonStr = jsonMatch ? jsonMatch[1] : cleanStdout;
                resolve(JSON.parse(jsonStr));
            } catch (err) {
                resolve({
                    ok: true,
                    spoken_answer: cleanStdout,
                    markdown_report: cleanStdout
                });
            }
        });

        child.on("error", (err) => {
            currentChildProcess = null;
            resolve({ ok: false, error: err.message });
        });
    });
}
