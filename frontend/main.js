const { app, BrowserWindow, ipcMain } = require("electron");
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");

let win;
const ROOT_DIR = path.dirname(__dirname);
const VENV_PYTHON = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");
const PYTHON_COMMAND = process.env.NEXON_PYTHON || (fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : "python");
const BOB_API = path.join(__dirname, "phoebe_api.py");

function createWindow() {
    win = new BrowserWindow({
        width: 320,
        height: 360,
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        resizable: false,
        hasShadow: false,
        skipTaskbar: true,

        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    win.loadFile(path.join(__dirname, "index.html"));
}

app.whenReady().then(createWindow);

ipcMain.on("bob:minimize", () => {
    if (win) {
        win.minimize();
    }
});

ipcMain.on("bob:close", () => {
    app.quit();
});

ipcMain.handle("bob:ask", async (_event, message) => {
    const text = String(message || "").trim();

    if (!text) {
        return {
            ok: false,
            error: "Ask me something first."
        };
    }

    return runBobApi(["--ask", text]);
});

app.on("window-all-closed", () => {
    app.quit();
});

function runBobApi(args) {
    return new Promise((resolve) => {
        execFile(
            PYTHON_COMMAND,
            [BOB_API, ...args],
            {
                cwd: ROOT_DIR,
                windowsHide: true,
                timeout: 120000,
                maxBuffer: 1024 * 1024
            },
            (error, stdout, stderr) => {
                if (error) {
                    resolve({
                        ok: false,
                        error: stderr.trim() || error.message
                    });
                    return;
                }

                try {
                    resolve(JSON.parse(stdout.trim()));
                } catch (parseError) {
                    resolve({
                        ok: false,
                        error: stdout.trim() || parseError.message
                    });
                }
            }
        );
    });
}
