import { describe, expect, it } from "vitest";
import { normalizeUiLanguage, translate } from "./i18n";

describe("GUI internationalization", () => {
  it("normalizes supported languages and keeps Chinese as the compatibility default", () => {
    expect(normalizeUiLanguage("en-US")).toBe("en-US");
    expect(normalizeUiLanguage("zh-CN")).toBe("zh-CN");
    expect(normalizeUiLanguage("fr-FR")).toBe("zh-CN");
  });

  it("translates fixed labels and interpolated interface messages", () => {
    expect(translate("en-US", "设置")).toBe("Settings");
    expect(translate("en-US", "session.count", { count: 3, time: "10:30" })).toBe("3 messages · 10:30");
    expect(translate("zh-CN", "设置")).toBe("设置");
  });

  it("preserves unknown core-provided text", () => {
    expect(translate("en-US", "Provider-defined label")).toBe("Provider-defined label");
  });
});
