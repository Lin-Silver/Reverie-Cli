export const SIDEBAR_COLLAPSED_STORAGE_KEY = "reverie.layout.sidebar-collapsed";

export function normalizeSidebarCollapsed(value: string | null | undefined): boolean {
  return value === "true";
}
