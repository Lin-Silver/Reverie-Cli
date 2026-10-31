/// <reference types="vite/client" />

import type { CoreAction, CorePayload, CoreResponse } from "./core-protocol";
import type { DesktopPaths } from "./types";
import type { UiPreferences } from "./preferences";
import type { GitWorkspaceStatus } from "../electron/git-workspace";
import type { ComposerAttachment } from "../electron/attachments";
import type { FilePatch, GitSnapshot, Preview, PushPlan } from "../electron/workbench";

type JsonRecord = Record<string, unknown>;

interface ReverieDesktopApi {
  request<Action extends CoreAction>(action: Action, payload: CorePayload<Action>): Promise<CoreResponse<Action>>;
  cancel(owner?: {projectRoot:string;sessionId:string}): Promise<void>;
  notify(payload: { title: string; body: string }): Promise<void>;
  onEvent(listener: (message: JsonRecord) => void): () => void;
  selectWorkspace(): Promise<string | null>;
  switchWorkspace(projectRoot: string): Promise<string | null>;
  deleteWorkspace(projectRoot: string): Promise<{ projectRoot: string; deletedSessions: number; preferences: UiPreferences } | null>;
  selectAttachment(projectRoot?: string): Promise<ComposerAttachment | null>;
  importDroppedFiles(files: File[], projectRoot?: string): Promise<ComposerAttachment[]>;
  pasteImage(projectRoot: string): Promise<ComposerAttachment>;
  retryAttachment(projectRoot: string, item: ComposerAttachment, copy?: boolean): Promise<ComposerAttachment>;
  gitStatus(): Promise<GitWorkspaceStatus | null>;
  workbench(operation: string, payload?: JsonRecord): Promise<GitSnapshot | FilePatch | Preview | PushPlan | JsonRecord>;
  switchGitBranch(name: string, remote: boolean): Promise<GitWorkspaceStatus>;
  createGitBranch(name: string): Promise<GitWorkspaceStatus>;
  selectCoreData(): Promise<string | null>;
  paths(): Promise<DesktopPaths>;
  appearance(): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  setAppearance(theme: "system" | "dark" | "light", owner?: "classic" | "liquid-glass"): Promise<{ theme: "system" | "dark" | "light"; resolved: "dark" | "light" }>;
  onAppearance(listener: (appearance: { theme: "system" | "dark" | "light"; resolved: "dark" | "light" }) => void): () => void;
  uiPreferences(): Promise<UiPreferences>;
  setUiPreferences(patch: Partial<UiPreferences>, owner?: "classic" | "liquid-glass"): Promise<UiPreferences>;
  selectBackground(): Promise<UiPreferences | null>;
  clearBackground(owner?: "classic" | "liquid-glass"): Promise<UiPreferences>;
  reveal(target: string): Promise<boolean>;
  openExternal(url: string): Promise<boolean>;
  selectRatsProvider(providerId: string): Promise<string | null>;
  /** Deprecated compatibility alias for the original Engine-only picker. */
  selectRatsEngine(): Promise<string | null>;
  platform: string;
  versions: Record<string, string>;
}

declare global {
  interface Window {
    reverie: ReverieDesktopApi;
  }
}

export {};
