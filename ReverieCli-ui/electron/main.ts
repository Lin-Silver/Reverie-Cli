import { ViewInstances } from "./view-interactions";
import { app, BrowserWindow, clipboard, dialog, ipcMain, nativeImage, nativeTheme, Notification, protocol, shell, Tray } from "electron";
import { assertCoreAction, assertCoreResponse, normalizeCorePayload } from "./core-actions";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { appendFile, copyFile, readFile, rm, stat, writeFile } from "node:fs/promises";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import {
  findRepositoryCoreRoot,
  kernelExecutableName,
  packagedExecutableHome,
  packagedKernelPath,
  packagedRuntimeRoot,
} from "./runtime-paths";
import { resolveKernelSelection, TRUSTED_KERNELS_FILENAME } from "./kernel-resolver";
import { parseDesktopLaunchOptions, resolveDesktopStartupMode } from "./launch-options";
import { normalizeThemePreference, type ThemePreference, windowAppearance } from "./appearance";
import { createWindowTray, showWindow } from "./window-tray";
import { coreRequestTimeoutMs } from "./core-timeouts";
import { createGitBranch, getGitWorkspaceStatus, switchGitBranch } from "./git-workspace";
import { importAttachments, saveClipboardImage, validateAttachments, type ComposerAttachment } from "./attachments";
import { gitSnapshot, gitPatch, gitMutate, gitCommit, gitPushPlan, gitPush, gitOutput, readPreview, listDirectory, readEditorFile, saveEditorFile, type DiffScope, type PushPlan } from "./workbench";
import { TerminalManager, RunJournal, actions, saveActions, loadGoal, saveGoal, goalInstructions, readJson, atomicJson, type ProjectAction, type Goal, type LocalNotification } from "./session-workspace";
import { ExecutionCoordinator } from "./execution-coordinator";
import { WorkerPool } from "./worker-pool";
import { createManaged, listManaged, copyPlan, archivePlan, archiveManaged, restoreManaged, workingSnapshot } from "./isolated-workspaces";
import {
  activateWorkspaceInPlace,
  isWorkspaceDirectory,
  pathIsWithin,
  samePath,
} from "./workspace-lifecycle";
import {
  mergeUiPreferences,
  effectiveUiPreferences,
  initializeUiPreferences,
  normalizeUiVariant,
  normalizeUiPreferences,
  uiThemePreference,
  type StoredUiPreferences,
} from "./preferences";
import { VIEW_SCHEME, ViewHost } from "./view-host";
import { attachViewDownloadGuard, attachViewFrameGuards, attachViewProtocol, createViewGuardLog } from "./view-session";
import { prepareViewResolution } from "./view-resolve";
import { runIsolationProbe } from "./view-isolation-runner";

type JsonRecord = Record<string, unknown>;
type DesktopSettings = {
  projectRoot?: string;
  coreAppRoot?: string;
  theme?: ThemePreference;
  ui?: StoredUiPreferences;
};

const desktopStartedAt = Date.now();
const uiRoot = path.resolve(__dirname, "..");
const launchOptions = parseDesktopLaunchOptions(process.argv);

// Generative views are served from their own scheme so they never share the application's
// origin. It is a standard, secure scheme that obeys CSP and cannot fetch or run a service
// worker; privileges must be declared before the app becomes ready.
protocol.registerSchemesAsPrivileged([
  {
    scheme: VIEW_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: false,
      corsEnabled: false,
      bypassCSP: false,
      allowServiceWorkers: false,
      stream: false,
    },
  },
]);
const ownsDesktopInstance = launchOptions.tui || app.requestSingleInstanceLock();
if (!ownsDesktopInstance) app.quit();
const outerExecutableDirectory = process.env.PORTABLE_EXECUTABLE_DIR
  || (process.env.APPIMAGE ? path.dirname(process.env.APPIMAGE) : undefined);
const executableHome = packagedExecutableHome(process.execPath, outerExecutableDirectory);
const runtimeRoot = app.isPackaged
  ? packagedRuntimeRoot(executableHome)
  : path.join(uiRoot, ".runtime");
const runtimePaths = {
  root: runtimeRoot,
  userData: path.join(runtimeRoot, "user-data"),
  sessionData: path.join(runtimeRoot, "session-data"),
  cache: path.join(runtimeRoot, "cache"),
  logs: path.join(runtimeRoot, "logs"),
  temp: path.join(runtimeRoot, "temp"),
  crashDumps: path.join(runtimeRoot, "crash-dumps"),
  backgrounds: path.join(runtimeRoot, "backgrounds"),
  views: path.join(runtimeRoot, "views"),
  settings: path.join(runtimeRoot, "desktop-settings.json"),
};

for (const [key, value] of Object.entries(runtimePaths)) {
  if (key !== "settings") {
    awaitDirectory(value);
  }
}

app.setPath("userData", runtimePaths.userData);
app.setPath("sessionData", runtimePaths.sessionData);
app.setPath("cache", runtimePaths.cache);
app.setPath("logs", runtimePaths.logs);
app.setPath("temp", runtimePaths.temp);
app.setPath("crashDumps", runtimePaths.crashDumps);
app.commandLine.appendSwitch("disk-cache-dir", runtimePaths.cache);
process.env.TEMP = runtimePaths.temp;
process.env.TMP = runtimePaths.temp;

function awaitDirectory(directory: string): void {
  mkdirSync(directory, { recursive: true });
}

function internalKernelPath(): string {
  return app.isPackaged
    ? packagedKernelPath(process.execPath)
    : path.resolve(uiRoot, "..", "dist", kernelExecutableName());
}

let activeKernelPath = internalKernelPath();
const viewHost = new ViewHost({ root: runtimePaths.views });
const viewGuardLog = createViewGuardLog();
const knownWorkspaceRoots = new Set<string>();

async function selectKernelPath(preferExternal = true): Promise<string> {
  if (!app.isPackaged) return internalKernelPath();
  const selection = await resolveKernelSelection({
    internalPath: internalKernelPath(),
    externalHome: executableHome,
    manifestPath: path.join(app.getAppPath(), "build", "generated", TRUSTED_KERNELS_FILENAME),
    preferExternal,
  });
  activeKernelPath = selection.path;
  void log(`Kernel selected (${selection.source}): ${selection.path}; ${selection.reason}`);
  return selection.path;
}

function defaultCoreAppRoot(): string {
  if (!app.isPackaged) return path.dirname(internalKernelPath());
  return executableHome;
}

async function log(message: string): Promise<void> {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  await appendFile(path.join(runtimePaths.logs, "desktop.log"), line, "utf8").catch(() => undefined);
}

async function readDesktopSettings(): Promise<DesktopSettings> {
  try {
    const settings = JSON.parse(await readFile(runtimePaths.settings, "utf8")) as DesktopSettings;
    return { ...settings, ui: initializeUiPreferences(settings.ui, true) };
  } catch {
    return { ui: initializeUiPreferences(undefined, existsSync(runtimePaths.settings)) };
  }
}

async function saveDesktopSettings(settings: DesktopSettings): Promise<void> {
  await writeFile(runtimePaths.settings, JSON.stringify(settings, null, 2), "utf8");
}

let desktopSettingsQueue: Promise<void> = Promise.resolve();

async function mutateDesktopSettings(
  mutate: (settings: DesktopSettings) => DesktopSettings,
): Promise<DesktopSettings> {
  let updated: DesktopSettings = {};
  const operation = desktopSettingsQueue.then(async () => {
    updated = mutate(await readDesktopSettings());
    await saveDesktopSettings(updated);
  });
  desktopSettingsQueue = operation.then(() => undefined, () => undefined);
  await operation;
  return updated;
}

async function updateDesktopSettings(patch: DesktopSettings): Promise<DesktopSettings> {
  return mutateDesktopSettings((settings) => ({ ...settings, ...patch }));
}

const ratsDiscoveryRoots = String(process.env.REVERIE_RATS_DISCOVERY_ROOTS ?? "")
  .split(path.delimiter)
  .map((item) => item.trim())
  .filter(Boolean);
