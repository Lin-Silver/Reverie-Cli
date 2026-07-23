import { app, BrowserWindow, dialog, ipcMain, nativeTheme, shell } from "electron";
import { assertCoreAction, assertCoreResponse, normalizeCorePayload } from "./core-actions";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { appendFile, copyFile, readFile, rm, stat, writeFile } from "node:fs/promises";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
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
import {
  activateWorkspaceInPlace,
  isWorkspaceDirectory,
  pathIsWithin,
  samePath,
} from "./workspace-lifecycle";
import {
  mergeUiPreferences,
  normalizeUiPreferences,
  type StoredUiPreferences,
} from "./preferences";

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
    return JSON.parse(await readFile(runtimePaths.settings, "utf8")) as DesktopSettings;
  } catch {
    return {};
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

function safeAttachmentName(filePath: string): string {
  const parsed = path.parse(filePath);
  const stem = parsed.name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-").replace(/\s+/g, " ").trim() || "attachment";
  const extension = parsed.ext.replace(/[^.A-Za-z0-9_-]/g, "");
  return `${Date.now()}-${stem}${extension}`;
}

function uiPreferencesPayload(preferences: StoredUiPreferences): JsonRecord {
  const backgroundPath = preferences.backgroundPath && existsSync(preferences.backgroundPath)
    ? preferences.backgroundPath
    : "";
  const { backgroundPath: _storedPath, ...rest } = preferences;
  return {
    ...rest,
    backgroundUrl: preferences.backgroundPreset === "custom" && backgroundPath
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
      height: 46,
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
    }
  >();

  constructor(
    private projectRoot: string,
    private coreAppRoot: string,
    private readonly executablePath: string,
    private readonly sendEvent: (message: JsonRecord) => void,
  ) {}

  setProjectRoot(projectRoot: string): void {
    this.projectRoot = path.resolve(projectRoot);
  }

  getProjectRoot(): string {
    return this.projectRoot;
  }

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
    const timeoutMs = action === "runPrompt" || action === "indexWorkspace"
      ? 0
      : action === "refreshModelSources"
        ? 120_000
        : action === "getSession"
          ? 15_000
          : 60_000;
    return new Promise<JsonRecord>((resolve, reject) => {
      const timer = timeoutMs > 0
        ? setTimeout(() => {
            if (!this.pending.delete(id)) return;
            reject(new Error(`Reverie core request timed out: ${action}`));
          }, timeoutMs)
        : null;
      this.pending.set(id, { resolve, reject, timer });
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
let bridge: CoreBridge | null = null;

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
    if (mainWindow?.isMinimized()) mainWindow.restore();
    mainWindow?.show();
    mainWindow?.focus();
  });
}

function localizedUiText(language: StoredUiPreferences["language"], chinese: string, english: string): string {
  return language === "en-US" ? english : chinese;
}

async function activateWorkspace(projectRoot: string): Promise<string> {
  if (!bridge) throw new Error("Reverie core bridge is not initialized.");
  const resolved = await activateWorkspaceInPlace(bridge, projectRoot, async (nextProjectRoot) => {
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
  nativeTheme.themeSource = normalizeThemePreference(settings.theme);
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
      height: 46,
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
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const current = mainWindow?.webContents.getURL() ?? "";
    if (url !== current) {
      event.preventDefault();
      if (/^https?:\/\//i.test(url)) void shell.openExternal(url);
    }
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
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
  const action = assertCoreAction(rawAction);
  const payload = normalizeCorePayload(rawPayload);
  const response = await bridge.request(action, payload);
  if (action === "initialize") {
    void log(`Desktop initialized in ${Date.now() - desktopStartedAt} ms`);
  }
  return assertCoreResponse(action, response);
});

ipcMain.handle("core:cancel", async () => {
  if (!bridge) return;
  await bridge.restart();
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

ipcMain.handle("desktop:select-attachment", async () => {
  if (!mainWindow || !bridge) return null;
  const projectRoot = path.resolve(bridge.getProjectRoot());
  const preferences = normalizeUiPreferences((await readDesktopSettings()).ui);
  const result = await dialog.showOpenDialog(mainWindow, {
    title: localizedUiText(preferences.language, "选择要提供给 Reverie 的文件", "Choose a file to provide to Reverie"),
    defaultPath: projectRoot,
    properties: ["openFile"],
  });
  if (result.canceled || !result.filePaths[0]) return null;
  const sourcePath = path.resolve(result.filePaths[0]);
  const destinationDirectory = attachmentDirectory(projectRoot);
  awaitDirectory(destinationDirectory);
  const destinationPath = path.join(destinationDirectory, safeAttachmentName(sourcePath));
  await copyFile(sourcePath, destinationPath);
  const info = await stat(destinationPath);
  return {
    name: path.basename(sourcePath),
    relativePath: path.relative(projectRoot, destinationPath).replaceAll("\\", "/"),
    size: info.size,
  };
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

ipcMain.handle("desktop:paths", () => ({
  projectRoot: bridge?.getProjectRoot() ?? "",
  kernelPath: activeKernelPath,
  coreAppRoot: bridge?.getCoreAppRoot() ?? defaultCoreAppRoot(),
  runtimeRoot,
}));

ipcMain.handle("desktop:appearance", () => appearancePayload());

ipcMain.handle("desktop:set-appearance", async (_event, value: unknown) => {
  const theme = normalizeThemePreference(value);
  nativeTheme.themeSource = theme;
  await updateDesktopSettings({ theme });
  applyWindowAppearance();
  const appearance = appearancePayload();
  mainWindow?.webContents.send("desktop:appearance-changed", appearance);
  return appearance;
});

ipcMain.handle("desktop:ui-preferences", async () => {
  const settings = await readDesktopSettings();
  return uiPreferencesPayload(normalizeUiPreferences(settings.ui));
});

ipcMain.handle("desktop:set-ui-preferences", async (_event, patch: JsonRecord) => {
  const safePatch = { ...(patch ?? {}) };
  delete safePatch.backgroundPath;
  delete safePatch.backgroundUrl;
  delete safePatch.backgroundName;
  const updated = await mutateDesktopSettings((settings) => ({
    ...settings,
    ui: mergeUiPreferences(settings.ui, safePatch),
  }));
  const ui = normalizeUiPreferences(updated.ui);
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
  const destination = path.join(runtimePaths.backgrounds, `workspace-background${extension}`);
  if (source.toLowerCase() !== destination.toLowerCase()) {
    await copyFile(source, destination);
  }
  let previousBackgroundPath = "";
  const updated = await mutateDesktopSettings((settings) => {
    const current = normalizeUiPreferences(settings.ui);
    previousBackgroundPath = current.backgroundPath;
    return {
      ...settings,
      ui: {
        ...current,
        backgroundPreset: "custom",
        backgroundPath: destination,
        backgroundOpacity: current.backgroundOpacity < 0.72 ? 0.9 : current.backgroundOpacity,
      },
    };
  });
  if (
    previousBackgroundPath
    && path.dirname(previousBackgroundPath).toLowerCase() === runtimePaths.backgrounds.toLowerCase()
    && previousBackgroundPath.toLowerCase() !== destination.toLowerCase()
  ) {
    await rm(previousBackgroundPath, { force: true }).catch(() => undefined);
  }
  const ui = normalizeUiPreferences(updated.ui);
  return uiPreferencesPayload(ui);
});

ipcMain.handle("desktop:clear-background", async () => {
  let backgroundPath = "";
  const updated = await mutateDesktopSettings((settings) => {
    const current = normalizeUiPreferences(settings.ui);
    backgroundPath = current.backgroundPath;
    return { ...settings, ui: { ...current, backgroundPreset: "none", backgroundPath: "" } };
  });
  if (
    backgroundPath
    && path.dirname(backgroundPath).toLowerCase() === runtimePaths.backgrounds.toLowerCase()
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
  const settings = await readDesktopSettings();
  const startupMode = resolveDesktopStartupMode(
    launchOptions,
    normalizeUiPreferences(settings.ui).startupMode,
  );
  if (startupMode === "tui") {
    await runTuiFromDesktop(settings);
    return;
  }
  await createWindow();
  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) await createWindow();
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
  if (coreStoppedForQuit || !bridge) return;
  event.preventDefault();
  const activeBridge = bridge;
  bridge = null;
  void activeBridge.stop("Application is closing.").finally(() => {
    coreStoppedForQuit = true;
    app.quit();
  });
});
