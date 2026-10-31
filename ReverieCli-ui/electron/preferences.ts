import { normalizeViewDisplayPreferences, type ViewDisplayPreference } from "./view-display-preferences";
import { normalizeThemePreference, type ThemePreference } from "./appearance";
export type UiVariant = "classic" | "liquid-glass";
export type UiLanguage = "zh-CN" | "en-US";
export type StartupModePreference = "gui" | "tui";
export type AccentPreference = "violet" | "blue" | "teal" | "rose" | "amber";
export type FontSizePreference = "compact" | "comfortable" | "large";
export type MessageWidthPreference = "focused" | "balanced" | "wide";
export type BackgroundPreset = "none" | "aurora-archive" | "moss-library" | "ember-manuscript" | "liquid-glass" | "custom";

export interface LiquidGlassAppearance {
  theme: ThemePreference;
  accent: AccentPreference;
  backgroundPreset: BackgroundPreset;
  backgroundPath: string;
  backgroundOpacity: number;
  backgroundBlur: number;
  backgroundDim: number;
}

const GLASS_DEFAULTS: LiquidGlassAppearance = {
  theme: "system", accent: "violet", backgroundPreset: "liquid-glass",
  backgroundPath: "", backgroundOpacity: 1, backgroundBlur: 0, backgroundDim: 0,
};

export function normalizeUiVariant(value: unknown): UiVariant {
  return value === "liquid-glass" ? "liquid-glass" : "classic";
}

function normalizeGlassAppearance(value: unknown): LiquidGlassAppearance {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  return {
    theme: normalizeThemePreference(source.theme),
    accent: enumValue(source.accent, ["violet", "blue", "teal", "rose", "amber"], GLASS_DEFAULTS.accent),
    backgroundPreset: enumValue(source.backgroundPreset, ["none", "aurora-archive", "moss-library", "ember-manuscript", "liquid-glass", "custom"], GLASS_DEFAULTS.backgroundPreset),
    backgroundPath: String(source.backgroundPath ?? "").trim(),
    backgroundOpacity: clamp(source.backgroundOpacity, 0, 1, GLASS_DEFAULTS.backgroundOpacity),
    backgroundBlur: clamp(source.backgroundBlur, 0, 24, GLASS_DEFAULTS.backgroundBlur),
    backgroundDim: clamp(source.backgroundDim, 0, 0.8, GLASS_DEFAULTS.backgroundDim),
  };
}

export interface StoredUiPreferences {
  uiVariant: UiVariant;
  liquidGlassAppearance: LiquidGlassAppearance;
  language: UiLanguage;
  userDisplayName: string;
  userAvatarUrl: string;
  startupMode: StartupModePreference;
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
  rtpProviderDetails: boolean;
  inspectorOpen: boolean;
  sidebarWidth: number;
  inspectorWidth: number;
  recentProjects: string[];
  archivedSessions: Record<string, string[]>;
  viewPresentations: Record<string, ViewDisplayPreference>;
}

/**
 * Pane drag bounds, mirrored from `src/layout.ts`.
 *
 * The main process cannot import the renderer bundle, and a width clamped to a
 * different range here than there would snap the pane back the moment the
 * stored value returned to the renderer. Keep the two lists in step.
 */
const SIDEBAR_MIN_WIDTH = 208;
const SIDEBAR_MAX_WIDTH = 460;
const INSPECTOR_MIN_WIDTH = 380;
const INSPECTOR_MAX_WIDTH = 1100;

export const DEFAULT_UI_PREFERENCES: StoredUiPreferences = {
  uiVariant: "classic",
  liquidGlassAppearance: GLASS_DEFAULTS,
  language: "zh-CN",
  userDisplayName: "",
  userAvatarUrl: "",
  startupMode: "gui",
  accent: "violet",
  fontSize: "comfortable",
  messageWidth: "balanced",
  backgroundPreset: "none",
  backgroundPath: "",
  backgroundOpacity: 0.9,
  backgroundBlur: 0,
  backgroundDim: 0.12,
  // Matches the renderer's default. When these two disagreed the main process
  // won, so the transcript hid a trace the trace bar had already counted.
  showReasoning: true,
  expandReasoning: true,
  showToolCalls: true,
  showToolResults: true,
  expandToolResults: false,
  showLiveActivity: true,
  rtpProviderDetails: false,
  inspectorOpen: false,
  sidebarWidth: 268,
  inspectorWidth: 620,
  recentProjects: [],
  archivedSessions: {},
  viewPresentations: {},
};