const RATS_PROVIDER_DISCOVERY_ADAPTERS: Record<string, () => string[]> = {
  // The production registry currently has only this verified provider adapter.
  "reverie.engine": () => [
    path.join(executableHome, "ReverieLocal", "RATS", "Services"),
    ...(!app.isPackaged
      ? [path.resolve(uiRoot, "..", "..", "Reverie Engine", "Reverie Engine", "bin", "ReverieLocal", "RATS", "Services")]
      : []),
  ],
};
for (const resolveRoots of Object.values(RATS_PROVIDER_DISCOVERY_ADAPTERS)) {
  ratsDiscoveryRoots.push(...resolveRoots());
}

function rememberProject(preferences: StoredUiPreferences, projectRoot: string): StoredUiPreferences {
  const resolved = path.resolve(projectRoot);
  const recentProjects = [
    resolved,
    ...preferences.recentProjects.filter((item) => !samePath(item, resolved)),
  ].filter(isWorkspaceDirectory).slice(0, 12);
  return { ...preferences, recentProjects };
}

function forgetProject(preferences: StoredUiPreferences, projectRoot: string): StoredUiPreferences {
  const target = path.resolve(projectRoot);
  return {
    ...preferences,
    recentProjects: preferences.recentProjects.filter((item) => !samePath(item, target)),
    archivedSessions: Object.fromEntries(
      Object.entries(preferences.archivedSessions).filter(([item]) => !samePath(item, target)),
    ),
  };
}

function attachmentDirectory(projectRoot: string): string {
  return path.join(path.resolve(projectRoot), ".reverie", "attachments");
}

function attachmentRoot(requested?: string): string {
  if (!bridge) throw new Error("Reverie core bridge is not initialized.");
  const root = path.resolve(requested || bridge.getProjectRoot());
  if (!samePath(root, bridge.getProjectRoot()) && !knownWorkspaceRoots.has(root.toLowerCase())) throw new Error("Select this workspace before accessing its files.");
  return root;
}

function attachmentDetails(projectRoot: string, items: ComposerAttachment[]): ComposerAttachment[] {
  return items.map(item => {
    if (item.status !== "ready" || !/\.(png|jpe?g|gif|bmp|webp)$/i.test(item.relativePath)) return item;
    const image = nativeImage.createFromPath(path.join(projectRoot, item.relativePath));
    if (image.isEmpty()) return item;
    const { width, height } = image.getSize();
    return { ...item, width, height, thumbnail: image.resize({ width: 96 }).toDataURL() };
  });
}

function uiPreferencesPayload(preferences: StoredUiPreferences): JsonRecord {
  preferences = effectiveUiPreferences(preferences);
  const backgroundPath = preferences.backgroundPath && existsSync(preferences.backgroundPath)
    ? preferences.backgroundPath
    : "";
  const { backgroundPath: _storedPath, liquidGlassAppearance: _glass, ...rest } = preferences;
  return {
    ...rest,
    backgroundUrl: backgroundPath
      ? pathToFileURL(backgroundPath).href
      : "",
    backgroundName: backgroundPath ? path.basename(backgroundPath) : "",
  };
}

function appearancePayload(): { theme: ThemePreference; resolved: "dark" | "light" } {
  return {
    theme: normalizeThemePreference(nativeTheme.themeSource),
    resolved: nativeTheme.shouldUseDarkColors ? "dark" : "light",
  };
}

function applyWindowAppearance(): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const appearance = windowAppearance(nativeTheme.shouldUseDarkColors);
  mainWindow.setBackgroundColor(appearance.backgroundColor);
  if (process.platform === "win32") {
    mainWindow.setTitleBarOverlay({
      color: appearance.overlayColor,
      symbolColor: appearance.symbolColor,
    height: 58,
    });
  }
}

class CoreBridge {
  private child: ChildProcessWithoutNullStreams | null = null;
  private starting: Promise<void> | null = null;
  private sequence = 0;
  private pending = new Map<
    string,
    {
      resolve: (value: JsonRecord) => void;
      reject: (reason: Error) => void;
      timer: ReturnType<typeof setTimeout> | null;
      action: string;
    }
  >();

  constructor(
    private projectRoot: string,
    private coreAppRoot: string,
    private readonly executablePath: string,
    private sendEvent: (message: JsonRecord) => void,
  ) {}

  setEventHandler(sendEvent: (message: JsonRecord) => void): void { this.sendEvent = sendEvent; }

  setProjectRoot(projectRoot: string): void {
    this.projectRoot = path.resolve(projectRoot);
  }

  getProjectRoot(): string {
    return this.projectRoot;
  }

  hasActivePrompt(): boolean { return [...this.pending.values()].some(item => ["runPrompt", "resumePrompt", "callViewTool"].includes(item.action)); }
  getPid(): number | undefined { return this.child?.pid; }

  setCoreAppRoot(coreAppRoot: string): void {
    this.coreAppRoot = path.resolve(coreAppRoot);
  }

  getCoreAppRoot(): string {
    return this.coreAppRoot;
  }

  async start(): Promise<void> {
    if (this.starting) return this.starting;
    if (this.child && !this.child.killed) return;

    this.starting = new Promise<void>((resolve, reject) => {
      const executable = this.executablePath;
      if (!existsSync(executable)) {
        reject(new Error(`Reverie core not found: ${executable}`));
        return;
      }

      awaitDirectory(this.coreAppRoot);
      const child = spawn(executable, ["--sdk-bridge"], {
        cwd: this.projectRoot,
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONIOENCODING: "utf-8",
          PYTHONUTF8: "1",
          REVERIE_APP_ROOT: this.coreAppRoot,
          REVERIE_RATS_DISCOVERY_ROOTS: [...new Set(ratsDiscoveryRoots.map((item) => path.resolve(item)))].join(path.delimiter),
          TEMP: runtimePaths.temp,
          TMP: runtimePaths.temp,
        },
      });
      this.child = child;
      let ready = false;
      const lines = readline.createInterface({ input: child.stdout });
      lines.on("line", (line) => {
        let message: JsonRecord;
        try {
          message = JSON.parse(line) as JsonRecord;
        } catch {
          void log(`Invalid core JSON: ${line.slice(0, 500)}`);
          return;
        }
        if (message.type === "ready" && !ready) {
          ready = true;
          void log(`Core ready in ${Date.now() - desktopStartedAt} ms`);
          resolve();
          return;
        }
        if (message.type === "prompt.event") {
          this.sendEvent(message);
          return;
        }
        const id = String(message.id ?? "");
        const request = this.pending.get(id);
        if (!request) return;
        this.pending.delete(id);
        if (request.timer) clearTimeout(request.timer);
        if (message.type === "error") {
          request.reject(new Error(String(message.error ?? "Unknown core error")));
        } else {
          request.resolve(message);
        }
      });
      child.stderr.on("data", (chunk: Buffer) => {
        void log(`CORE ${chunk.toString("utf8").trimEnd()}`);
      });
      child.once("error", (error) => {
        if (!ready) reject(error);
        void log(`Core process error: ${error.message}`);
      });
      child.once("exit", (code, signal) => {
        const error = new Error(`Reverie core exited (${code ?? signal ?? "unknown"})`);
        if (this.child === child) {
          for (const request of this.pending.values()) {
            if (request.timer) clearTimeout(request.timer);
            request.reject(error);
          }
          this.pending.clear();
          this.child = null;
        }
        if (!ready) reject(error);
        void log(error.message);
      });
    }).finally(() => {
      this.starting = null;
    });

