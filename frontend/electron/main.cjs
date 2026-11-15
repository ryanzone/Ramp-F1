// RAMP desktop HUD: a transparent, frameless, always-on-top window to run over a race broadcast.
const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require("electron");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

// Port 5173 is already in the backend's CORS allow-list. Dev mode uses the vite server instead.
const PORT = 5173;
const DEV = !!process.env.OVERLAY_DEV;
const DIST = path.join(__dirname, "..", "dist");
const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
  ".png": "image/png", ".json": "application/json", ".woff2": "font/woff2",
};

let win = null;
let server = null;
let locked = false; // everything click-through
let hit = false; // pointer is over a HUD panel

function serveDist() {
  return new Promise((resolve, reject) => {
    server = http.createServer((req, res) => {
      const rel = decodeURIComponent(req.url.split("?")[0]);
      const file = path.normalize(path.join(DIST, rel === "/" ? "overlay.html" : rel));
      if (!file.startsWith(DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404).end();
        return;
      }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    server.on("error", reject);
    server.listen(PORT, "127.0.0.1", resolve);
  });
}

// Transparent areas pass clicks to the video; panels capture them. Locked passes everything.
function applyMouse() {
  if (!win) return;
  const ignore = locked || !hit;
  win.setIgnoreMouseEvents(ignore, { forward: true });
}

function send(cmd) {
  win?.webContents.send("overlay:cmd", cmd);
}

function setLocked(value) {
  locked = value;
  applyMouse();
  send(`locked:${locked}`);
}

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  const width = workArea.width;
  const height = workArea.height;
  win = new BrowserWindow({
    width,
    height,
    x: workArea.x,
    y: workArea.y,
    frame: false,
    transparent: true,
    resizable: false,
    hasShadow: false,
    alwaysOnTop: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setAlwaysOnTop(true, "screen-saver"); // above borderless full-screen video
  win.loadURL(`http://localhost:${PORT}/overlay.html`);
  win.webContents.on("did-finish-load", applyMouse);
  win.on("closed", () => (win = null));
}

app.whenReady().then(async () => {
  if (!DEV) {
    try {
      await serveDist();
    } catch (err) {
      console.error(`Could not listen on port ${PORT} (is the vite dev server running?): ${err.message}`);
      app.quit();
      return;
    }
  }
  createWindow();
  const keys = {
    "Control+Shift+O": () => (win?.isVisible() ? win.hide() : win?.showInactive()),
    "Control+Shift+C": () => setLocked(!locked),
    "Control+Shift+Space": () => send("toggle"),
    "Control+Shift+Left": () => send("seek:-5"),
    "Control+Shift+Right": () => send("seek:+5"),
    "Control+Alt+Left": () => send("seek:-1"),
    "Control+Alt+Right": () => send("seek:+1"),
    "Control+Shift+Q": () => {
      // Let the pointer-less keyboard path work: take focus and open the ask box.
      locked = false;
      hit = true;
      applyMouse();
      win?.show();
      win?.focus();
      send("locked:false");
      send("ask");
    },
  };
  for (const [accelerator, fn] of Object.entries(keys)) globalShortcut.register(accelerator, fn);
});

ipcMain.on("overlay:hit", (_e, value) => {
  hit = value;
  applyMouse();
});
ipcMain.on("overlay:locked", (_e, value) => setLocked(!!value));
ipcMain.on("overlay:opacity", (_e, value) => win?.setOpacity(Math.min(1, Math.max(0.3, Number(value) || 1))));
ipcMain.on("overlay:quit", () => app.quit());

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  server?.close();
});
app.on("window-all-closed", () => app.quit());
