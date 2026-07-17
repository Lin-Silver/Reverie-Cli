import { describe, expect, it } from "vitest";
import { normalizeThemePreference, windowAppearance } from "./appearance";

describe("desktop appearance", () => {
  it("falls back to the system preference for invalid values", () => {
    expect(normalizeThemePreference("dark")).toBe("dark");
    expect(normalizeThemePreference("light")).toBe("light");
    expect(normalizeThemePreference("system")).toBe("system");
    expect(normalizeThemePreference("sepia")).toBe("system");
  });

  it("keeps the native title bar aligned with the renderer palette", () => {
    expect(windowAppearance(true)).toEqual({
      backgroundColor: "#0b0d12",
      overlayColor: "#0e1117",
      symbolColor: "#aeb4bf",
    });
    expect(windowAppearance(false)).toEqual({
      backgroundColor: "#f6f7f9",
      overlayColor: "#eef0f4",
      symbolColor: "#5f6671",
    });
  });
});