    return this.starting;
  }

  async request(action: string, payload: JsonRecord = {}): Promise<JsonRecord> {
    await this.start();
    const child = this.child;
    if (!child || child.killed) throw new Error("Reverie core is not running.");
    const id = `desktop-${Date.now()}-${++this.sequence}`;
    const timeoutMs = coreRequestTimeoutMs(action);
    return new Promise<JsonRecord>((resolve, reject) => {
      const timer = timeoutMs > 0
        ? setTimeout(() => {
            if (!this.pending.delete(id)) return;
            reject(new Error(`Reverie core request timed out: ${action}`));
          }, timeoutMs)
        : null;
      this.pending.set(id, { resolve, reject, timer, action });
      child.stdin.write(`${JSON.stringify({ id, action, payload })}\n`, "utf8", (error) => {
        if (error) {
          this.pending.delete(id);
          if (timer) clearTimeout(timer);
          reject(error);
        }
      });
    });
  }

  async stop(reason = "Core stopped"): Promise<void> {
    const child = this.child;
    if (!child) return;
    for (const request of this.pending.values()) {
      if (request.timer) clearTimeout(request.timer);
      request.reject(new Error(reason));
    }
    this.pending.clear();
    if (process.platform === "win32" && child.pid) {
      await new Promise<void>((resolve) => {
        const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
          windowsHide: true,
          stdio: "ignore",
        });
        killer.once("error", () => {
          child.kill();
          resolve();
        });
        killer.once("exit", () => resolve());
      });
    } else {
      child.kill();
    }
    if (this.child === child) this.child = null;
  }

  async restart(): Promise<void> {
    await this.stop("Prompt cancelled; core restarted.");
    await this.start();
  }
}

let mainWindow: BrowserWindow | null = null;
let windowTray: Tray | null = null;
let quitRequested = false;
let quitDialogOpen = false;
let bridge: CoreBridge | null = null;
const terminals = new TerminalManager(message => mainWindow?.webContents.send("core:event", message));
const journal = new RunJournal();
const executors = new Map<string, { worker: CoreBridge; root: string; sessionId: string; runId: string; interactionId?: string }>();
const workerPool = new WorkerPool<CoreBridge>(4, worker => worker.stop("Idle kernel released."));
const approvalOwners = new Map<string, string>();
const stopBeforeStart = new Set<string>();
const viewInstances = new ViewInstances();
const coordinator = new ExecutionCoordinator(entries => mainWindow?.webContents.send("core:event", { type: "executors.changed", entries, maximum: 4 }));
const notificationFile = path.join(runtimeRoot, "notifications.json");
let notifications: LocalNotification[] = [];
let notificationMuted = false;
async function publishNotification(projectRoot: string, sessionId: string, runId: string, kind: string, title: string, body: string): Promise<void> {
  const id = `${runId}:${kind}`;
  if (notifications.some(item => item.id === id)) return;
  const item: LocalNotification = { id, projectRoot, sessionId, runId, kind, title, body, createdAt: new Date().toISOString(), read: false, osState: notificationMuted ? "muted" : "not requested" };
  notifications.unshift(item); await atomicJson(notificationFile, notifications);
  mainWindow?.webContents.send("core:event", { type: "notification.changed", notification: item });
  if (notificationMuted || (mainWindow?.isFocused() && !mainWindow.isMinimized())) return;
  if (!Notification.isSupported()) { item.osState = "unsupported"; await atomicJson(notificationFile, notifications); return; }
  try {
    const notification = new Notification({ title, body: body.slice(0, 220) });
    item.osState = "requested; OS delivery unconfirmed";
    notification.on("show", () => { item.osState = "shown"; void atomicJson(notificationFile, notifications); });
    notification.on("failed", (_event, error) => { item.osState = `failed: ${error}`; void atomicJson(notificationFile, notifications); });
    notification.on("click", () => { focusMainWindow(); mainWindow?.webContents.send("core:event", { type: "notification.open", notification: item }); });
    notification.show(); await atomicJson(notificationFile, notifications);
  } catch (error) { item.osState = `failed: ${String(error)}`; await atomicJson(notificationFile, notifications); }
}

if (!launchOptions.tui) {
  app.on("second-instance", (_event, argv, workingDirectory) => {
    const options = parseDesktopLaunchOptions(argv, workingDirectory);
    if (options.projectRoot && isWorkspaceDirectory(options.projectRoot)) {
      if (bridge) {
        void activateWorkspace(options.projectRoot).catch((error) => {
          void log(`Second-instance workspace switch failed: ${error instanceof Error ? error.message : String(error)}`);
        });
      } else {
        void updateDesktopSettings({ projectRoot: options.projectRoot });
      }
    }
    if (mainWindow) showWindow(mainWindow);
  });
}

function localizedUiText(language: StoredUiPreferences["language"], chinese: string, english: string): string {
  return language === "en-US" ? english : chinese;
}

async function requestAppQuit(): Promise<void> {
  if (quitDialogOpen || quitRequested) return;
  const active = coordinator.list();
  const manual = terminals.active();
  if (mainWindow && (active.length || manual.length)) {
    quitDialogOpen = true;
    try {
      showWindow(mainWindow);
      const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
      const result = await dialog.showMessageBox(mainWindow, {
        type: "warning", title: "Reverie",
        message: localizedUiText(preferences.language, "退出会结束后台任务和用户终端。", "Quitting ends background tasks and user terminals."),
        detail: [...active.map(item => `${item.projectRoot}\n${item.sessionId} · ${item.state} · PID ${item.pid || "?"}`), ...manual.map(item => `${item.cwd}\n${item.sessionId} · PID ${item.pid}`)].join("\n\n"),
        buttons: [localizedUiText(preferences.language, "保留运行", "Keep running"), localizedUiText(preferences.language, "退出并结束进程", "Quit and end processes")],
        defaultId: 0, cancelId: 0,
      });
      if (result.response !== 1) return;
    } finally {
      quitDialogOpen = false;
    }
  }
  app.quit();
}

async function activateWorkspace(projectRoot: string): Promise<string> {
  if (!bridge) throw new Error("Reverie core bridge is not initialized.");
  viewInstances.clear();
  const resolved = await activateWorkspaceInPlace(bridge, projectRoot, async (nextProjectRoot) => {
    knownWorkspaceRoots.add(path.resolve(nextProjectRoot).toLowerCase());
    await mutateDesktopSettings((settings) => ({
      ...settings,
      projectRoot: nextProjectRoot,
      ui: rememberProject(normalizeUiPreferences(settings.ui), nextProjectRoot),
    }));
  });
  void log(`Workspace switched in the existing core process: ${resolved}`);
  return resolved;
}

