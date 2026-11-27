/**
 * NexonAI — Electron Main Process (Phase 3)
 * ==========================================
 * Manages the Python daemon lifecycle and IPC communication.
 *
 * Python IPC Architecture:
 *   - Persistent daemon: jarvis.py --ipc (voice loop, long-running)
 *   - One-shot workers:  backend/ai/assistant.py --ask/--research/etc.
 *
 * stdout → machine-readable JSON IPC
 * stderr → diagnostic logging only (not parsed by Electron)
 */

"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs   = require("fs");
const path = require("path");

// ─────────────────────────────────────────────────────────────────────────────
// Paths
// ─────────────────────────────────────────────────────────────────────────────
const ROOT_DIR     = path.dirname(__dirname);
const VENV_PYTHON  = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");
const PYTHON_CMD   = process.env.NEXON_PYTHON ||
                     (fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : "python");
const ASSISTANT_API = path.join(ROOT_DIR, "backend", "ai", "assistant.py");
const JARVIS_SCRIPT = path.join(ROOT_DIR, "jarvis.py");

// ─────────────────────────────────────────────────────────────────────────────
// Settings
// ─────────────────────────────────────────────────────────────────────────────
const SETTINGS_FILE     = path.join(app.getPath("userData"), "phoebe_settings.json");
const DEFAULT_SETTINGS  = {
    alwaysOnTop:  true,
    activeModel:  "qwen3-vl:4b",
    activeVoice:  "en-GB-RyanNeural",
    voiceOutput:  true,
    speechRate:   1.0,
    speechVolume: 100,
};

function loadSettingsSync() {
    try {
        if (fs.existsSync(SETTINGS_FILE)) {
            return { ...DEFAULT_SETTINGS, ...JSON.parse(fs.readFileSync(SETTINGS_FILE, "utf-8")) };
        }
    } catch (e) {
        console.error("[Settings] Load failed:", e.message);
    }
    return { ...DEFAULT_SETTINGS };
}

