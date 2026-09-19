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
    expect(translate("zh-CN", "Mode")).toBe("模式");
    expect(translate("zh-CN", "Use built-in model catalog")).toBe("使用内置模型列表");
    expect(translate("zh-CN", "Client name override")).toBe("客户端名称覆盖");
    expect(translate("zh-CN", "User-Agent override")).toBe("User-Agent 覆盖");
    expect(translate("en-US", "Client name override")).toBe("Client name override");
    // Chinese-text keys pass through in zh-CN and map to English in en-US.
    expect(translate("zh-CN", "同意")).toBe("同意");
    expect(translate("en-US", "同意")).toBe("Allow");
    expect(translate("zh-CN", "本轮出错")).toBe("本轮出错");
    expect(translate("en-US", "本轮出错")).toBe("This turn errored");
    expect(translate("en-US", "我想额外说点")).toBe("I want to add something");
    // Dotted keys resolve in both template tables, interpolating values.
    expect(translate("zh-CN", "approval.notify.body", { tool: "bash" })).toBe("bash 需要你的批准才能运行");
    expect(translate("en-US", "approval.notify.body", { tool: "bash" })).toBe("bash needs your approval to run");
    expect(translate("zh-CN", "composer.interruptHint")).toBe("发送将打断当前任务并追加新要求");
    expect(translate("zh-CN", "OpenCode Zen model returned by the live API catalog.")).toBe("OpenCode Zen 实时 API 目录返回的模型。");
    expect(translate("zh-CN", "OpenCode Zen paid DeepSeek V4 Pro model available with an API key.")).toBe("需要 API 密钥的 OpenCode Zen 付费 DeepSeek V4 Pro 模型。");
    expect(translate("zh-CN", "openai-responses")).toBe("OpenAI Responses");
    expect(translate("zh-CN", "Use a high reasoning effort for complex work.")).toBe("复杂任务使用较高的思考强度。");
    expect(translate("zh-CN", "Use an explicit HTTP or HTTPS proxy for model API requests. Leave empty to use the default network settings.")).toBe("为模型 API 请求使用显式 HTTP 或 HTTPS 代理。留空则使用默认网络设置。");
    expect(translate("zh-CN", "SenseNova-hosted DeepSeek V4 Pro with a 1M context window.")).toContain("100 万 token");
  });

  it("preserves unknown core-provided text", () => {
    expect(translate("en-US", "Provider-defined label")).toBe("Provider-defined label");
  });
});