async function createWindow(): Promise<void> {
  const executable = await selectKernelPath(false);
  const settings = await readDesktopSettings();
  nativeTheme.themeSource = uiThemePreference(normalizeUiPreferences(settings.ui), settings.theme);
  const appearance = windowAppearance(nativeTheme.shouldUseDarkColors);
  const repositoryCoreRoot = app.isPackaged ? findRepositoryCoreRoot(executableHome) : null;
  const defaultProjectRoot = app.isPackaged
    ? (repositoryCoreRoot ? path.dirname(repositoryCoreRoot) : executableHome)
    : path.resolve(uiRoot, "..");
  const projectRoot = launchOptions.projectRoot && isWorkspaceDirectory(launchOptions.projectRoot)
    ? path.resolve(launchOptions.projectRoot)
    : settings.projectRoot && isWorkspaceDirectory(settings.projectRoot)
      ? path.resolve(settings.projectRoot)
      : defaultProjectRoot;
  const coreAppRoot =
    settings.coreAppRoot && existsSync(settings.coreAppRoot)
      ? path.resolve(settings.coreAppRoot)
      : defaultCoreAppRoot();
  await mutateDesktopSettings((current) => ({
    ...current,
    projectRoot,
    ui: rememberProject(normalizeUiPreferences(current.ui), projectRoot),
  }));

  mainWindow = new BrowserWindow({
    width: 1500,
    height: 960,
    minWidth: 1080,
    minHeight: 700,
    backgroundColor: appearance.backgroundColor,
    show: false,
    title: "Reverie",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: appearance.overlayColor,
      symbolColor: appearance.symbolColor,
      height: 58,
    },
    icon: app.isPackaged
      ? undefined
      : path.resolve(uiRoot, "..", "ReverieCli-py", "reverie.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });

  knownWorkspaceRoots.add(path.resolve(projectRoot).toLowerCase());
  bridge = new CoreBridge(projectRoot, coreAppRoot, executable, (message) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("core:event", message);
    }
  });
  void bridge.start().catch((error) => log(`Core startup failed: ${error instanceof Error ? error.message : String(error)}`));

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  // Generative-view boundaries that cannot affect the shell: the view scheme answers 404
  // until a view is registered, the download guard only fires for `reverie-view:` items,
  // and the navigation guard only judges sub-frames, of which the shell has none.
  attachViewProtocol(mainWindow.webContents.session, viewHost);
  attachViewDownloadGuard(mainWindow.webContents.session, viewGuardLog);
  attachViewFrameGuards(mainWindow.webContents, viewHost, viewGuardLog);
  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type === "keyDown" && input.key === "Escape" && mainWindow?.webContents.focusedFrame?.url.startsWith("reverie-view:")) {
      mainWindow.webContents.send("core:event", { type: "view.escape" });
    }
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const current = mainWindow?.webContents.getURL() ?? "";
    if (url !== current) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    }
  });
  mainWindow.webContents.on("did-start-navigation", (_event, _url, _inPlace, isMainFrame) => { if (isMainFrame) viewInstances.clear(); });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  windowTray?.destroy();
  windowTray = createWindowTray(
    mainWindow, path.join(uiRoot, "dist", "reverie-mark.png"),
    normalizeUiPreferences(settings.ui).language,
    () => quitRequested,
    () => void requestAppQuit().catch(error => log(`Quit confirmation failed: ${String(error)}`)),
  );
  applyWindowAppearance();

  const devServer = process.env.VITE_DEV_SERVER_URL;
  if (devServer) {
    await mainWindow.loadURL(devServer);
  } else {
    await mainWindow.loadFile(path.join(uiRoot, "dist", "index.html"));
  }
}

ipcMain.handle("core:request", async (_event, rawAction: unknown, rawPayload?: unknown) => {
  if (!bridge) throw new Error("Reverie core bridge is not initialized.");
  if (!mainWindow || _event.sender !== mainWindow.webContents || _event.senderFrame !== mainWindow.webContents.mainFrame) throw new Error("Only the trusted top frame may use core IPC.");
  const action = assertCoreAction(rawAction);
  const payload = normalizeCorePayload(rawPayload);
  if (action === "getContextUsage" && payload.sessionId) {
    const root = path.resolve(String(payload.projectRoot || bridge.getProjectRoot()));
    const entry = coordinator.find(root, String(payload.sessionId));
    const executor = entry ? executors.get(entry.id) : undefined;
    if (executor?.worker.hasActivePrompt()) {
      return assertCoreResponse(action, await executor.worker.request(action, { ...payload, liveRead: true }));
    }
  }
  if (action === "releaseView") {
    const id = String(payload.interactionId || "");
    const released = viewInstances.revoke(id);
    if (released) viewHost.release(released.viewId);
    for (const [leaseId, executor] of executors) if (executor.interactionId === id) {
      stopBeforeStart.add(leaseId);
      if (executor.worker.hasActivePrompt()) void executor.worker.request("stopPrompt", { sessionId: executor.sessionId }).catch(() => {});
    }
    return { type: "view.released" };
  }
  if (["setViewState", "updateViewModelContext", "callViewTool"].includes(action)) {
    const ref = viewInstances.require(payload);
    if (!samePath(ref.projectRoot, bridge.getProjectRoot())) throw new Error("View workspace is no longer selected.");
    payload.projectRoot = ref.projectRoot;
  }
  if (["runPrompt", "resumePrompt", "callViewTool"].includes(action)) {
    const admin = bridge; const root = attachmentRoot(String(payload.projectRoot || admin.getProjectRoot())); const sessionId = String(payload.sessionId || "");
    const viewCall = action === "callViewTool";
    const models = viewCall ? {} : payload.source && payload.model
      ? { active_model: { id: payload.model }, active_source: payload.source }
      : (await admin.request("getModelSources")).models as JsonRecord;
    const selectedModel=models.active_model as JsonRecord | null;
    if (!payload.source && selectedModel?.id) payload.source=models.active_source;
    if (!payload.model && selectedModel?.id) payload.model=selectedModel.id;
    const record = await journal.start(root, sessionId, payload, JSON.stringify(models.active_model || {})); payload.runId = record.id; payload.projectRoot = root;
    let leaseId = ""; let worker: CoreBridge | null = null; let reusable = false;
    const workerKey = JSON.stringify([root, admin.getCoreAppRoot(), activeKernelPath]);
    try {
      const lease = await coordinator.acquire(root, sessionId, payload.runType === "review", !viewCall); leaseId = lease.id;
      payload.goalContext = payload.runType === "review" ? "" : goalInstructions(await loadGoal(root, sessionId));
      await journal.update(record.id, { goalContext: String(payload.goalContext) });
      const acquired = await workerPool.acquire(workerKey, () => new CoreBridge(root, admin.getCoreAppRoot(), activeKernelPath, () => {}));
      worker = acquired.worker;
      worker.setEventHandler(message => {
        const event: JsonRecord = { ...(message.event as JsonRecord), project_root: root, session_id: sessionId, run_id: record.id };
        journal.event(record.id, event);
        if (event.type === "approval.request") { approvalOwners.set(String(event.approval_id), lease.id); void publishNotification(root, sessionId, record.id, `approval:${event.approval_id}`, "Reverie 需要审批 / Approval needed", String(event.command || event.tool || event.message || "")); }
        if (event.type === "run.control") void journal.update(record.id, { state: String(event.state) });
        mainWindow?.webContents.send("core:event", { ...message, event });
      });
      executors.set(lease.id, { worker, root, sessionId, runId: record.id, interactionId: viewCall ? String(payload.interactionId) : undefined });
      if (viewCall) mainWindow?.webContents.send("core:event", { type: "prompt.event", event: { type: "view.run", state: "running", project_root: root, session_id: sessionId, run_id: record.id } });
      const preparation = await Promise.allSettled([
        acquired.reused ? Promise.resolve() : worker.request("initialize", { projectRoot: root, deferPayloads: true }),
        workingSnapshot(root, `refs/reverie/runs/${record.id}/before`).then(() => journal.update(record.id,{beforeRef:`refs/reverie/runs/${record.id}/before`})).catch(error => { journal.event(record.id,{type:"snapshot.unavailable",error:String(error)}); }),
      ]);
      for (const result of preparation) if (result.status === "rejected") throw result.reason;
      coordinator.pid(lease.id, worker.getPid() || 0); await journal.update(record.id, { state: "running", pid: worker.getPid() });
      if (stopBeforeStart.has(lease.id)) throw new Error("Run stopped before tools started.");
      if (viewCall) viewInstances.require(payload);
      const response = await worker.request(action, payload);
      const result = viewCall ? { success: response.status === "success", output_text: response.output, error: response.error } : response.result as JsonRecord;
      reusable = true;
      const cancelled = !result.success && stopBeforeStart.has(lease.id);
      if (!cancelled) {
        try { await workingSnapshot(root, `refs/reverie/runs/${record.id}/after`); await journal.update(record.id,{afterRef:`refs/reverie/runs/${record.id}/after`}); } catch (error) { journal.event(record.id,{type:"snapshot.unavailable",error:String(error)}); }
      }
      await journal.finish(record.id, result, result.success ? "completed" : cancelled ? "cancelled" : "failed");
      if (!cancelled) await publishNotification(root, sessionId, record.id, result.success ? "completed" : "failed", result.success ? "Reverie 已完成 / Completed" : "Reverie 运行失败 / Failed", String(result.error || result.output_text || "").slice(0,220));
      if (viewCall) viewInstances.require(payload);
      return assertCoreResponse(action, response);
    } catch (error) { await journal.finish(record.id, {error:String(error)}, String(error).includes("Queued run cancelled") || (leaseId && stopBeforeStart.has(leaseId)) ? "cancelled" : "interrupted"); await publishNotification(root, sessionId, record.id, "recovery", "Reverie 需要核对 / Needs review", String(error)); throw error; }
    finally { if (viewCall && leaseId) mainWindow?.webContents.send("core:event", { type: "prompt.event", event: { type: "view.run", state: "finished", project_root: root, session_id: sessionId, run_id: record.id } }); if (worker) { worker.setEventHandler(() => {}); await workerPool.release(workerKey, worker, reusable); } if (leaseId) { executors.delete(leaseId); stopBeforeStart.delete(leaseId); coordinator.release(leaseId); for (const [id, owner] of approvalOwners) if (owner === leaseId) approvalOwners.delete(id); } }
  }
  if (["stopPrompt", "steerPrompt", "pausePrompt", "continuePrompt"].includes(action)) {
    const root = path.resolve(String(payload.projectRoot || bridge.getProjectRoot())); const sessionId = String(payload.sessionId || "");
    if (action === "stopPrompt" && coordinator.cancelQueued(root, sessionId)) return { type: "run.control", state: "cancelled", run_id: "" };
    const entry = coordinator.find(root, sessionId); const executor = entry ? executors.get(entry.id) : undefined;
    if (entry && !executor && action === "stopPrompt") { stopBeforeStart.add(entry.id); return { type:"run.control",state:"stopping",run_id:"" }; }
    if (!entry || !executor) throw new Error("No active run belongs to this project and conversation.");
    if (action === "stopPrompt") { stopBeforeStart.add(entry.id); if (!executor.worker.hasActivePrompt()) return { type:"run.control",state:"stopping",run_id:executor.runId }; }
    return assertCoreResponse(action, await executor.worker.request(action,payload));
  }
  if (action === "resolveApproval") {
    const owner = approvalOwners.get(String(payload.approvalId));
    const executor = owner ? executors.get(owner) : undefined;
    if (!executor || stopBeforeStart.has(owner!)) throw new Error("Approval expired or its run stopped.");
    if (payload.sessionId && payload.sessionId !== executor.sessionId || payload.projectRoot && !samePath(String(payload.projectRoot),executor.root)) throw new Error("Approval belongs to a different run.");
    approvalOwners.delete(String(payload.approvalId)); return assertCoreResponse(action, await executor.worker.request(action,payload));
  }
  if (action === "getView") {
    // The kernel's response carries the model-safe `view` AND an authoritative
    // `resolved` path block. prepareViewResolution hands the paths to the host
    // registrar ONLY and builds a path-free reference for the renderer. The
    // registrar widens containment to the kernel ViewStore's own views dir
    // (trusted, never model-supplied) and binds an opaque `reverie-view:` url.
    // A forged view id never reaches here: the kernel's getView raises first.
    const generation = viewInstances.generation;
    const response = await bridge.request(action, payload);
    if (generation !== viewInstances.generation) throw new Error("View resolution expired during session switch.");
    const reference = await prepareViewResolution(response, async (source) => {
      await viewHost.allowRoot(source.viewsRoot);
      const binding = await viewHost.register({
        viewId: source.viewId,
        revision: source.revision,
        sessionId: source.sessionId,
        directory: source.directory,
        entry: source.entry,
        mimeType: source.mimeType,
      });
      return { url: binding.url, policyId: binding.policyId };
    });
    if (generation !== viewInstances.generation) throw new Error("View resolution expired during session switch.");
    const interactionId = viewInstances.register({ ...reference, projectRoot: bridge.getProjectRoot() });
    return assertCoreResponse(action, { type: "view.resolved", view: { ...reference, interactionId } });
  }
  if (["deleteSession", "deleteSessions", "forkSession", "rewindSession", "rollbackCheckpoint", "deleteProjectData"].includes(action)) {
    const root=String(payload.projectRoot || bridge.getProjectRoot()); const sessionId=String(payload.sessionId || "");
    if (coordinator.list().some(item=>samePath(item.projectRoot,root) && (!sessionId || item.sessionId===sessionId)) || terminals.active(root).some(item=>!sessionId || item.sessionId===sessionId)) throw new Error("Stop the affected session runs and terminals before removing or restoring records.");
  }
  if (action === "getSession" && viewInstances.selectSession(String(payload.sessionId || ""))) viewHost.releaseAll();
  if (["initialize", "loadSession", "createSession", "deleteSession", "deleteSessions", "forkSession", "rewindSession", "deleteProjectData"].includes(action)) { viewInstances.clear(); viewHost.releaseAll(); }
  const response = await bridge.request(action, payload);
  if (action === "initialize") {
    void log(`Desktop initialized in ${Date.now() - desktopStartedAt} ms`);
  }
  return assertCoreResponse(action, response);
});

