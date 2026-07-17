/// <reference types="vite/client" />

type JsonRecord = Record<string, unknown>;

interface ReverieDesktopApi {
  request(action: string, payload?: JsonRecord): Promise<JsonRecord>;
  cancel(): Promise<void>;
  onEvent(listener: (message: JsonRecord) => void): () => void;
  selectWorkspace(): Promise<string | null>;
  switchWorkspace(projectRoot: string): Promise<string | null>;
  deleteWorkspace(projectRoot: string): Promise<{ projectRoot: string; deletedSessions: number; preferences: JsonRecord } | null>;
  selectAttachment(): Promise<{ name: string; relativePath: string; size: number } | null>;
  selectCoreData(): Promise<string | null>;
  paths(): Promise<{ projectRoot: string; kernelPath: string; coreAppRoot: string; runtimeRoot: string }>;
  appearance(): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  setAppearance(theme: "system" | "dark" | "light"): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  onAppearance(listener: (appearance: { theme: "system" | "dark" | "light"; resolved: "dark" | "light" }) => void): () => void;
  uiPreferences(): Promise<JsonRecord>;
  setUiPreferences(patch: JsonRecord): Promise<JsonRecord>;
  selectBackground(): Promise<JsonRecord | null>;
  clearBackground(): Promise<JsonRecord>;
  reveal(target: string): Promise<boolean>;
  openExternal(url: string): Promise<boolean>;
  platform: string;
  versions: Record<string, string>;
}

declare global {
  interface Window {
    reverie: ReverieDesktopApi;
  }
}

export {};
