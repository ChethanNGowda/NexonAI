const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

let win;

function createWindow() {
    win = new BrowserWindow({
        width: 260,
        height: 300,

        frame: false,
        transparent: true,
        backgroundColor: "#00000000",

        alwaysOnTop: true,
        resizable: false,
        movable: true,
        minimizable: false,
        maximizable: false,
        closable: true,

        hasShadow: false,
        skipTaskbar: true,

        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            devTools: true
        }
    });

    win.loadFile(path.join(__dirname, "index.html"));

    // Keep Phoebe above normal windows
    win.setAlwaysOnTop(true, "floating");

    // Prevent accidental white background
    win.setBackgroundColor("#00000000");

    win.on("closed", () => {
        win = null;
    });
}

app.whenReady().then(() => {
    createWindow();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});
