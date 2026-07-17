export type ThemePreference = "system" | "dark" | "light";
export type ResolvedTheme = "dark" | "light";

export const THEME_STORAGE_KEY = "reverie.theme";

export function normalizeTheme(value: unknown): ThemePreference {
  return value === "dark" || value === "light" || value === "system" ? value : "system";
}

export function resolveTheme(theme: ThemePreference, systemDark: boolean): ResolvedTheme {
  return theme === "system" ? (systemDark ? "dark" : "light") : theme;
}

export function applyTheme(theme: ThemePreference, systemDark: boolean): ResolvedTheme {
  const resolved = resolveTheme(theme, systemDark);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  return resolved;
}
