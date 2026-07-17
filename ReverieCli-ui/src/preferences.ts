export type AccentPreference = "violet" | "blue" | "teal" | "rose" | "amber";
export type FontSizePreference = "compact" | "comfortable" | "large";
export type MessageWidthPreference = "focused" | "balanced" | "wide";
export type BackgroundPreset = "none" | "aurora-archive" | "moss-library" | "ember-manuscript" | "custom";

export interface UiPreferences {
  accent: AccentPreference;
  fontSize: FontSizePreference;
  messageWidth: MessageWidthPreference;
  backgroundPreset: BackgroundPreset;
  backgroundUrl: string;
  backgroundName: string;
  backgroundOpacity: number;
  backgroundBlur: number;
  backgroundDim: number;
  showReasoning: boolean;
  expandReasoning: boolean;
  showToolCalls: boolean;
  showToolResults: boolean;
  expandToolResults: boolean;
  showLiveActivity: boolean;
  recentProjects: string[];
  archivedSessions: Record<string, string[]>;
}

export const DEFAULT_UI_PREFERENCES: UiPreferences = {
  accent: "violet",
  fontSize: "comfortable",
  messageWidth: "balanced",
  backgroundPreset: "none",
  backgroundUrl: "",
  backgroundName: "",
  backgroundOpacity: 0.9,
  backgroundBlur: 0,
  backgroundDim: 0.12,
  showReasoning: false,
  expandReasoning: true,
  showToolCalls: true,
  showToolResults: false,
  expandToolResults: false,
  showLiveActivity: true,
  recentProjects: [],
  archivedSessions: {},
};

function enumValue<T extends string>(value: unknown, values: readonly T[], fallback: T): T {
  return values.includes(value as T) ? value as T : fallback;
}

function clamp(value: unknown, minimum: number, maximum: number, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))];
}

export function normalizeUiPreferences(value: unknown): UiPreferences {
  const source = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  const rawArchives = source.archivedSessions && typeof source.archivedSessions === "object" && !Array.isArray(source.archivedSessions)
    ? source.archivedSessions as Record<string, unknown>
    : {};
  return {
    accent: enumValue(source.accent, ["violet", "blue", "teal", "rose", "amber"] as const, DEFAULT_UI_PREFERENCES.accent),
    fontSize: enumValue(source.fontSize, ["compact", "comfortable", "large"] as const, DEFAULT_UI_PREFERENCES.fontSize),
    messageWidth: enumValue(source.messageWidth, ["focused", "balanced", "wide"] as const, DEFAULT_UI_PREFERENCES.messageWidth),
    backgroundPreset: enumValue(
      source.backgroundPreset,
      ["none", "aurora-archive", "moss-library", "ember-manuscript", "custom"] as const,
      source.backgroundUrl ? "custom" : DEFAULT_UI_PREFERENCES.backgroundPreset,
    ),
    backgroundUrl: String(source.backgroundUrl ?? ""),
    backgroundName: String(source.backgroundName ?? ""),
    backgroundOpacity: clamp(source.backgroundOpacity, 0, 1, DEFAULT_UI_PREFERENCES.backgroundOpacity),
    backgroundBlur: clamp(source.backgroundBlur, 0, 24, DEFAULT_UI_PREFERENCES.backgroundBlur),
    backgroundDim: clamp(source.backgroundDim, 0, 0.8, DEFAULT_UI_PREFERENCES.backgroundDim),
    showReasoning: source.showReasoning === undefined ? DEFAULT_UI_PREFERENCES.showReasoning : Boolean(source.showReasoning),
    expandReasoning: source.expandReasoning === undefined ? DEFAULT_UI_PREFERENCES.expandReasoning : Boolean(source.expandReasoning),
    showToolCalls: source.showToolCalls === undefined ? DEFAULT_UI_PREFERENCES.showToolCalls : Boolean(source.showToolCalls),
    showToolResults: source.showToolResults === undefined ? DEFAULT_UI_PREFERENCES.showToolResults : Boolean(source.showToolResults),
    expandToolResults: source.expandToolResults === undefined ? DEFAULT_UI_PREFERENCES.expandToolResults : Boolean(source.expandToolResults),
    showLiveActivity: source.showLiveActivity === undefined ? DEFAULT_UI_PREFERENCES.showLiveActivity : Boolean(source.showLiveActivity),
    recentProjects: stringList(source.recentProjects).slice(0, 12),
    archivedSessions: Object.fromEntries(
      Object.entries(rawArchives).map(([project, sessions]) => [project, stringList(sessions)]),
    ),
  };
}

export function backgroundPresetUrl(preset: BackgroundPreset): string {
  if (preset === "none" || preset === "custom") return "";
  const baseUrl = typeof document === "undefined" ? "file:///" : document.baseURI;
  return new URL(`backgrounds/${preset}.webp`, baseUrl).href;
}

export function effectiveBackgroundUrl(preferences: UiPreferences): string {
  return preferences.backgroundPreset === "custom"
    ? preferences.backgroundUrl
    : backgroundPresetUrl(preferences.backgroundPreset);
}

export function applyUiPreferences(preferences: UiPreferences): void {
  const root = document.documentElement;
  const backgroundUrl = effectiveBackgroundUrl(preferences);
  root.dataset.accent = preferences.accent;
  root.dataset.fontSize = preferences.fontSize;
  root.dataset.messageWidth = preferences.messageWidth;
  root.style.setProperty("--background-opacity", String(preferences.backgroundOpacity));
  root.style.setProperty("--background-blur", `${preferences.backgroundBlur}px`);
  root.style.setProperty("--background-dim", String(preferences.backgroundDim));
  root.style.setProperty(
    "--workspace-background-image",
    backgroundUrl ? `url("${backgroundUrl.replaceAll('"', "%22")}")` : "none",
  );
  root.classList.toggle("has-workspace-background", Boolean(backgroundUrl));
}
