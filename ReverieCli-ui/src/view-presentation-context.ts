import { createContext, useContext } from "react";
import type { ViewSegment } from "./types";

import { VIEW_DISPLAY_MODES, type ViewDisplayMode, type ViewDisplayPreference } from "../electron/view-display-preferences";
export { VIEW_DISPLAY_MODES, type ViewDisplayMode } from "../electron/view-display-preferences";
export type ViewContent = { segment: ViewSegment; onFollowUp?: (text: string) => void };
export type ActiveView = { key: string; title: string; mode: Exclude<ViewDisplayMode, "inline"> };
type Presentation = {
  scope: string;
  persisted?: Record<string, ViewDisplayPreference>;
  active: ActiveView | null;
  fullscreenSlot: HTMLDivElement | null;
  pipSlot: HTMLDivElement | null;
  setFullscreenSlot: (slot: HTMLDivElement | null) => void;
  select: (key: string, title: string, mode: ViewDisplayMode) => void;
  forget: (key: string) => void;
  mountView?: (key: string, owner: object, anchor: HTMLDivElement, content: ViewContent) => void;
  unmountView?: (key: string, owner: object) => void;
};
const noop = () => {};
export const ViewPresentationContext = createContext<Presentation>({ scope: "", active: null, fullscreenSlot: null, pipSlot: null, setFullscreenSlot: noop, select: noop, forget: noop });
export const useViewPresentation = () => useContext(ViewPresentationContext);

const STORAGE_KEY = "reverie.view-presentation.v1";
type SavedPresentation = { mode?: ViewDisplayMode; expanded?: boolean; updatedAt?: number };
function savedPresentations(): Record<string, SavedPresentation> {
  try { const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {}; }
  catch { return {}; }
}
export function readViewPresentation(key: string, persisted?: SavedPresentation): ViewDisplayPreference {
  const local = savedPresentations()[key];
  const saved = !local || (persisted?.updatedAt ?? 0) > (local.updatedAt ?? 0) ? persisted : local;
  return { mode: VIEW_DISPLAY_MODES.includes(saved?.mode as ViewDisplayMode) ? saved!.mode as ViewDisplayMode : "inline", expanded: saved?.expanded !== false, updatedAt: saved?.updatedAt ?? 0 };
}
/** Host display preferences only: never HTML, application state, secrets or tool results. */
export function saveViewPresentation(key: string, patch: SavedPresentation, persisted?: SavedPresentation) {
  const next = { ...readViewPresentation(key, persisted), ...patch, updatedAt: Date.now() };
  try {
    const saved = savedPresentations();
    delete saved[key]; saved[key] = next;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(Object.entries(saved).slice(-200))));
  } catch { /* Browser storage is only a cache; host persistence remains available. */ }
  try {
    void window.reverie?.setUiPreferences?.({ viewPresentations: { [key]: next } })?.catch(() => {});
  } catch { /* A closing host can no longer persist appearance. */ }
}
