/**
 * NexonAI — Electron Preload (Phase 3)
 * ======================================
 * Secure bridge between renderer and main process.
 * contextIsolation: true  |  nodeIntegration: false
 * All IPC goes through this validated surface.
 */

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const api = {
    // ── Window controls ──────────────────────────────────────────────────────
    minimize:          ()     => ipcRenderer.send("window:minimize"),
    maximize:          ()     => ipcRenderer.invoke("window:maximize"),
    isMaximized:       ()     => ipcRenderer.invoke("window:is_maximized"),
    close:             ()     => ipcRenderer.send("window:close"),
    toggleAlwaysOnTop: (flag) => ipcRenderer.invoke("window:toggle_always_on_top", flag),
    getAlwaysOnTop:    ()     => ipcRenderer.invoke("window:get_always_on_top"),

    // ── Settings ─────────────────────────────────────────────────────────────
    loadSettings: ()         => ipcRenderer.invoke("settings:load"),
    saveSettings: (settings) => ipcRenderer.invoke("settings:save", settings),

    // ── Assistant (one-shot workers) ─────────────────────────────────────────
    ask: (message, options) => {
        if (message && typeof message === "object") {
            return ipcRenderer.invoke("assistant:ask", message);
        }
        return ipcRenderer.invoke("assistant:ask", {
            message: String(message || ""),
            ...(options || {}),
        });
    },
    research: (query, options) => {
        if (query && typeof query === "object") {
            return ipcRenderer.invoke("assistant:research", query);
        }
        return ipcRenderer.invoke("assistant:research", {
            query: String(query || ""),
            ...(options || {}),
        });
    },
    cancel:      () => ipcRenderer.invoke("assistant:cancel"),
    getModels:   () => ipcRenderer.invoke("assistant:get_models"),
    clearMemory: () => ipcRenderer.invoke("assistant:clear_memory"),
    health:      () => ipcRenderer.invoke("assistant:health"),

    // ── Voice daemon controls ────────────────────────────────────────────────
    interruptAudio:  () => ipcRenderer.invoke("voice:interrupt"),
    stopListening:   () => ipcRenderer.invoke("voice:stop_listening"),
    startListening:  () => ipcRenderer.invoke("voice:start_listening"),
    restartDaemon:   () => ipcRenderer.invoke("voice:restart_daemon"),

    // ── Event subscriptions ───────────────────────────────────────────────────
    onProgress: (callback) => {
        const handler = (_e, data) => callback(data);
        ipcRenderer.on("research:progress", handler);
        return () => ipcRenderer.removeListener("research:progress", handler);
    },
    onVoiceEvent: (callback) => {
        const handler = (_e, data) => callback(data);
        ipcRenderer.on("voice:event", handler);
        return () => ipcRenderer.removeListener("voice:event", handler);
    },
    onMaximizedChange: (callback) => {
        const handler = (_e, isMax) => callback(isMax);
        ipcRenderer.on("window:maximized_change", handler);
        return () => ipcRenderer.removeListener("window:maximized_change", handler);
    },
};

// Expose under three names for backwards compatibility
contextBridge.exposeInMainWorld("phoebe", api);
contextBridge.exposeInMainWorld("jarvis", api);
contextBridge.exposeInMainWorld("bob",    api);
