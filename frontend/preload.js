const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("bob", {
    minimize: () => ipcRenderer.send("bob:minimize"),
    close: () => ipcRenderer.send("bob:close"),
    ask: (message) => ipcRenderer.invoke("bob:ask", message)
});