ipcMain.handle("core:cancel", async (_event, owner?: {projectRoot:string;sessionId:string}) => {
  if (!mainWindow || _event.senderFrame !== mainWindow.webContents.mainFrame) throw new Error("Only the trusted top frame may cancel runs.");
  if (!bridge) return;
  const active = [...executors.values()].filter(item => samePath(item.root, owner?.projectRoot || bridge!.getProjectRoot()) && (!owner || item.sessionId === owner.sessionId));
  if (active.length > 1) throw new Error("Select a specific session run for forced termination.");
  if (active[0]) await active[0].worker.stop("Forced stop requested; verify incomplete effects."); else await bridge.restart();
});

// Bring the window to the front: restore it if minimized, show it if hidden,
// and take focus. Same sequence the single-instance guard uses at main.ts:418.
function focusMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

// Raise a native OS toast in Reverie's name. Gated to the background: when the
// window is focused the user is already looking at the in-app panel/body, so a
// system toast would just be the same thing said three times. The renderer
// decides *when* to call this (it owns the translated copy); main owns *how*.
// Clicking the toast pulls Reverie to the foreground.
function notifyDesktop(title: string, body: string): void {
  if (!Notification.isSupported()) return;
  if (mainWindow && !mainWindow.isDestroyed() && mainWindow.isFocused() && !mainWindow.isMinimized()) return;
  const icon = app.isPackaged
    ? undefined
    : path.resolve(uiRoot, "..", "ReverieCli-py", "reverie.ico");
  try {
    const notification = new Notification({ title, body, icon, silent: false });
    notification.on("click", focusMainWindow);
    notification.show();
  } catch (error) {
    void log(`Notification failed: ${error instanceof Error ? error.message : String(error)}`);
  }
}

ipcMain.handle("desktop:notify", (_event, rawPayload: unknown) => {
  const payload = (rawPayload ?? {}) as { title?: unknown; body?: unknown };
  const title = typeof payload.title === "string" && payload.title.trim() ? payload.title.trim() : "Reverie";
  const body = typeof payload.body === "string" ? payload.body.trim().slice(0, 220) : "";
  if (!body) return;
  notifyDesktop(title, body);
});

ipcMain.handle("desktop:select-workspace", async () => {
  if (!mainWindow || !bridge) return null;
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, "选择 Reverie 工作区", "Choose a Reverie workspace"),
    defaultPath: bridge.getProjectRoot(),
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  return activateWorkspace(result.filePaths[0]);
});

ipcMain.handle("desktop:switch-workspace", async (_event, projectRoot: string) => {
  if (!mainWindow || !bridge) return null;
  return activateWorkspace(String(projectRoot ?? ""));
});

