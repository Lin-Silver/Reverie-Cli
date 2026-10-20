import { describe, expect, it } from "vitest";
import { DEFAULT_UI_PREFERENCES, mergeUiPreferences, normalizeUiPreferences } from "./preferences";
import { DEFAULT_UI_PREFERENCES as RENDERER_DEFAULTS } from "../src/preferences";

/** The renderer resolves these two into the single `backgroundPath` stored here. */
const RENDERER_ONLY_KEYS = new Set(["backgroundUrl", "backgroundName"]);

describe("desktop UI preferences", () => {
  it("merges durable view display patches, bounds history and excludes component data", () => {
    const first = mergeUiPreferences({}, { viewPresentations: { first: { mode: "pip", expanded: true, updatedAt: 1, state: "PRIVATE" } } });
    const next = mergeUiPreferences(first, { viewPresentations: { second: { mode: "inline", expanded: false, updatedAt: 2 } } });
    expect(next.viewPresentations).toEqual({ first: { mode: "pip", expanded: true, updatedAt: 1 }, second: { mode: "inline", expanded: false, updatedAt: 2 } });
    const many = normalizeUiPreferences({ viewPresentations: Object.fromEntries(Array.from({length:250}, (_,i)=>[String(i),{mode:"inline",expanded:false,updatedAt:i}])) });
    expect(Object.keys(many.viewPresentations)).toHaveLength(200);
    expect(many.viewPresentations["0"]).toBeUndefined();
    expect(normalizeUiPreferences({ viewPresentations: { bad: { mode: "carousel" } } }).viewPresentations).toEqual({});
  });
  it("uses readable defaults and shows the reasoning the trace bar counts", () => {
    expect(normalizeUiPreferences(null)).toEqual(DEFAULT_UI_PREFERENCES);
    expect(DEFAULT_UI_PREFERENCES.showReasoning).toBe(true);
    expect(DEFAULT_UI_PREFERENCES.language).toBe("zh-CN");
    expect(DEFAULT_UI_PREFERENCES.startupMode).toBe("gui");
    expect(DEFAULT_UI_PREFERENCES.expandReasoning).toBe(true);
    expect(DEFAULT_UI_PREFERENCES.showToolCalls).toBe(true);
    expect(DEFAULT_UI_PREFERENCES.showToolResults).toBe(true);
    // The RTP board opens scannable; the contract detail is opt-in per install.
    expect(DEFAULT_UI_PREFERENCES.rtpProviderDetails).toBe(false);
  });

  it("carries every preference the renderer stores", () => {
    // The renderer sends a patch and then adopts whatever this module returns, so
    // a key missing from the list here is silently discarded on every round-trip.
    // That is exactly how the inspector toggle became inert.
    const stored = new Set(Object.keys(DEFAULT_UI_PREFERENCES));
    const dropped = Object.keys(RENDERER_DEFAULTS)
      .filter((key) => !RENDERER_ONLY_KEYS.has(key) && !stored.has(key));
    expect(dropped).toEqual([]);
    expect(normalizeUiPreferences({}).inspectorOpen).toBe(DEFAULT_UI_PREFERENCES.inspectorOpen);
  });

  it("normalizes ranges, enums, archives, and recent projects", () => {
    const value = normalizeUiPreferences({
      accent: "neon",
      language: "en-US",
      startupMode: "tui",
      fontSize: "large",
      backgroundPreset: "moss-library",
      backgroundOpacity: 4,
      backgroundBlur: -1,
      recentProjects: ["G:\\One", "G:\\One", "G:\\Two"],
      archivedSessions: { "G:\\One": ["a", "a", "b"] },
    });
    expect(value.accent).toBe("violet");
    expect(value.language).toBe("en-US");
    expect(value.startupMode).toBe("tui");
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
      { accent: "blue", language: "en-US", showToolResults: true, recentProjects: ["G:\\One"] },
      { fontSize: "large" },
    );
    expect(value.accent).toBe("blue");
    expect(value.language).toBe("en-US");
    expect(value.fontSize).toBe("large");
    expect(value.showToolResults).toBe(true);
    expect(value.recentProjects).toEqual(["G:\\One"]);
  });

  it("keeps a closed inspector closed and clamps dragged pane widths", () => {
    const value = mergeUiPreferences(
      { inspectorOpen: true, sidebarWidth: 268 },
      { inspectorOpen: false, sidebarWidth: 340.4, inspectorWidth: 9_000 },
    );
    expect(value.inspectorOpen).toBe(false);
    expect(value.sidebarWidth).toBe(340);
    expect(value.inspectorWidth).toBe(1100);
    expect(mergeUiPreferences({ sidebarWidth: 12 }, {}).sidebarWidth).toBe(208);
  });

  it("persists a trimmed user label without changing other UI settings", () => {
    const value = mergeUiPreferences({ accent: "blue" }, { userDisplayName: "  Lin  " });
    expect(value.userDisplayName).toBe("Lin");
    expect(value.accent).toBe("blue");
  });
});
