import { describe, expect, it } from "vitest";
import { backgroundPresetUrl, DEFAULT_UI_PREFERENCES, effectiveBackgroundUrl, normalizeUiPreferences } from "./preferences";

describe("renderer UI preferences", () => {
  it("keeps technical detail off by default except tool call names", () => {
    const value = normalizeUiPreferences({});
    expect(value.showReasoning).toBe(false);
    expect(value.language).toBe("zh-CN");
    expect(value.startupMode).toBe("gui");
    expect(value.expandReasoning).toBe(true);
    expect(value.showToolCalls).toBe(true);
    expect(value.showToolResults).toBe(false);
    expect(value).toEqual(DEFAULT_UI_PREFERENCES);
  });

  it("normalizes persisted values received from Electron", () => {
    const value = normalizeUiPreferences({
      accent: "teal",
      language: "en-US",
      startupMode: "tui",
      fontSize: "large",
      messageWidth: "wide",
      backgroundPreset: "aurora-archive",
      backgroundOpacity: 0.4,
      recentProjects: ["G:\\Reverie"],
      archivedSessions: { "G:\\Reverie": ["session-1"] },
    });
    expect(value.accent).toBe("teal");
    expect(value.language).toBe("en-US");
    expect(value.startupMode).toBe("tui");
    expect(value.fontSize).toBe("large");
    expect(value.messageWidth).toBe("wide");
    expect(value.backgroundPreset).toBe("aurora-archive");
    expect(value.backgroundOpacity).toBe(0.4);
    expect(value.archivedSessions["G:\\Reverie"]).toEqual(["session-1"]);
  });

  it("resolves built-in and custom background URLs", () => {
    const builtin = normalizeUiPreferences({ backgroundPreset: "ember-manuscript" });
    expect(effectiveBackgroundUrl(builtin)).toBe(backgroundPresetUrl("ember-manuscript"));
    const custom = normalizeUiPreferences({ backgroundPreset: "custom", backgroundUrl: "file:///custom.webp" });
    expect(effectiveBackgroundUrl(custom)).toBe("file:///custom.webp");
  });
});