ipcMain.handle("desktop:delete-workspace", async (_event, projectRoot: string) => {
  if (!mainWindow || !bridge) return null;
  const requestedProject = String(projectRoot ?? "").trim();
  if (!requestedProject) throw new Error("Project path is required.");
  const target = path.resolve(requestedProject);
  if (coordinator.list().some(item=>samePath(item.projectRoot,target)) || terminals.active(target).length) throw new Error("Stop this project's runs and terminals before deleting its records.");
  const current = path.resolve(bridge.getProjectRoot());
  const settings = await readDesktopSettings();
  const preferences = normalizeUiPreferences(settings.ui);
  const knownProjects = [current, ...preferences.recentProjects];
  if (!knownProjects.some((item) => samePath(item, target))) {
    throw new Error("Only the current or a recent Reverie project can be deleted.");
  }
  const remaining = preferences.recentProjects
    .map((item) => path.resolve(item))
    .filter((item) => !samePath(item, target) && isWorkspaceDirectory(item));
  let nextProjectRoot = samePath(current, target) ? remaining[0] : current;

  if (!nextProjectRoot) {
    const selection = await dialog.showOpenDialog(mainWindow, {
      title: localizedUiText(preferences.language, "删除当前项目后切换到…", "Choose a workspace after deleting the current project…"),
      defaultPath: path.dirname(target),
      properties: ["openDirectory", "createDirectory"],
    });
    if (selection.canceled || !selection.filePaths[0]) return null;
    nextProjectRoot = path.resolve(selection.filePaths[0]);
    if (samePath(nextProjectRoot, target)) {
      throw new Error(localizedUiText(preferences.language, "请选择另一个工作区后再删除当前项目。", "Choose another workspace before deleting the current project."));
    }
  }

  let deletedSessions = 0;
  if (existsSync(target)) {
    const response = await bridge.request("deleteProjectData", { projectRoot: target, confirmed: true });
    deletedSessions = Number(response.deleted_sessions ?? 0);
    const attachments = attachmentDirectory(target);
    if (path.dirname(attachments).toLowerCase() === path.join(target, ".reverie").toLowerCase()) {
      await rm(attachments, { recursive: true, force: true });
    }
  }

  const updated = await mutateDesktopSettings((currentSettings) => {
    const withoutTarget = forgetProject(normalizeUiPreferences(currentSettings.ui), target);
    return {
      ...currentSettings,
      projectRoot: nextProjectRoot,
      ui: rememberProject(withoutTarget, nextProjectRoot),
    };
  });
  bridge.setProjectRoot(nextProjectRoot);
  return {
    projectRoot: nextProjectRoot,
    deletedSessions,
    preferences: uiPreferencesPayload(normalizeUiPreferences(updated.ui)),
  };
});

ipcMain.handle("desktop:select-attachment", async (_event, requestedRoot?: string) => {
  if (!mainWindow || !bridge) return null;
  const projectRoot = attachmentRoot(requestedRoot);
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, "选择要提供给 Reverie 的文件", "Choose a file to provide to Reverie"),
    defaultPath: projectRoot,
    properties: ["openFile"],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  return attachmentDetails(projectRoot, await importAttachments(projectRoot, [result.filePaths[0]]))[0];
});

ipcMain.handle("desktop:import-dropped-files", async (_event, paths: unknown, requestedRoot?: string, copy = false) => {
  if (!bridge || !Array.isArray(paths) || paths.length > 20 || !paths.every((item) => typeof item === "string")) {
    throw new Error("Select up to 20 local files to attach.");
  }
  const projectRoot = attachmentRoot(requestedRoot);
  return attachmentDetails(projectRoot, await importAttachments(projectRoot, paths, copy));
});

ipcMain.handle("desktop:paste-image", async (_event, requestedRoot: string) => {
  const root = attachmentRoot(requestedRoot);
  const item = await saveClipboardImage(root, clipboard.readImage().toPNG());
  return attachmentDetails(root, [item])[0];
});

ipcMain.handle("desktop:retry-attachment", async (_event, requestedRoot: string, item: ComposerAttachment, copy = false) => {
  const root = attachmentRoot(requestedRoot);
  if (!item.sourcePath) throw new Error("请选择文件重新导入 / Select the file again.");
  return attachmentDetails(root, await importAttachments(root, [item.sourcePath], copy))[0];
});

ipcMain.handle("desktop:git-status", async () => bridge ? getGitWorkspaceStatus(bridge.getProjectRoot()) : null);
ipcMain.handle("desktop:workbench", async (_event, operation: string, payload: JsonRecord = {}) => {
  if (!bridge) throw new Error("Core is not initialized.");
  const root = attachmentRoot(String(payload.projectRoot || bridge.getProjectRoot()));
  const sessionId = String(payload.sessionId || "");
  if (["mutate", "commit", "push", "fetch"].includes(operation) && (coordinator.list().some(item=>samePath(item.projectRoot,root)) || terminals.active(root).length)) throw new Error("Wait for the active run and user terminals before changing this repository.");
  if (operation === "executors") return { entries: coordinator.list(), maximum: coordinator.maximum };
  if (operation === "validate-input") return { attachments: await validateAttachments(root,payload.attachments as ComposerAttachment[] || []) };
  if (operation === "worktrees") return { worktrees: await listManaged(root) };
  if (operation === "worktree-copy-plan") return copyPlan(root);
  if (operation === "worktree-create") { if (coordinator.busy(root)) throw new Error("Wait for this checkout's writer before copying or creating a worktree."); return createManaged(root, String(payload.name || ""), String(payload.base || "HEAD"), payload.files as string[] || [], String(payload.version || "")); }
  if (operation === "worktree-archive-plan") return archivePlan(root, String(payload.id || ""));
  if (operation === "worktree-archive") { const plan = await archivePlan(root, String(payload.id || "")); if (coordinator.list().some(item=>samePath(item.projectRoot,plan.workspace.path)) || terminals.active(plan.workspace.path).length) throw new Error("Stop this worktree's runs and terminals before archiving."); if (payload.confirmed !== true) throw new Error("Confirm archive scope first."); return archiveManaged(root, String(payload.id || ""), String(payload.version || ""), payload.preserveIgnored as string[] || [], payload.discardIgnored as string[] || []); }
  if (operation === "worktree-restore") return restoreManaged(root, String(payload.id || ""));
  if (operation === "terminals") return { terminals: await terminals.load(root, sessionId), active: terminals.active().length };
  if (operation === "terminal-create") return terminals.create(root, sessionId, String(payload.cwd || "."));
  if (operation === "terminal-write") { terminals.write(String(payload.id || ""), root, sessionId, String(payload.data || "")); return { written: true }; }
  if (operation === "terminal-resize") { terminals.resize(String(payload.id || ""), root, sessionId, Number(payload.cols), Number(payload.rows)); return { resized: true }; }
  if (operation === "terminal-read") return terminals.read(String(payload.id || ""), root, sessionId);
  if (operation === "terminal-close") { if (payload.confirmed !== true) throw new Error("Confirm ending the selected terminal and its children."); await terminals.close(String(payload.id || ""), root, sessionId); return { closed: true }; }
  if (operation === "actions") return { actions: await actions(root) };
  if (operation === "save-actions") { await saveActions(root, payload.actions as ProjectAction[]); return { saved: true }; }
  if (operation === "action-run") { if (payload.confirmed !== true) throw new Error("Inspect and confirm the action command before running."); const action = (await actions(root)).find(item => item.id === payload.id); if (!action) throw new Error("Action no longer exists."); return terminals.create(root, sessionId, action.cwd, action); }
  if (operation === "goal") return { goal: await loadGoal(root, sessionId) };
  if (operation === "save-goal") { await saveGoal(root, sessionId, payload.goal as Goal | null); return { saved: true }; }
  if (operation === "runs") return { runs: await journal.list(root) };
  if (operation === "run-detail") return journal.detail(root, String(payload.id || ""));
  if (operation === "run-export") return { path: await journal.export(root, String(payload.id || "")) };
  if (operation === "notifications") return { notifications, muted: notificationMuted, supported: Notification.isSupported() };
  if (operation === "notification-read") { notifications = notifications.map(item => item.id === payload.id || payload.all === true ? { ...item, read: true } : item); await atomicJson(notificationFile, notifications); return { notifications }; }
  if (operation === "notification-mute") { notificationMuted = payload.muted === true; await atomicJson(path.join(runtimeRoot,"notification-preferences.json"), {muted:notificationMuted}); return {muted:notificationMuted}; }
  if (operation === "snapshot") return gitSnapshot(root, payload.scope as DiffScope, String(payload.base || ""), String(payload.before || ""), String(payload.after || ""));
  if (operation === "patch") return gitPatch(root, payload as unknown as Parameters<typeof gitPatch>[1]);
  if (operation === "mutate") return gitMutate(root, payload as unknown as Parameters<typeof gitMutate>[1]);
  if (operation === "commit") return gitCommit(root, String(payload.message || ""), String(payload.version || ""));
  if (operation === "push-plan") return gitPushPlan(root, String(payload.remote || ""), String(payload.target || ""));
  if (operation === "push") return gitPush(root, payload.plan as PushPlan, payload.confirmed === true);
  if (operation === "fetch") return { output: await gitOutput(root, ["fetch", "--all", "--prune"]) };
  if (operation === "preview") return readPreview(root, String(payload.file || ""), Number(payload.offset || 0));
  if (operation === "list-directory") return listDirectory(root, String(payload.directory || "."));
  if (operation === "read-file") return readEditorFile(root, String(payload.file || ""));
  if (operation === "save-file") {
    if (coordinator.busy(root)) throw new Error("Wait for the active model run before saving this file.");
    if (typeof payload.text !== "string") throw new Error("Text content is required.");
    return saveEditorFile(root, String(payload.file || ""), payload.text, String(payload.version || ""));
  }
  if (operation === "open-editor") { const preview = await readPreview(root, String(payload.file || "")); return { error: await shell.openPath(preview.path) }; }
  if (operation === "reviews" || operation === "save-reviews") {
    const owner = createHash("sha256").update(String(payload.sessionId || "new")).digest("hex");
    const directory = path.join(root, ".reverie", "desktop", "reviews"); const file = path.join(directory, `${owner}.json`);
    if (operation === "reviews") { try { return { reviews: JSON.parse(await readFile(file, "utf8")) }; } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return { reviews: [] }; throw error; } }
    if (!Array.isArray(payload.reviews)) throw new Error("Invalid review records.");
    awaitDirectory(directory); await writeFile(file, JSON.stringify(payload.reviews, null, 2), "utf8"); return { saved: true };
  }
  throw new Error("Unknown workspace operation.");
});
ipcMain.handle("desktop:git-switch-branch", async (_event, name: unknown, remote: unknown) => {
  if (!bridge || typeof name !== "string" || typeof remote !== "boolean") throw new Error("Invalid branch selection.");
  if (coordinator.list().some(item=>samePath(item.projectRoot,bridge!.getProjectRoot()))) throw new Error("Wait for the active run before switching branches.");
  if (terminals.active(bridge.getProjectRoot()).length) throw new Error("End the workspace terminals before switching branches.");
  return switchGitBranch(bridge.getProjectRoot(), name, remote);
});
ipcMain.handle("desktop:git-create-branch", async (_event, name: unknown) => {
  if (!bridge || typeof name !== "string") throw new Error("Invalid branch name.");
  if (coordinator.list().some(item=>samePath(item.projectRoot,bridge!.getProjectRoot()))) throw new Error("Wait for the active run before switching branches.");
  if (terminals.active(bridge.getProjectRoot()).length) throw new Error("End the workspace terminals before switching branches.");
  return createGitBranch(bridge.getProjectRoot(), name);
});

