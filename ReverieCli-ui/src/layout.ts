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