function saveSettingsSync(settings) {
    try {
        fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2), "utf-8");
        return true;
    } catch (e) {
        console.error("[Settings] Save failed:", e.message);
        return false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Window
// ─────────────────────────────────────────────────────────────────────────────
let win = null;

function createWindow() {
    const s = loadSettingsSync();
    win = new BrowserWindow({
        title:       "Phoebe - NexonAI",
        width:       360,
        height:      520,
        frame:       false,
        transparent: true,
        alwaysOnTop: s.alwaysOnTop !== false,
        resizable:   true,
        minWidth:    320,
        minHeight:   420,
        hasShadow:   true,
        webPreferences: {
            preload:          path.join(__dirname, "preload.js"),
            nodeIntegration:  false,
            contextIsolation: true,
        },
    });

    win.loadFile(path.join(__dirname, "index.html"));

    win.on("maximize",   () => { if (win && !win.isDestroyed()) win.webContents.send("window:maximized_change", true);  });
    win.on("unmaximize", () => { if (win && !win.isDestroyed()) win.webContents.send("window:maximized_change", false); });
    win.on("closed", () => {
        win = null;
        _shutdownDaemon();
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Python daemon state
// ─────────────────────────────────────────────────────────────────────────────
let _daemon           = null;      // The persistent jarvis.py --ipc process
let _daemonLineBuffer = "";        // Rolling stdout line buffer
let _daemonReady      = false;     // True once {"event":"ready"} received
let _daemonRestarts   = 0;         // Restart counter (rate-limit safety)
let _daemonRestartTimer = null;    // Pending restart timer handle
let _isQuitting       = false;     // True when app is shutting down
let _intentionalStop  = false;     // True during intentional daemon restart
const MAX_RESTARTS    = 5;         // Max automatic restarts before giving up
const RESTART_DELAY   = 3000;      // ms between restart attempts

// One-shot worker per chat/research request
let _currentWorker    = null;

// ─────────────────────────────────────────────────────────────────────────────
// Daemon management
// ─────────────────────────────────────────────────────────────────────────────

function _spawnEnv() {
    return {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
    };
}

function _startDaemon(settings) {
    // Guard: prevent duplicate processes
    if (_daemon) {
        console.log("[Daemon] Already running — not starting a second instance.");
        return;
    }
    if (_daemonRestarts >= MAX_RESTARTS) {
        console.error("[Daemon] Restart limit reached. Voice daemon disabled.");
        _notifyRenderer({ event: "error", message: "Voice daemon failed too many times. Restart the app." });
        return;
    }

    const args = [JARVIS_SCRIPT, "--ipc"];
    if (!settings.voiceOutput) args.push("--silent");

    console.log("[Daemon] Starting:", PYTHON_CMD, args.join(" "));

    try {
        _daemon = spawn(PYTHON_CMD, args, {
            cwd:         ROOT_DIR,
            windowsHide: true,
            env:         _spawnEnv(),
            stdio:       ["pipe", "pipe", "pipe"],  // stdin is writable for commands
        });
    } catch (e) {
        console.error("[Daemon] Spawn failed:", e.message);
        _daemon = null;
        return;
    }

    _daemonLineBuffer = "";
    _daemonReady      = false;
    _intentionalStop  = false;

    // ── stdout: JSON IPC events ──────────────────────────────────────────────
    _daemon.stdout.on("data", (chunk) => {
        _daemonLineBuffer += chunk.toString("utf-8");
        const lines = _daemonLineBuffer.split("\n");
        _daemonLineBuffer = lines.pop();     // keep incomplete trailing fragment

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("{")) continue;
            try {
                const evt = JSON.parse(trimmed);
                if (evt.event === "ready") _daemonReady = true;
                _notifyRenderer(evt);
            } catch (e) {
                console.warn("[Daemon IPC Parse Error]:", trimmed.slice(0, 120));
            }
        }
    });

    // ── stderr: diagnostic logs (never parsed) ───────────────────────────────
    _daemon.stderr.on("data", (chunk) => {
        const lines = chunk.toString("utf-8").split("\n").filter(Boolean);
        for (const l of lines) console.log("[Daemon]", l);
    });

    // ── process exit ─────────────────────────────────────────────────────────
    _daemon.on("close", (code, signal) => {
        console.log(`[Daemon] Exited (code=${code} signal=${signal})`);
        _daemon       = null;
        _daemonReady  = false;

        // Notify renderer the daemon is gone
        _notifyRenderer({ event: "state", status: "error", detail: "Voice daemon stopped." });

        // Auto-restart unless it was a clean exit (code 0), intentional restart, or app is quitting
        if (!_isQuitting && !_intentionalStop && code !== 0) {
            _daemonRestarts++;
            _scheduleRestart();
        }
    });

    _daemon.on("error", (err) => {
        console.error("[Daemon] Process error:", err.message);
        _daemon = null;
        _daemonReady = false;
        if (!_isQuitting) {
            _daemonRestarts++;
            _scheduleRestart();
        }
    });

    // Push current settings to the daemon once it's ready
    // (small delay to let it boot before accepting stdin commands)
    setTimeout(() => _syncSettingsToDaemon(settings), 1500);
}

function _scheduleRestart() {
    if (_daemonRestartTimer) return;
    if (_daemonRestarts >= MAX_RESTARTS) {
        console.error("[Daemon] Will not restart — restart limit reached.");
        return;
    }
    console.log(`[Daemon] Scheduling restart #${_daemonRestarts} in ${RESTART_DELAY}ms...`);
    _daemonRestartTimer = setTimeout(() => {
        _daemonRestartTimer = null;
        if (!_daemon) _startDaemon(loadSettingsSync());
    }, RESTART_DELAY);
}

function _killTree(child) {
    if (!child || !child.pid) return;
    try {
        if (process.platform === "win32") {
            spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
                windowsHide: true,
                stdio: "ignore",
            });
        } else {
            child.kill("SIGKILL");
        }
    } catch (_) {
        try { child.kill(); } catch (_) {}
    }
}

