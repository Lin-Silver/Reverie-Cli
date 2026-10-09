import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { CoreActionName } from "./core-actions";
import type { GitWorkspaceStatus } from "./git-workspace";
import type { ComposerAttachment } from "./attachments";
import type { FilePatch, GitSnapshot, Preview, PushPlan } from "./workbench";

type JsonRecord = Record<string, unknown>;
type EventListener = (message: JsonRecord) => void;
type UiPreferencesPayload = JsonRecord & {
  startupMode: "gui" | "tui";
  accent: "violet" | "blue" | "teal" | "rose" | "amber";
  fontSize: "compact" | "comfortable" | "large";
  messageWidth: "focused" | "balanced" | "wide";
  backgroundUrl: string;
  backgroundName: string;
};

contextBridge.exposeInMainWorld("reverie", {
  request: (action: CoreActionName, payload: JsonRecord = {}) =>
    ipcRenderer.invoke("core:request", action, payload) as Promise<JsonRecord>,
  cancel: (owner?: {projectRoot:string;sessionId:string}) => ipcRenderer.invoke("core:cancel", owner) as Promise<void>,
  notify: (payload: { title: string; body: string }) =>
    ipcRenderer.invoke("desktop:notify", payload) as Promise<void>,
  onEvent: (listener: EventListener) => {
    const wrapped = (_event: Electron.IpcRendererEvent, message: JsonRecord) => listener(message);
    ipcRenderer.on("core:event", wrapped);
    return () => ipcRenderer.removeListener("core:event", wrapped);
  },
  selectWorkspace: () =>
    ipcRenderer.invoke("desktop:select-workspace") as Promise<string | null>,
  switchWorkspace: (projectRoot: string) =>
    ipcRenderer.invoke("desktop:switch-workspace", projectRoot) as Promise<string | null>,
  deleteWorkspace: (projectRoot: string) =>
    ipcRenderer.invoke("desktop:delete-workspace", projectRoot) as Promise<{
      projectRoot: string;
      deletedSessions: number;
      preferences: UiPreferencesPayload;
    } | null>,
  selectAttachment: (projectRoot?: string) => ipcRenderer.invoke("desktop:select-attachment", projectRoot) as Promise<ComposerAttachment | null>,
  importDroppedFiles: (files: File[], projectRoot?: string) => ipcRenderer.invoke("desktop:import-dropped-files", files.map((file) => webUtils.getPathForFile(file)), projectRoot) as Promise<ComposerAttachment[]>,
  pasteImage: (projectRoot: string) => ipcRenderer.invoke("desktop:paste-image", projectRoot) as Promise<ComposerAttachment>,
  retryAttachment: (projectRoot: string, item: ComposerAttachment, copy = false) => ipcRenderer.invoke("desktop:retry-attachment", projectRoot, item, copy) as Promise<ComposerAttachment>,
  gitStatus: () => ipcRenderer.invoke("desktop:git-status") as Promise<GitWorkspaceStatus | null>,
  workbench: (operation: string, payload: JsonRecord = {}) => ipcRenderer.invoke("desktop:workbench", operation, payload) as Promise<GitSnapshot | FilePatch | Preview | PushPlan | JsonRecord>,
  switchGitBranch: (name: string, remote: boolean) =>
    ipcRenderer.invoke("desktop:git-switch-branch", name, remote) as Promise<GitWorkspaceStatus>,
  createGitBranch: (name: string) =>
    ipcRenderer.invoke("desktop:git-create-branch", name) as Promise<GitWorkspaceStatus>,
  selectCoreData: () =>
    ipcRenderer.invoke("desktop:select-core-data") as Promise<string | null>,
  paths: () =>
    ipcRenderer.invoke("desktop:paths") as Promise<{
      projectRoot: string;
      kernelPath: string;
      coreAppRoot: string;
      runtimeRoot: string;
      desktopExecutable?: string;
      desktopBuild?: {version:string;id:string;builtAt:string;platform:string;arch:string} | null;
    }>,
  appearance: () =>
    ipcRenderer.invoke("desktop:appearance") as Promise<{
      theme: "system" | "dark" | "light";
      resolved: "dark" | "light";
    }>,
  setAppearance: (theme: "system" | "dark" | "light") =>
    ipcRenderer.invoke("desktop:set-appearance", theme) as Promise<{
      theme: "system" | "dark" | "light";
      resolved: "dark" | "light";
    }>,
  onAppearance: (listener: (appearance: { theme: "system" | "dark" | "light"; resolved: "dark" | "light" }) => void) => {
    const wrapped = (
      _event: Electron.IpcRendererEvent,
      appearance: { theme: "system" | "dark" | "light"; resolved: "dark" | "light" },
    ) => listener(appearance);
    ipcRenderer.on("desktop:appearance-changed", wrapped);
    return () => ipcRenderer.removeListener("desktop:appearance-changed", wrapped);
  },
  uiPreferences: () =>
    ipcRenderer.invoke("desktop:ui-preferences") as Promise<UiPreferencesPayload>,
  setUiPreferences: (patch: JsonRecord) =>
    ipcRenderer.invoke("desktop:set-ui-preferences", patch) as Promise<UiPreferencesPayload>,
  selectBackground: () =>
    ipcRenderer.invoke("desktop:select-background") as Promise<UiPreferencesPayload | null>,
  clearBackground: () =>
    ipcRenderer.invoke("desktop:clear-background") as Promise<UiPreferencesPayload>,
  reveal: (target: string) => ipcRenderer.invoke("desktop:reveal", target) as Promise<boolean>,
  openExternal: (url: string) =>
    ipcRenderer.invoke("desktop:open-external", url) as Promise<boolean>,
  selectRatsProvider: (providerId: string) =>
    ipcRenderer.invoke("desktop:select-rats-provider", providerId) as Promise<string | null>,
  // Deprecated alias retained for packaged renderer compatibility.
  selectRatsEngine: () => ipcRenderer.invoke("desktop:select-rats-engine") as Promise<string | null>,
  platform: process.platform,
  versions: process.versions,
});
