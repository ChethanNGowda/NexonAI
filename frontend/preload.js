const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("phoebe", {
    speak: () => ipcRenderer.send("speak-phoebe")
});