function _shutdownDaemon() {
    _isQuitting = true;
    if (_daemonRestartTimer) {
        clearTimeout(_daemonRestartTimer);
        _daemonRestartTimer = null;
    }
    if (_daemon) {
        const proc = _daemon;
        console.log("[Daemon] Sending shutdown command...");
        try { _daemonCommand({ cmd: "shutdown" }); } catch (_) {}
        // Give it 1.5 s to exit cleanly then force-kill tree
        setTimeout(() => {
            if (_daemon === proc) {
                _killTree(proc);
                _daemon = null;
            }
        }, 1500);
    }
}

/** Send a JSON command to the daemon via its stdin pipe. */
function _daemonCommand(obj) {
    if (!_daemon || !_daemon.stdin || _daemon.stdin.destroyed) return;
    try {
        _daemon.stdin.write(JSON.stringify(obj) + "\n");
    } catch (e) {
        console.warn("[Daemon] Failed to write stdin command:", e.message);
    }
}

/** Push current settings to a running daemon. */
function _syncSettingsToDaemon(settings) {
    if (!_daemon) return;
    _daemonCommand({ cmd: "set_rate",     rate:    settings.speechRate   ?? 1.0 });
    _daemonCommand({ cmd: "set_volume",   volume:  settings.speechVolume ?? 100 });
    _daemonCommand({ cmd: "set_voice",    enabled: settings.voiceOutput  !== false });
    if (settings.activeVoice) {
        _daemonCommand({ cmd: "set_voice_id", voice: settings.activeVoice });
    }
    if (settings.activeModel) {
        _daemonCommand({ cmd: "set_model", model: settings.activeModel });
    }
}

