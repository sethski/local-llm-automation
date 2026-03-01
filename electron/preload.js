/**
 * preload.js — Secure bridge between Electron main process and the web app
 * Exposes only safe, controlled APIs to the renderer (index.html)
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('sethOS', {
  // App info
  getVersion: () => ipcRenderer.invoke('get-app-version'),
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // Backend server
  serverStatus: () => ipcRenderer.invoke('server-status'),
  restartServer: () => ipcRenderer.invoke('restart-server'),
  onServerReady: (cb) => ipcRenderer.on('server-ready', cb),
  onServerError: (cb) => ipcRenderer.on('server-error', (_, msg) => cb(msg)),

  // Native dialogs
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  showInFolder: (path) => ipcRenderer.invoke('show-item-in-folder', path),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // Desktop notifications
  notify: (title, body) => ipcRenderer.invoke('notify', { title, body }),
});
