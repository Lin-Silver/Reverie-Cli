import { describe, expect, it } from "vitest";
import { DEFAULT_UI_PREFERENCES, mergeUiPreferences, normalizeUiPreferences } from "./preferences";

describe("desktop UI preferences", () => {
  it("uses readable defaults that hide raw reasoning and tool results", () => {
    expect(normalizeUiPreferences(null)).toEqual(DEFAULT_UI_PREFERENCES);
    expect(DEFAULT_UI_PREFERENCES.showReasoning).toBe(false);
    expect(DEFAULT_UI_PREFERENCES.expandReasoning).toBe(true);
    expect(DEFAULT_UI_PREFERENCES.showToolCalls).toBe(true);
    expect(DEFAULT_UI_PREFERENCES.showToolResults).toBe(false);
  });

  it("normalizes ranges, enums, archives, and recent projects", () => {
    const value = normalizeUiPreferences({
      accent: "neon",
      fontSize: "large",
      backgroundPreset: "moss-library",
      backgroundOpacity: 4,
      backgroundBlur: -1,
      recentProjects: ["G:\\One", "G:\\One", "G:\\Two"],
      archivedSessions: { "G:\\One": ["a", "a", "b"] },
    });
    expect(value.accent).toBe("violet");
    expect(value.fontSize).toBe("large");
    expect(value.backgroundPreset).toBe("moss-library");
    expect(value.backgroundOpacity).toBe(1);
    expect(value.backgroundBlur).toBe(0);
    expect(value.recentProjects).toEqual(["G:\\One", "G:\\Two"]);
    expect(value.archivedSessions["G:\\One"]).toEqual(["a", "b"]);
  });

  it("upgrades an existing imported background to the custom preset", () => {
    expect(normalizeUiPreferences({ backgroundPath: "G:\\Art\\background.png" }).backgroundPreset).toBe("custom");
  });

  it("merges small renderer patches without resetting unrelated preferences", () => {
    const value = mergeUiPreferences(
      { accent: "blue", showToolResults: true, recentProjects: ["G:\\One"] },
      { fontSize: "large" },
    );
    expect(value.accent).toBe("blue");
    expect(value.fontSize).toBe("large");
    expect(value.showToolResults).toBe(true);
    expect(value.recentProjects).toEqual(["G:\\One"]);
  });
});
