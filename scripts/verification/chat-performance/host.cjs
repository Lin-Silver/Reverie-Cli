const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const repo = path.resolve(__dirname, '../../..');
const audit = path.join(repo, '.audit/chat-perf');
const root = path.join(audit, 'profile');
app.setPath('userData', path.join(root, 'chromium'));
app.commandLine.appendSwitch('remote-debugging-port', '9347');
let sequence = 0;
let win;
let child;
const pending = new Map();
const metrics = [];
const prefs = { language: 'en-US', inspectorOpen: false, recentProjects: [root], backgroundPreset: 'none' };
app.whenReady().then(async () => {
  child = spawn(process.env.PERF_KERNEL || path.join(repo, 'ReverieCli-py/venv/Scripts/python.exe'),
    process.env.PERF_KERNEL ? ['--sdk-bridge'] : ['-u', '-m', 'reverie.sdk_bridge'],
    { cwd: path.join(repo, 'ReverieCli-py'), env: { ...process.env, REVERIE_APP_ROOT: root }, windowsHide: true });
  child.stderr.on('data', data => fs.appendFileSync(path.join(audit, 'core.log'), data));
  createInterface({ input: child.stdout }).on('line', line => {
    let result;
    try { result = JSON.parse(line); } catch { return; }
    if (result.type === 'prompt.event') {
      if (win) win.webContents.send('core:event', result);
      return;
    }
    const request = pending.get(result.id);
    if (request) {
      pending.delete(result.id);
      metrics.push({ action: request.action, ms: performance.now() - request.start });
      if (result.type === 'error') request.reject(new Error(result.error));
      else request.resolve(result);
    } else if (result.type === 'event' && win) win.webContents.send('core:event', result);
  });
  ipcMain.handle('core:request', (_, action, payload) => new Promise((resolve, reject) => {
    const id = `perf-${++sequence}`;
    pending.set(id, { resolve, reject, action, start: performance.now() });
    child.stdin.write(JSON.stringify({ id, action, payload }) + '\n');
  }));
  ipcMain.handle('desktop:paths', () => ({ projectRoot: root, coreAppRoot: root, runtimeRoot: root, kernelPath: 'test' }));
  ipcMain.handle('desktop:ui-preferences', () => prefs);
  ipcMain.handle('desktop:set-ui-preferences', (_, patch) => Object.assign(prefs, patch));
  ipcMain.handle('desktop:appearance', () => ({ theme: 'dark', resolved: 'dark' }));
  ipcMain.handle('desktop:notify', () => undefined);
  ipcMain.handle('perf:metrics', () => metrics);
  win = new BrowserWindow({ show: true, width: 1480, height: 940, webPreferences: {
    preload: path.join(repo, 'ReverieCli-ui/dist-electron/preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false,
  } });
  win.webContents.on('console-message', (_, details) => {
    if (details.level === 'error') fs.appendFileSync(path.join(audit, 'renderer.log'), details.message + '\n');
  });
  await win.loadFile(path.join(process.env.PERF_RENDERER_ROOT || path.join(repo, 'ReverieCli-ui/dist'), 'index.html'));
  setInterval(() => fs.writeFileSync(path.join(audit, 'ipc-metrics.json'), JSON.stringify(metrics)), 500);
});
app.on('before-quit', () => child?.kill());