ipcMain.handle("desktop:select-core-data", async () => {
  if (!mainWindow || !bridge) return null;
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, "选择 Reverie CLI 数据目录", "Choose the Reverie CLI data folder"),
    defaultPath: bridge.getCoreAppRoot(),
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  let coreAppRoot = path.resolve(result.filePaths[0]);
  if (path.basename(coreAppRoot).toLowerCase() === ".reverie") coreAppRoot = path.dirname(coreAppRoot);
  await bridge.stop("Core data directory changed.");
  bridge.setCoreAppRoot(coreAppRoot);
  await updateDesktopSettings({ coreAppRoot });
  await bridge.start();
  return coreAppRoot;
});

ipcMain.handle("desktop:paths", async () => ({
  projectRoot: bridge?.getProjectRoot() ?? "",
  kernelPath: activeKernelPath,
  coreAppRoot: bridge?.getCoreAppRoot() ?? defaultCoreAppRoot(),
  runtimeRoot,
  desktopExecutable: process.execPath,
  desktopBuild: await readJson(path.join(app.getAppPath(), "dist-electron", "reverie-build.json"), null),
}));

ipcMain.handle("desktop:appearance", () => appearancePayload());

ipcMain.handle("desktop:set-appearance", async (_event, value: unknown, owner?: unknown) => {
  const theme = normalizeThemePreference(value);
  const updated = await mutateDesktopSettings((settings) => {
    const ui = normalizeUiPreferences(settings.ui);
    const target = owner === undefined ? ui.uiVariant : normalizeUiVariant(owner);
    return target === "liquid-glass"
      ? { ...settings, ui: { ...ui, liquidGlassAppearance: { ...ui.liquidGlassAppearance, theme } } }
      : { ...settings, theme };
  });
  nativeTheme.themeSource = uiThemePreference(normalizeUiPreferences(updated.ui), updated.theme);
  applyWindowAppearance();
  const appearance = appearancePayload();
  mainWindow?.webContents.send("desktop:appearance-changed", appearance);
  return appearance;
});

ipcMain.handle("desktop:ui-preferences", async () => {
  const settings = await readDesktopSettings();
  return uiPreferencesPayload(normalizeUiPreferences(settings.ui));
});

ipcMain.handle("desktop:set-ui-preferences", async (_event, patch: JsonRecord, owner?: unknown) => {
  const safePatch = { ...(patch ?? {}) };
  delete safePatch.backgroundPath;
  delete safePatch.backgroundUrl;
  delete safePatch.backgroundName;
  delete safePatch.liquidGlassAppearance;
  const updated = await mutateDesktopSettings((settings) => ({
    ...settings,
    ui: mergeUiPreferences(settings.ui, safePatch, owner === undefined ? undefined : normalizeUiVariant(owner)),
  }));
  const ui = normalizeUiPreferences(updated.ui);
  if (Object.hasOwn(safePatch, "uiVariant")) {
    nativeTheme.themeSource = uiThemePreference(ui, updated.theme);
    applyWindowAppearance();
    mainWindow?.webContents.send("desktop:appearance-changed", appearancePayload());
  }
  // Pane controls already reconcile their own optimistic, sequenced requests.
  // A full snapshot here can roll back a newer pane request while saving a view.
  const passive: JsonRecord = {};
  if (Object.hasOwn(safePatch, "language")) passive.language = ui.language;
  if (Object.hasOwn(safePatch, "viewPresentations")) passive.viewPresentations = ui.viewPresentations;
  if (Object.keys(passive).length) mainWindow?.webContents.send("core:event", { type: "desktop.preferences", preferences: passive });
  return uiPreferencesPayload(ui);
});

ipcMain.handle("desktop:select-background", async () => {
  if (!mainWindow) return null;
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, "选择 Reverie 背景图片", "Choose a Reverie background image"),
    properties: ["openFile"],
    filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp", "bmp"] }],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  const source = path.resolve(result.filePaths[0]);
  const extension = path.extname(source).toLowerCase() || ".png";
  const owner = preferences.uiVariant;
  const destination = path.join(runtimePaths.backgrounds, `workspace-background-${owner}-${Date.now()}${extension}`);
  if (source.toLowerCase() !== destination.toLowerCase()) {
    await copyFile(source, destination);
  }
  let previousBackgroundPath = "";
  const updated = await mutateDesktopSettings((settings) => {
    const current = normalizeUiPreferences(settings.ui);
    const appearance = effectiveUiPreferences({ ...current, uiVariant: owner });
    previousBackgroundPath = appearance.backgroundPath;
    return {
      ...settings,
      ui: mergeUiPreferences(current, {
        backgroundPreset: "custom",
        backgroundPath: destination,
        backgroundOpacity: appearance.backgroundOpacity < 0.72 ? 0.9 : appearance.backgroundOpacity,
      }, owner),
    };
  });
  if (
    previousBackgroundPath
    && path.dirname(previousBackgroundPath).toLowerCase() === runtimePaths.backgrounds.toLowerCase()
    && previousBackgroundPath.toLowerCase() !== destination.toLowerCase()
    && ![updated.ui?.backgroundPath, updated.ui?.liquidGlassAppearance.backgroundPath].includes(previousBackgroundPath)
  ) {
    await rm(previousBackgroundPath, { force: true }).catch(() => undefined);
  }
  const ui = normalizeUiPreferences(updated.ui);
  return uiPreferencesPayload(ui);
});

