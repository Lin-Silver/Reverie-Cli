export type UiLanguage = "zh-CN" | "en-US";
export type AccentPreference = "violet" | "blue" | "teal" | "rose" | "amber";
export type FontSizePreference = "compact" | "comfortable" | "large";
export type MessageWidthPreference = "focused" | "balanced" | "wide";
export type BackgroundPreset = "none" | "aurora-archive" | "moss-library" | "ember-manuscript" | "custom";

export interface StoredUiPreferences {
  language: UiLanguage;
  accent: AccentPreference;
  fontSize: FontSizePreference;
  messageWidth: MessageWidthPreference;
  backgroundPreset: BackgroundPreset;
  backgroundPath: string;
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

export const DEFAULT_UI_PREFERENCES: StoredUiPreferences = {
  language: "zh-CN",
  accent: "violet",
  fontSize: "comfortable",
  messageWidth: "balanced",
  backgroundPreset: "none",
  backgroundPath: "",
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

function archivedSessions(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([project, sessions]) => [project, stringList(sessions)])
      .filter(([project]) => Boolean(project)),
  );
}

export function normalizeUiPreferences(value: unknown): StoredUiPreferences {
  const source = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  return {
    language: enumValue(source.language, ["zh-CN", "en-US"] as const, DEFAULT_UI_PREFERENCES.language),
    accent: enumValue(source.accent, ["violet", "blue", "teal", "rose", "amber"] as const, DEFAULT_UI_PREFERENCES.accent),
    fontSize: enumValue(source.fontSize, ["compact", "comfortable", "large"] as const, DEFAULT_UI_PREFERENCES.fontSize),
    messageWidth: enumValue(source.messageWidth, ["focused", "balanced", "wide"] as const, DEFAULT_UI_PREFERENCES.messageWidth),
    backgroundPreset: enumValue(
      source.backgroundPreset,
      ["none", "aurora-archive", "moss-library", "ember-manuscript", "custom"] as const,
      source.backgroundPath ? "custom" : DEFAULT_UI_PREFERENCES.backgroundPreset,
    ),
    backgroundPath: String(source.backgroundPath ?? "").trim(),
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
    archivedSessions: archivedSessions(source.archivedSessions),
  };
}

export function mergeUiPreferences(current: unknown, patch: unknown): StoredUiPreferences {
  const base = normalizeUiPreferences(current);
  const update = patch && typeof patch === "object" && !Array.isArray(patch)
    ? patch as Record<string, unknown>
    : {};
  return normalizeUiPreferences({
    ...base,
    ...update,
    archivedSessions: update.archivedSessions ?? base.archivedSessions,
    recentProjects: update.recentProjects ?? base.recentProjects,
  });
}