/** Forward a daemon event to the renderer process. */
function _notifyRenderer(evt) {
    if (win && !win.isDestroyed()) {
        win.webContents.send("voice:event", evt);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// App lifecycle
// ─────────────────────────────────────────────────────────────────────────────

app.whenReady().then(() => {
    createWindow();
    _startDaemon(loadSettingsSync());
});

app.on("window-all-closed", () => {
    _shutdownDaemon();
    if (_currentWorker) { _killTree(_currentWorker); _currentWorker = null; }
    app.quit();
});

app.on("before-quit", () => {
    _shutdownDaemon();
    if (_currentWorker) { _killTree(_currentWorker); _currentWorker = null; }
});

// ─────────────────────────────────────────────────────────────────────────────
// Window IPC handlers
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.on("window:minimize", () => { if (win) win.minimize(); });

ipcMain.handle("window:maximize", () => {
    if (!win) return { isMaximized: false };
    if (win.isMaximized()) win.unmaximize(); else win.maximize();
    return { isMaximized: win.isMaximized() };
});

ipcMain.handle("window:is_maximized",   () => ({ isMaximized: win ? win.isMaximized() : false }));
ipcMain.handle("window:get_always_on_top", () => ({ alwaysOnTop: win ? win.isAlwaysOnTop() : true }));

ipcMain.handle("window:toggle_always_on_top", (_e, flag) => {
    if (!win) return { alwaysOnTop: false };
    const next = typeof flag === "boolean" ? flag : !win.isAlwaysOnTop();
    win.setAlwaysOnTop(next);
    const s = loadSettingsSync();
    s.alwaysOnTop = next;
    saveSettingsSync(s);
    return { alwaysOnTop: win.isAlwaysOnTop() };
});

ipcMain.on("window:close", () => {
    _shutdownDaemon();
    if (_currentWorker) { try { _currentWorker.kill(); } catch (_) {} }
    app.quit();
});

// Legacy aliases
ipcMain.on("bob:minimize", () => { if (win) win.minimize(); });
ipcMain.on("bob:close",    () => { _shutdownDaemon(); app.quit(); });

// ─────────────────────────────────────────────────────────────────────────────
// Settings IPC
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle("settings:load", async () => ({ ok: true, settings: loadSettingsSync() }));

ipcMain.handle("settings:save", async (_e, newSettings) => {
    if (!newSettings || typeof newSettings !== "object") {
        return { ok: false, error: "Invalid settings object." };
    }
    // Validate types to prevent injection via IPC
    const clean = {};
    if (typeof newSettings.alwaysOnTop  === "boolean") clean.alwaysOnTop  = newSettings.alwaysOnTop;
    if (typeof newSettings.voiceOutput  === "boolean") clean.voiceOutput  = newSettings.voiceOutput;
    if (typeof newSettings.activeModel  === "string")  clean.activeModel  = newSettings.activeModel.slice(0, 64);
    if (typeof newSettings.activeVoice  === "string")  clean.activeVoice  = newSettings.activeVoice.slice(0, 64);
    if (typeof newSettings.speechRate   === "number")  clean.speechRate   = Math.max(0.5, Math.min(2.0, newSettings.speechRate));
    if (typeof newSettings.speechVolume === "number")  clean.speechVolume = Math.max(0, Math.min(100, Math.round(newSettings.speechVolume)));

    const merged = { ...loadSettingsSync(), ...clean };
    const saved  = saveSettingsSync(merged);

    if (win && !win.isDestroyed() && typeof merged.alwaysOnTop === "boolean") {
        win.setAlwaysOnTop(merged.alwaysOnTop);
    }

    // Push updated settings to live daemon
    _syncSettingsToDaemon(merged);

    return { ok: saved, settings: merged };
});

// ─────────────────────────────────────────────────────────────────────────────
// Daemon control IPC (voice controls forwarded to running daemon)
// ─────────────────────────────────────────────────────────────────────────────

ipcMain.handle("voice:interrupt", async () => {
    _daemonCommand({ cmd: "interrupt_audio" });
    return { ok: true };
});

ipcMain.handle("voice:stop_listening", async () => {
    _daemonCommand({ cmd: "stop_listening" });
    return { ok: true };
});

ipcMain.handle("voice:start_listening", async () => {
    _daemonCommand({ cmd: "start_listening" });
    return { ok: true };
});

ipcMain.handle("voice:restart_daemon", async () => {
    _intentionalStop = true;
    if (_daemonRestartTimer) {
        clearTimeout(_daemonRestartTimer);
        _daemonRestartTimer = null;
    }
    if (_daemon) {
        const proc = _daemon;
        try { _daemonCommand({ cmd: "shutdown" }); } catch (_) {}
        setTimeout(() => { if (_daemon === proc) { _killTree(proc); _daemon = null; } }, 1000);
    }
    _isQuitting = false;
    _daemonRestarts = 0;   // reset counter on explicit user request
    setTimeout(() => _startDaemon(loadSettingsSync()), 1200);
    return { ok: true };
});

// ─────────────────────────────────────────────────────────────────────────────
// One-shot assistant IPC handlers
// ─────────────────────────────────────────────────────────────────────────────

function _runWorker(args, timeoutMs = 120000) {
    return new Promise((resolve) => {
        // Cancel any in-flight worker
        if (_currentWorker) {
            _killTree(_currentWorker);
            _currentWorker = null;
        }

        const child = spawn(PYTHON_CMD, [ASSISTANT_API, ...args], {
            cwd:         ROOT_DIR,
            windowsHide: true,
            env:         _spawnEnv(),
            stdio:       ["ignore", "pipe", "pipe"],
        });

        _currentWorker = child;
        let stdout = "";
        let stderr = "";
        let settled = false;

        const timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            _killTree(child);
            if (_currentWorker === child) _currentWorker = null;
            resolve({ ok: false, error: `Assistant worker timed out after ${Math.round(timeoutMs / 1000)}s.` });
        }, timeoutMs);

        child.stdout.on("data", d => { stdout += d.toString("utf-8"); });

        child.stderr.on("data", d => {
            const lines = d.toString("utf-8").split("\n");
            for (const l of lines) {
                const t = l.trim();
                stderr += t + "\n";
                // Forward progress events
                const m = t.match(/^\[PROGRESS\]\s+([^:]+):\s*(.*)$/);
                if (m && win && !win.isDestroyed()) {
                    win.webContents.send("research:progress", { step: m[1].trim(), detail: m[2].trim() });
                }
            }
        });

        child.on("close", (code) => {
            clearTimeout(timer);
            if (settled) return;
            settled = true;
            if (_currentWorker === child) _currentWorker = null;
            const clean = stdout.trim();
            if (!clean) {
                resolve({ ok: false, error: stderr.trim() || `Process exited with code ${code}` });
                return;
            }
            try {
                // The JSON object may be preceded by debug prints; grab the last {...}
                const m = clean.match(/(\{[\s\S]*\})$/);
                resolve(JSON.parse(m ? m[1] : clean));
            } catch (_) {
                resolve({ ok: true, spoken_answer: clean, markdown_report: clean });
            }
        });

        child.on("error", (err) => {
            clearTimeout(timer);
            if (settled) return;
            settled = true;
            if (_currentWorker === child) _currentWorker = null;
            resolve({ ok: false, error: err.message });
        });
    });
}

