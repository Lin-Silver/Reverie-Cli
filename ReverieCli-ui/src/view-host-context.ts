import { VIEW_DISPLAY_MODES, type ViewDisplayMode } from "./view-presentation-context";

const variables: Record<string, string> = {
  "--color-background-primary": "--bg", "--color-background-secondary": "--panel",
  "--color-text-primary": "--text", "--color-text-secondary": "--text-2",
  "--color-text-tertiary": "--muted", "--color-border-primary": "--border",
  "--color-border-secondary": "--border-soft", "--color-text-danger": "--red",
  "--font-mono": "--font-mono",
};

/** Public appearance only. Private view state and host credentials never enter context. */
export function viewHostContext(frame: HTMLIFrameElement, locale: string, mode: ViewDisplayMode) {
  const style = getComputedStyle(document.documentElement);
  const rect = frame.getBoundingClientRect();
  return {
    theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
    locale, displayMode: mode, availableDisplayModes: [...VIEW_DISPLAY_MODES], platform: "desktop",
    containerDimensions: { width: Math.round(rect.width), height: Math.round(rect.height) },
    styles: { variables: { ...Object.fromEntries(Object.entries(variables).map(([key, value]) => [key, style.getPropertyValue(value).trim()]).filter(([, value]) => value)), "--font-sans": style.fontFamily } },
    // ext-apps 2.0.3 permits namespaced host-context extensions; it defines no reduced-motion field.
    reverie: { reducedMotion: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false },
  };
}
