/// <reference types="vite/client" />

import type { CoreAction, CorePayload, CoreResponse } from "./core-protocol";
import type { UiPreferences } from "./preferences";

type JsonRecord = Record<string, unknown>;

interface ReverieDesktopApi {
  request<Action extends CoreAction>(action: Action, payload: CorePayload<Action>): Promise<CoreResponse<Action>>;
  cancel(): Promise<void>;
  onEvent(listener: (message: JsonRecord) => void): () => void;
  selectWorkspace(): Promise<string | null>;
  switchWorkspace(projectRoot: string): Promise<string | null>;
  deleteWorkspace(projectRoot: string): Promise<{ projectRoot: string; deletedSessions: number; preferences: UiPreferences } | null>;
  selectAttachment(): Promise<{ name: string; relativePath: string; size: number } | null>;
  selectCoreData(): Promise<string | null>;
  paths(): Promise<{ projectRoot: string; kernelPath: string; coreAppRoot: string; runtimeRoot: string }>;
  appearance(): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  setAppearance(theme: "system" | "dark" | "light"): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  onAppearance(listener: (appearance: { theme: "system" | "dark" | "light"; resolved: "dark" | "light" }) => void): () => void;
  uiPreferences(): Promise<UiPreferences>;
  setUiPreferences(patch: Partial<UiPreferences>): Promise<UiPreferences>;
  selectBackground(): Promise<UiPreferences | null>;
  clearBackground(): Promise<UiPreferences>;
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