ipcMain.handle("assistant:ask", async (_e, payload) => {
    let text = "", options = {};
    if (typeof payload === "string") {
        text = payload.trim();
    } else if (payload && typeof payload === "object") {
        text = String(payload.message || payload.query || "").trim();
        options = payload;
    }
    if (!text) return { ok: false, error: "Please ask a question, sir." };

    const s = loadSettingsSync();
    const args = ["--ask", text];
    args.push("--model", String(options.model || s.activeModel || "qwen3-vl:4b").slice(0, 64));
    const shouldSpeak = typeof options.voiceOutput === "boolean" ? options.voiceOutput : s.voiceOutput;
    if (shouldSpeak) {
        args.push("--speak");
        const voiceToUse = options.voice || s.activeVoice;
        if (voiceToUse) args.push("--voice", String(voiceToUse).slice(0, 64));
        if (typeof s.speechRate === "number") args.push("--rate", String(s.speechRate));
        if (typeof s.speechVolume === "number") args.push("--volume", String(s.speechVolume));
    }
    return _runWorker(args, 120000);
});

ipcMain.handle("assistant:research", async (_e, payload) => {
    let text = "", options = {};
    if (typeof payload === "string") {
        text = payload.trim();
    } else if (payload && typeof payload === "object") {
        text = String(payload.query || payload.message || "").trim();
        options = payload;
    }
    if (!text) return { ok: false, error: "Please specify a research topic, sir." };

    const s = loadSettingsSync();
    const args = ["--research", text];
    args.push("--model", String(options.model || s.activeModel || "qwen3-vl:4b").slice(0, 64));
    const shouldSpeak = typeof options.voiceOutput === "boolean" ? options.voiceOutput : s.voiceOutput;
    if (shouldSpeak) {
        args.push("--speak");
        const voiceToUse = options.voice || s.activeVoice;
        if (voiceToUse) args.push("--voice", String(voiceToUse).slice(0, 64));
        if (typeof s.speechRate === "number") args.push("--rate", String(s.speechRate));
        if (typeof s.speechVolume === "number") args.push("--volume", String(s.speechVolume));
    }
    return _runWorker(args, 180000);
});

ipcMain.handle("assistant:cancel", async () => {
    if (_currentWorker) {
        try { _currentWorker.kill(); _currentWorker = null; return { ok: true, message: "Cancelled." }; }
        catch (e) { return { ok: false, error: e.message }; }
    }
    // Also interrupt daemon audio
    _daemonCommand({ cmd: "interrupt_audio" });
    return { ok: true, message: "No active worker." };
});

ipcMain.handle("assistant:get_models", async ()    => _runWorker(["--models"]));
ipcMain.handle("assistant:clear_memory", async () => _runWorker(["--clear-memory"]));
ipcMain.handle("assistant:health",  async ()       => _runWorker(["--health"]));

// Legacy aliases
ipcMain.handle("bob:ask",    (_e, msg) => _runWorker(["--ask", String(msg || "").trim()]));
ipcMain.handle("jarvis:ask", (_e, msg) => _runWorker(["--ask", String(msg || "").trim()]));
