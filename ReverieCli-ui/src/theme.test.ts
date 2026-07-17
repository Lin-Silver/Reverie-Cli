import { describe, expect, it } from "vitest";
import { normalizeTheme, resolveTheme } from "./theme";

describe("theme preferences", () => {
  it("normalizes persisted values", () => {
    expect(normalizeTheme("dark")).toBe("dark");
    expect(normalizeTheme("light")).toBe("light");
    expect(normalizeTheme("system")).toBe("system");
    expect(normalizeTheme("midnight")).toBe("system");
    expect(normalizeTheme(null)).toBe("system");
  });

  it("resolves system appearance without changing explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });
});
