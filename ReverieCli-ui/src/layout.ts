export const SIDEBAR_COLLAPSED_STORAGE_KEY = "reverie.layout.sidebar-collapsed";
export const SIDEBAR_AUTO_COLLAPSE_QUERY = "(max-width: 1100px)";

export function normalizeSidebarCollapsed(value: string | null | undefined): boolean {
  return value === "true";
}

export function resolveSidebarCollapsed(
  preferenceCollapsed: boolean,
  compactViewport: boolean,
  viewportOverride: boolean | null,
): boolean {
  return viewportOverride ?? (preferenceCollapsed || compactViewport);
}

/**
 * Drag bounds for the two side panes.
 *
 * The same numbers live in `electron/preferences.ts`, which cannot import from
 * the renderer bundle: a width that survives the round-trip through the main
 * process has to be clamped identically on both sides, or the pane would snap
 * to a different size the moment the stored value came back.
 */
export const SIDEBAR_MIN_WIDTH = 208;
export const SIDEBAR_MAX_WIDTH = 460;
export const SIDEBAR_DEFAULT_WIDTH = 268;
export const INSPECTOR_MIN_WIDTH = 264;
export const INSPECTOR_MAX_WIDTH = 620;
export const INSPECTOR_DEFAULT_WIDTH = 316;

/** Space the centre column keeps for itself no matter where the handles are. */
export const MAIN_AREA_MIN_WIDTH = 420;

export function clampPaneWidth(value: number, minimum: number, maximum: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.round(Math.min(maximum, Math.max(minimum, value)));
}

export function clampSidebarWidth(value: number): number {
  return clampPaneWidth(value, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_DEFAULT_WIDTH);
}

export function clampInspectorWidth(value: number): number {
  return clampPaneWidth(value, INSPECTOR_MIN_WIDTH, INSPECTOR_MAX_WIDTH, INSPECTOR_DEFAULT_WIDTH);
}

/**
 * Widen the drag ceiling only as far as the window can actually afford.
 *
 * `available` is the shell width; `otherPane` is whatever the opposite pane is
 * currently occupying. Without this a wide drag on a narrow window would push
 * the conversation column to zero and the transcript would vanish.
 */
export function paneDragLimit(available: number, otherPane: number, maximum: number): number {
  if (!Number.isFinite(available) || available <= 0) return maximum;
  return Math.max(0, Math.min(maximum, available - otherPane - MAIN_AREA_MIN_WIDTH));
}
