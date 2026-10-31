import { describe, expect, it } from "vitest";
import {
  effectiveUiPreferences,
  initializeUiPreferences,
  mergeUiPreferences,
  normalizeUiPreferences,
  uiThemePreference,
} from "./preferences";

describe("Liquid Glass appearance", () => {
  it("opens fresh desktop installations in Liquid Glass and preserves existing installations", () => {
    expect(initializeUiPreferences(undefined, false).uiVariant).toBe("liquid-glass");
    expect(initializeUiPreferences(undefined, true).uiVariant).toBe("classic");
    expect(initializeUiPreferences({ accent: "blue" }, true).uiVariant).toBe("classic");
    expect(initializeUiPreferences({ uiVariant: "classic" }, true).uiVariant).toBe("classic");
    expect(initializeUiPreferences({ uiVariant: "liquid-glass" }, true).uiVariant).toBe("liquid-glass");
    expect(normalizeUiPreferences({ uiVariant: "unknown" }).uiVariant).toBe("classic");
  });

  it("resolves an independent background and brand palette without rewriting classic appearance", () => {
    const classic = normalizeUiPreferences({ accent: "blue", backgroundPreset: "custom", backgroundPath: "G:\\art.webp", backgroundBlur: 7 });
    const glass = mergeUiPreferences(classic, { uiVariant: "liquid-glass" });
    expect(effectiveUiPreferences(glass)).toMatchObject({ accent: "violet", backgroundPreset: "liquid-glass", backgroundPath: "", backgroundBlur: 0 });
    expect(glass).toMatchObject({ accent: "blue", backgroundPreset: "custom", backgroundPath: "G:\\art.webp", backgroundBlur: 7 });
    expect(effectiveUiPreferences(mergeUiPreferences(glass, { uiVariant: "classic" }))).toMatchObject({ accent: "blue", backgroundPath: "G:\\art.webp", backgroundBlur: 7 });
  });

  it("routes delayed appearance writes to their original UI while keeping shared preferences shared", () => {
    const glass = mergeUiPreferences({}, { uiVariant: "liquid-glass" });
    const edited = mergeUiPreferences(glass, { backgroundOpacity: 0.7, accent: "rose", language: "en-US", fontSize: "large" }, "liquid-glass");
    const switched = mergeUiPreferences(edited, { uiVariant: "classic" });
    const delayed = mergeUiPreferences(switched, { backgroundBlur: 5 }, "liquid-glass");
    expect(delayed.uiVariant).toBe("classic");
    expect(effectiveUiPreferences(delayed)).toMatchObject({ backgroundBlur: 0, accent: "violet", language: "en-US", fontSize: "large" });
    expect(effectiveUiPreferences(mergeUiPreferences(delayed, { uiVariant: "liquid-glass" }))).toMatchObject({ backgroundBlur: 5, backgroundOpacity: 0.7, accent: "rose", language: "en-US", fontSize: "large" });
  });

  it("bounds the glass profile and keeps each theme independent", () => {
    const ui = normalizeUiPreferences({ uiVariant: "liquid-glass", liquidGlassAppearance: { theme: "dark", accent: "invalid", backgroundOpacity: 9, backgroundBlur: -1, backgroundDim: 3 } });
    expect(effectiveUiPreferences(ui)).toMatchObject({ accent: "violet", backgroundOpacity: 1, backgroundBlur: 0, backgroundDim: 0.8 });
    expect(uiThemePreference(ui, "light")).toBe("dark");
    expect(uiThemePreference(mergeUiPreferences(ui, { uiVariant: "classic" }), "light")).toBe("light");
    expect(uiThemePreference(mergeUiPreferences({}, { uiVariant: "liquid-glass" }), "dark")).toBe("system");
  });
});
