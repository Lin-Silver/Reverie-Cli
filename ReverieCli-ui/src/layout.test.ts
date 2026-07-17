import { describe, expect, it } from "vitest";
import { normalizeSidebarCollapsed, SIDEBAR_COLLAPSED_STORAGE_KEY } from "./layout";

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
});
