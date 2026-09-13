export type ThemePreference = "system" | "dark" | "light";

export function normalizeThemePreference(value: unknown): ThemePreference {
  return value === "dark" || value === "light" || value === "system" ? value : "system";
}

export function windowAppearance(dark: boolean): {
  backgroundColor: string;
  overlayColor: string;
  symbolColor: string;
} {
  return dark
    ? { backgroundColor: "#0b0d12", overlayColor: "#0b0d12", symbolColor: "#aeb4bf" }
    : { backgroundColor: "#f6f7f9", overlayColor: "#f6f7f9", symbolColor: "#5f6671" };
}