function enumValue<T extends string>(value: unknown, values: readonly T[], fallback: T): T {
  return values.includes(value as T) ? value as T : fallback;
}

function clamp(value: unknown, minimum: number, maximum: number, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

/** Pane widths are written straight into a CSS track, so keep them integral. */
function paneWidth(value: unknown, minimum: number, maximum: number, fallback: number): number {
  return Math.round(clamp(value, minimum, maximum, fallback));
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
    uiVariant: normalizeUiVariant(source.uiVariant),
    liquidGlassAppearance: normalizeGlassAppearance(source.liquidGlassAppearance),
    language: enumValue(source.language, ["zh-CN", "en-US"] as const, DEFAULT_UI_PREFERENCES.language),
    userDisplayName: String(source.userDisplayName ?? "").trim().slice(0, 32),
    userAvatarUrl: typeof source.userAvatarUrl === "string" && source.userAvatarUrl.length <= 512 * 1024 && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(source.userAvatarUrl) ? source.userAvatarUrl : "",
    startupMode: enumValue(source.startupMode, ["gui", "tui"] as const, DEFAULT_UI_PREFERENCES.startupMode),
    accent: enumValue(source.accent, ["violet", "blue", "teal", "rose", "amber"] as const, DEFAULT_UI_PREFERENCES.accent),
    fontSize: enumValue(source.fontSize, ["compact", "comfortable", "large"] as const, DEFAULT_UI_PREFERENCES.fontSize),
    messageWidth: enumValue(source.messageWidth, ["focused", "balanced", "wide"] as const, DEFAULT_UI_PREFERENCES.messageWidth),
    backgroundPreset: enumValue(
      source.backgroundPreset,
      ["none", "aurora-archive", "moss-library", "ember-manuscript", "liquid-glass", "custom"] as const,
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
    rtpProviderDetails: source.rtpProviderDetails === undefined ? DEFAULT_UI_PREFERENCES.rtpProviderDetails : Boolean(source.rtpProviderDetails),
    inspectorOpen: source.inspectorOpen === undefined ? DEFAULT_UI_PREFERENCES.inspectorOpen : Boolean(source.inspectorOpen),
    sidebarWidth: paneWidth(source.sidebarWidth, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH, DEFAULT_UI_PREFERENCES.sidebarWidth),
    inspectorWidth: paneWidth(source.inspectorWidth, INSPECTOR_MIN_WIDTH, INSPECTOR_MAX_WIDTH, DEFAULT_UI_PREFERENCES.inspectorWidth),
    recentProjects: stringList(source.recentProjects).slice(0, 12),
    archivedSessions: archivedSessions(source.archivedSessions),
    viewPresentations: normalizeViewDisplayPreferences(source.viewPresentations),
  };
}

export function initializeUiPreferences(value: unknown, existingInstallation: boolean): StoredUiPreferences {
  return normalizeUiPreferences(value ?? { uiVariant: existingInstallation ? "classic" : "liquid-glass" });
}

export function effectiveUiPreferences(preferences: StoredUiPreferences): StoredUiPreferences {
  return preferences.uiVariant === "liquid-glass" ? { ...preferences, ...preferences.liquidGlassAppearance } : preferences;
}

export function uiThemePreference(preferences: StoredUiPreferences, classicTheme: unknown): ThemePreference {
  return preferences.uiVariant === "liquid-glass" ? preferences.liquidGlassAppearance.theme : normalizeThemePreference(classicTheme);
}

export function mergeUiPreferences(current: unknown, patch: unknown, owner?: UiVariant): StoredUiPreferences {
  const base = normalizeUiPreferences(current);
  const update = patch && typeof patch === "object" && !Array.isArray(patch)
    ? { ...patch as Record<string, unknown> }
    : {};
  const target = owner ?? normalizeUiVariant(update.uiVariant ?? base.uiVariant);
  const glass = { ...base.liquidGlassAppearance };
  if (target === "liquid-glass") {
    for (const key of ["accent", "backgroundPreset", "backgroundPath", "backgroundOpacity", "backgroundBlur", "backgroundDim"] as const) {
      if (Object.hasOwn(update, key)) {
        Object.assign(glass, { [key]: update[key] });
        delete update[key];
      }
    }
  }
  return normalizeUiPreferences({
    ...base,
    ...update,
    liquidGlassAppearance: glass,
    archivedSessions: update.archivedSessions ?? base.archivedSessions,
    recentProjects: update.recentProjects ?? base.recentProjects,
    viewPresentations: { ...base.viewPresentations, ...normalizeViewDisplayPreferences(update.viewPresentations) },
  });
}