ipcMain.handle("desktop:clear-background", async (_event, owner?: unknown) => {
  let backgroundPath = "";
  const updated = await mutateDesktopSettings((settings) => {
    const current = normalizeUiPreferences(settings.ui);
    const target = owner === undefined ? current.uiVariant : normalizeUiVariant(owner);
    backgroundPath = effectiveUiPreferences({ ...current, uiVariant: target }).backgroundPath;
    return { ...settings, ui: mergeUiPreferences(current, { backgroundPreset: target === "liquid-glass" ? "liquid-glass" : "none", backgroundPath: "" }, target) };
  });
  if (
    backgroundPath
    && path.dirname(backgroundPath).toLowerCase() === runtimePaths.backgrounds.toLowerCase()
    && ![updated.ui?.backgroundPath, updated.ui?.liquidGlassAppearance.backgroundPath].includes(backgroundPath)
  ) {
    await rm(backgroundPath, { force: true }).catch(() => undefined);
  }
  const ui = normalizeUiPreferences(updated.ui);
  return uiPreferencesPayload(ui);
});

ipcMain.handle("desktop:reveal", async (_event, target: string) => {
  if (!bridge) return false;
  const resolved = path.resolve(String(target ?? ""));
  const allowedRoots = [bridge.getProjectRoot(), bridge.getCoreAppRoot(), runtimeRoot, path.dirname(activeKernelPath)].map((item) =>
    path.resolve(item),
  );
  if (!allowedRoots.some((root) => pathIsWithin(resolved, root))) return false;
  shell.showItemInFolder(resolved);
  return true;
});

ipcMain.handle("desktop:open-external", async (_event, url: string) => {
  if (!/^https?:\/\//i.test(String(url ?? ""))) return false;
  await shell.openExternal(url);
  return true;
});

const RATS_PROVIDER_PICKERS: Record<string, { chinese: string; english: string; filterName: string }> = {
  // Only the compiled-in providers get bespoke picker copy. User-declared
  // providers are named by the settings file, which this process does not read,
  // so they fall through to the generic picker below.
  "reverie.engine": {
    chinese: "选择 Reverie Engine 可执行文件",
    english: "Choose a Reverie Engine executable",
    filterName: "Reverie Engine",
  },
};

/** A dotted, lowercase provider id — the shape the core's validator accepts. */
const RATS_PROVIDER_ID_PATTERN = /^[a-z][a-z0-9]{1,31}(\.[a-z0-9][a-z0-9_-]{0,31}){1,3}$/;

async function selectRatsProvider(providerId: string): Promise<string | null> {
  if (!mainWindow) return null;
  const normalized = String(providerId ?? "").trim();
  // The core owns which provider ids exist: it holds the compiled-in allowlist
  // *and* the user's definitions, and this process reads neither. Refusing an
  // id here on the strength of a hardcoded map would make a provider the user
  // legitimately defined unregisterable from the GUI, so the check is on shape
  // only. Naming a nonexistent provider fails in the core, where it should.
  if (!RATS_PROVIDER_ID_PATTERN.test(normalized)) {
    throw new Error(`Unsupported RATS provider: ${normalized || "unknown"}`);
  }
  const picker = RATS_PROVIDER_PICKERS[normalized] ?? {
    chinese: `选择 ${normalized} 的可执行文件`,
    english: `Choose an executable for ${normalized}`,
    filterName: normalized,
  };
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, picker.chinese, picker.english),
    defaultPath: executableHome,
    properties: ["openFile"],
    filters: process.platform === "win32"
      ? [{ name: picker.filterName, extensions: ["exe"] }]
      : undefined,
  });
  if (result.canceled || !result.filePaths[0]) return null;
  return path.resolve(result.filePaths[0]);
}

ipcMain.handle("desktop:select-rats-provider", async (_event, providerId: unknown) =>
  selectRatsProvider(String(providerId ?? "")),
);

// Deprecated alias retained for packaged renderer compatibility.
ipcMain.handle("desktop:select-rats-engine", async () => selectRatsProvider("reverie.engine"));

async function runTuiFromDesktop(settings: DesktopSettings): Promise<void> {
  const executable = await selectKernelPath(false);
  const projectRoot = launchOptions.projectRoot && isWorkspaceDirectory(launchOptions.projectRoot)
    ? launchOptions.projectRoot
    : settings.projectRoot && isWorkspaceDirectory(settings.projectRoot)
      ? settings.projectRoot
      : process.cwd();
  await new Promise<void>((resolve, reject) => {
    const child = spawn(executable, [projectRoot, ...launchOptions.tuiArgs], {
      cwd: projectRoot,
      windowsHide: false,
      stdio: "inherit",
      env: {
        ...process.env,
        REVERIE_APP_ROOT: settings.coreAppRoot && existsSync(settings.coreAppRoot)
          ? path.resolve(settings.coreAppRoot)
          : defaultCoreAppRoot(),
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      app.exit(code ?? 1);
      resolve();
    });
  });
}

app.whenReady().then(async () => {
  if (!ownsDesktopInstance) return;
  // Windows attributes a toast to whatever AppUserModelID raised it; without this
  // the notification reads as "electron.app.…" instead of Reverie. Harmless on
  // macOS/Linux, which ignore the id.
  app.setAppUserModelId("Reverie");
  if (launchOptions.isolationProbe) {
    // Verification entry point: a dedicated window and session partition, never the user's.
    const code = await runIsolationProbe({
      uiRoot,
      runtimeRoot,
      reportPath: launchOptions.isolationProbeReport,
    }).catch(error => {
      log(`Isolation probe failed: ${error instanceof Error ? error.stack ?? error.message : String(error)}`);
      process.stdout.write(`isolation probe crashed: ${error instanceof Error ? error.message : String(error)}\n`);
      return 2;
    });
    app.exit(code);
    return;
  }
  const settings = await readDesktopSettings();
  const startupMode = resolveDesktopStartupMode(
    launchOptions,
    normalizeUiPreferences(settings.ui).startupMode,
  );
  notifications = await readJson(notificationFile, []);
  notificationMuted = (await readJson(path.join(runtimeRoot,"notification-preferences.json"), {muted:false})).muted;
  if (startupMode === "tui") {
    await runTuiFromDesktop(settings);
    return;
  }
  await createWindow();
  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) await createWindow();
    else if (mainWindow) showWindow(mainWindow);
  });
});

nativeTheme.on("updated", () => {
  applyWindowAppearance();
  mainWindow?.webContents.send("desktop:appearance-changed", appearancePayload());
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

let coreStoppedForQuit = false;
app.on("before-quit", (event) => {
  quitRequested = true;
  if (coreStoppedForQuit) return;
  event.preventDefault();
  const activeBridge = bridge;
  bridge = null;
  for (const entry of coordinator.list()) if (entry.state === "queued") coordinator.cancelQueued(entry.projectRoot, entry.sessionId);
  void Promise.all([activeBridge?.stop("Application is closing."), terminals.closeAll(), workerPool.close()]).finally(() => {
    coreStoppedForQuit = true;
    app.quit();
  });
});

app.on("will-quit", () => {
  windowTray?.destroy();
  windowTray = null;
});
