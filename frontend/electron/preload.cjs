const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("overlay", {
  setHit: (value) => ipcRenderer.send("overlay:hit", !!value),
  setLocked: (value) => ipcRenderer.send("overlay:locked", !!value),
  setOpacity: (value) => ipcRenderer.send("overlay:opacity", value),
  quit: () => ipcRenderer.send("overlay:quit"),
  // Commands from global hotkeys: toggle, seek:+5, seek:-5, seek:+1, seek:-1, ask, locked:true|false
  onCommand: (cb) => {
    const handler = (_e, cmd) => cb(cmd);
    ipcRenderer.on("overlay:cmd", handler);
    return () => ipcRenderer.removeListener("overlay:cmd", handler);
  },
});
