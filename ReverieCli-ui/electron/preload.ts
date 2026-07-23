import { contextBridge, ipcRenderer } from "electron";
import type { CoreActionName } from "./core-actions";

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
  cancel: () => ipcRenderer.invoke("core:cancel") as Promise<void>,
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
  selectAttachment: () =>
    ipcRenderer.invoke("desktop:select-attachment") as Promise<{
      name: string;
      relativePath: string;
      size: number;
    } | null>,
  selectCoreData: () =>
    ipcRenderer.invoke("desktop:select-core-data") as Promise<string | null>,
  paths: () =>
    ipcRenderer.invoke("desktop:paths") as Promise<{
      projectRoot: string;
      kernelPath: string;
      coreAppRoot: string;
      runtimeRoot: string;
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
  platform: process.platform,
  versions: process.versions,
});
