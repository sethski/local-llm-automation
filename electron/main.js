const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, dialog, Notification } = require('electron');
const path = require('path');
const { spawn, execFile } = require('child_process');
const fs = require('fs');
const http = require('http');

// ─── GLOBALS ────────────────────────────────────────────────
let mainWindow = null;
let tray = null;
let pythonServer = null;
let serverReady = false;
const SERVER_PORT = 5000;
const isDev = process.argv.includes('--dev');

// ─── SINGLE INSTANCE LOCK ───────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ─── PYTHON SERVER ──────────────────────────────────────────
function getServerScript() {
  // In production (packaged), resources are in process.resourcesPath
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'sethOS_server.py');
  }
  return path.join(__dirname, '..', 'sethOS_server.py');
}

function findPython() {
  // Try all common Python paths on Windows and Unix
  const { execSync } = require('child_process');
  const candidates = ['python', 'python3', 'py'];
  for (const cmd of candidates) {
    try {
      execSync(`${cmd} --version`, { stdio: 'ignore', timeout: 3000 });
      console.log('[Server] Found Python as:', cmd);
      return cmd;
    } catch {}
  }
  // Last resort: check common Windows install paths
  const winPaths = [
    'C:\\Python312\\python.exe',
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
    'C:\\Python39\\python.exe',
    process.env.LOCALAPPDATA + '\\Programs\\Python\\Python312\\python.exe',
    process.env.LOCALAPPDATA + '\\Programs\\Python\\Python311\\python.exe',
    process.env.LOCALAPPDATA + '\\Programs\\Python\\Python310\\python.exe',
    process.env.LOCALAPPDATA + '\\Programs\\Python\\Python39\\python.exe',
  ];
  for (const p of winPaths) {
    if (p && fs.existsSync(p)) {
      console.log('[Server] Found Python at:', p);
      return p;
    }
  }
  console.error('[Server] Python not found!');
  return 'python';
}

function startPythonServer() {
  const scriptPath = getServerScript();

  if (!fs.existsSync(scriptPath)) {
    console.warn('[Server] sethOS_server.py not found at:', scriptPath);
    return;
  }

  console.log('[Server] Starting Python server...');
  const python = findPython();

  pythonServer = spawn(python, [scriptPath], {
    cwd: path.dirname(scriptPath),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    env: { ...process.env },
  });

  pythonServer.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    console.log('[Server]', msg);
    if (msg.includes('Starting on http') || msg.includes('Running on http')) {
      serverReady = true;
      mainWindow?.webContents.send('server-ready');
    }
  });

  pythonServer.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    // Flask prints to stderr normally, not an error
    if (msg.includes('Running on') || msg.includes('Debugger')) {
      serverReady = true;
      mainWindow?.webContents.send('server-ready');
    }
    console.log('[Server stderr]', msg);
  });

  pythonServer.on('error', (err) => {
    console.error('[Server] Failed to start:', err.message);
    mainWindow?.webContents.send('server-error', err.message);
  });

  pythonServer.on('close', (code) => {
    console.log('[Server] Exited with code', code);
    serverReady = false;
  });
}

function stopPythonServer() {
  if (pythonServer) {
    console.log('[Server] Stopping...');
    pythonServer.kill();
    pythonServer = null;
  }
}

function waitForServer(maxWait = 10000) {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = () => {
      http.get(`http://localhost:${SERVER_PORT}/api/health`, (res) => {
        if (res.statusCode === 200) resolve(true);
        else retry();
      }).on('error', () => {
        if (Date.now() - start < maxWait) setTimeout(check, 500);
        else resolve(false);
      });
    };
    const retry = () => setTimeout(check, 500);
    check();
  });
}

// ─── WINDOW ─────────────────────────────────────────────────
async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'SethOS',
    backgroundColor: '#0a0a0f',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    frame: process.platform !== 'win32',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: getIconPath(),
    show: false, // show after ready
  });

  // Custom title bar on Windows
  if (process.platform === 'win32') {
    mainWindow.setMenuBarVisibility(false);
  } else {
    Menu.setApplicationMenu(buildAppMenu());
  }

  // Load the HTML app
  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (isDev) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });

  mainWindow.on('close', (e) => {
    // On macOS, clicking X hides to tray instead of quitting
    if (process.platform === 'darwin' && !app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ─── TRAY ────────────────────────────────────────────────────
function createTray() {
  const iconPath = getIconPath('tray');
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'SethOS', enabled: false },
    { type: 'separator' },
    { label: 'Open', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { label: 'Restart Server', click: () => { stopPythonServer(); startPythonServer(); } },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
  ]);

  tray.setToolTip('SethOS');
  tray.setContextMenu(contextMenu);
  tray.on('click', () => { mainWindow?.show(); mainWindow?.focus(); });
}

// ─── ICON HELPERS ───────────────────────────────────────────
function getIconPath(type = 'app') {
  const base = path.join(__dirname, '..', 'assets');
  if (process.platform === 'win32') return path.join(base, 'icon.ico');
  if (process.platform === 'darwin') return path.join(base, type === 'tray' ? 'iconTemplate.png' : 'icon.icns');
  return path.join(base, 'icon.png');
}

// ─── APP MENU ───────────────────────────────────────────────
function buildAppMenu() {
  return Menu.buildFromTemplate([
    {
      label: 'SethOS',
      submenu: [
        { label: 'About SethOS', role: 'about' },
        { type: 'separator' },
        { label: 'Hide', accelerator: 'CmdOrCtrl+H', role: 'hide' },
        { type: 'separator' },
        { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => { app.isQuitting = true; app.quit(); } },
      ]
    },
    {
      label: 'View',
      submenu: [
        { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: () => mainWindow?.webContents.reload() },
        { label: 'Toggle DevTools', accelerator: 'F12', click: () => mainWindow?.webContents.toggleDevTools() },
        { type: 'separator' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ]
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' }, { role: 'zoom' },
      ]
    }
  ]);
}

// ─── IPC HANDLERS ───────────────────────────────────────────
ipcMain.handle('get-app-version', () => app.getVersion());
ipcMain.handle('get-platform', () => process.platform);
ipcMain.handle('server-status', () => ({ ready: serverReady, port: SERVER_PORT }));
ipcMain.handle('restart-server', () => { stopPythonServer(); startPythonServer(); return true; });

ipcMain.handle('open-external', (_, url) => shell.openExternal(url));
ipcMain.handle('show-item-in-folder', (_, filePath) => shell.showItemInFolder(filePath));

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('notify', (_, { title, body }) => {
  new Notification({ title, body }).show();
});

// ─── APP LIFECYCLE ──────────────────────────────────────────
app.whenReady().then(async () => {
  // Start Python backend
  startPythonServer();

  // Create window immediately (it loads while server starts)
  await createWindow();
  createTray();

  // Wait for server then notify renderer
  waitForServer().then((ok) => {
    if (ok) {
      serverReady = true;
      mainWindow?.webContents.send('server-ready');
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else mainWindow?.show();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopPythonServer();
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;
  stopPythonServer();
});

app.on('will-quit', () => stopPythonServer());
