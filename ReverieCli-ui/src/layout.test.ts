import { describe, expect, it } from "vitest";
import {
  clampInspectorWidth,
  clampSidebarWidth,
  INSPECTOR_DEFAULT_WIDTH,
  INSPECTOR_MAX_WIDTH,
  INSPECTOR_MIN_WIDTH,
  MAIN_AREA_MIN_WIDTH,
  normalizeSidebarCollapsed,
  paneDragLimit,
  resolveSidebarCollapsed,
  SIDEBAR_AUTO_COLLAPSE_QUERY,
  SIDEBAR_COLLAPSED_STORAGE_KEY,
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
} from "./layout";

describe("sidebar layout preference", () => {
  it("uses a stable storage key", () => {
    expect(SIDEBAR_COLLAPSED_STORAGE_KEY).toBe("reverie.layout.sidebar-collapsed");
  });

  it("restores only an explicitly collapsed sidebar", () => {
    expect(normalizeSidebarCollapsed("true")).toBe(true);
    expect(normalizeSidebarCollapsed("false")).toBe(false);
    expect(normalizeSidebarCollapsed(null)).toBe(false);
    expect(normalizeSidebarCollapsed("1")).toBe(false);
  });

  it("auto-collapses at the same compact width used by the inspector", () => {
    expect(SIDEBAR_AUTO_COLLAPSE_QUERY).toBe("(max-width: 1100px)");
    expect(resolveSidebarCollapsed(false, true, null)).toBe(true);
    expect(resolveSidebarCollapsed(false, false, null)).toBe(false);
    expect(resolveSidebarCollapsed(true, false, null)).toBe(true);
  });

  it("allows a button or shortcut to override automatic collapse until the viewport changes", () => {
    expect(resolveSidebarCollapsed(false, true, false)).toBe(false);
    expect(resolveSidebarCollapsed(false, true, true)).toBe(true);
  });
});

describe("side pane drag geometry", () => {
  it("clamps a dragged width into its own pane's range", () => {
    expect(clampSidebarWidth(340.6)).toBe(341);
    expect(clampSidebarWidth(10)).toBe(SIDEBAR_MIN_WIDTH);
    expect(clampSidebarWidth(9_000)).toBe(SIDEBAR_MAX_WIDTH);
    expect(clampSidebarWidth(Number.NaN)).toBe(SIDEBAR_DEFAULT_WIDTH);
    expect(clampInspectorWidth(10)).toBe(INSPECTOR_MIN_WIDTH);
    expect(clampInspectorWidth(9_000)).toBe(INSPECTOR_MAX_WIDTH);
    expect(clampInspectorWidth(Number.NaN)).toBe(INSPECTOR_DEFAULT_WIDTH);
  });

  it("never lets one pane drag the conversation column below its floor", () => {
    // A 1000px window with a 316px inspector leaves the sidebar 264px.
    expect(paneDragLimit(1_000, INSPECTOR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH))
      .toBe(1_000 - INSPECTOR_DEFAULT_WIDTH - MAIN_AREA_MIN_WIDTH);
    // A window with room to spare stops at the pane's own maximum instead.
    expect(paneDragLimit(2_400, INSPECTOR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH)).toBe(SIDEBAR_MAX_WIDTH);
    // Narrower than the floor plus the other pane: no width is affordable.
    expect(paneDragLimit(600, INSPECTOR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH)).toBe(0);
    // An unmeasured shell must not pin the handle; fall back to the full range.
    expect(paneDragLimit(0, 0, INSPECTOR_MAX_WIDTH)).toBe(INSPECTOR_MAX_WIDTH);
    expect(paneDragLimit(Number.NaN, 0, INSPECTOR_MIN_WIDTH)).toBe(INSPECTOR_MIN_WIDTH);
  });
});
