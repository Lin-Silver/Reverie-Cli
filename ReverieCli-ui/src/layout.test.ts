import { describe, expect, it } from "vitest";
import {
  normalizeSidebarCollapsed,
  resolveSidebarCollapsed,
  SIDEBAR_AUTO_COLLAPSE_QUERY,
  SIDEBAR_COLLAPSED_STORAGE_KEY,
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
