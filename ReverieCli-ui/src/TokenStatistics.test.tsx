// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "./i18n";
import TokenStatistics from "./TokenStatistics";
import type { TokenStatisticsData, TokenTotals } from "./types";

const totals: TokenTotals = { calls: 2, input_tokens: 1000, uncached_input_tokens: 600, cached_input_tokens: 400, output_tokens: 200, total_tokens: 1200,
  api_calls: 1, mixed_calls: 1, local_calls: 0, historical_calls: 0, unknown_cache_calls: 1, unpriced_calls: 2, costs: {} };
const report: TokenStatisticsData = { filters: {}, totals, models: [{ ...totals, model_key: "gemini::model", model: "model", name: "Gemini Test", provider: "gemini", price: null }],
  daily: [{ ...totals, date: "2026-11-12" }], prices: {}, timezone: "UTC", excluded_historical_calls: 0, warnings: [],
  options: { projects: [{ id: "one", name: "One", path: "G:/One" }], sessions: [{ id: "one::s1", session_id: "s1", name: "First", project_id: "one", project_name: "One" }], models: [{ id: "gemini::model", name: "Gemini Test", provider: "gemini" }] } };
const request = vi.fn();

beforeEach(() => {
  request.mockReset().mockImplementation(async (action: string) => action === "exportTokenStatistics"
    ? { type: "token.csv", filename: "Tokens.csv", content: "model,total_tokens\nmodel,1200\n" }
    : action === "setTokenPrice" ? { type: "token.price", model_key: "gemini::model", price: { currency: "USD", input: 2, cached_input: 0.5, output: 8 } }
    : { type: "token.statistics", statistics: report });
  Object.defineProperty(window, "reverie", { configurable: true, value: { request } });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const show = () => render(<I18nProvider language="zh-CN"><TokenStatistics projectRoot="G:/One" /></I18nProvider>);
const waitForTotals = () => screen.findByText("1,200", { selector: "dd" });

describe("Token statistics", () => {
  it("shows totals, charts and provenance without a fabricated price", async () => {
    show();
    await screen.findByText("Token 用量统计");
    await waitForTotals();
    const chart = screen.getByRole("img", { name: "Token 用量趋势（UTC）" });
    const dateLabel = within(chart).getByText("2026-11-12", { selector: "text" });
    expect(dateLabel.getAttribute("x")).toBe(chart.querySelector("circle")?.getAttribute("cx"));
    expect(screen.getByText(/尚未设置价格/)).toBeTruthy();
    expect(screen.getByText(/缓存用量未提供/)).toBeTruthy();
  });

  it("plots missing days as gaps on the UTC timeline", async () => {
    request.mockResolvedValueOnce({ type: "token.statistics", statistics: { ...report, daily: [
      { ...totals, date: "2026-11-01" }, { ...totals, date: "2026-11-02" }, { ...totals, date: "2026-11-11" },
    ] } });
    show();
    const chart = await screen.findByRole("img", { name: "Token 用量趋势（UTC）" });
    const [first, second, last] = Array.from(chart.querySelectorAll("circle"), point => Number(point.getAttribute("cx")));
    expect((second - first) / (last - first)).toBeCloseTo(0.1);
  });

  it("sends date, project, session and model filters to the same core report", async () => {
    show();
    await waitForTotals();
    fireEvent.change(screen.getByLabelText("开始日期（UTC）"), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("结束日期（UTC）"), { target: { value: "2026-11-12" } });
    fireEvent.change(screen.getByLabelText("统计项目"), { target: { value: "one" } });
    fireEvent.change(screen.getByLabelText("统计会话"), { target: { value: "one::s1" } });
    fireEvent.change(screen.getByLabelText("统计模型"), { target: { value: "gemini::model" } });
    await waitFor(() => expect(request).toHaveBeenLastCalledWith("getTokenStatistics", { projectRoot: "G:/One", filters: { start: "2026-11-10", end: "2026-11-12", project: "one", session: "one::s1", model: "gemini::model" } }));
  });

  it("persists all three price rates and currency per model", async () => {
    show();
    const form = await screen.findByRole("form", { name: "模型 Token 价格" });
    fireEvent.change(within(form).getByLabelText("普通输入"), { target: { value: "2" } });
    fireEvent.change(within(form).getByLabelText("缓存输入"), { target: { value: "0.5" } });
    fireEvent.change(within(form).getByLabelText("输出"), { target: { value: "8" } });
    fireEvent.click(within(form).getByRole("button", { name: "保存价格" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("setTokenPrice", { modelKey: "gemini::model", price: { currency: "USD", input: 2, cached_input: 0.5, output: 8 } }));
  });

  it("exports the active filter and releases the download object URL", async () => {
    const create = vi.fn(() => "blob:test");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    show();
    await waitForTotals();
    fireEvent.change(screen.getByLabelText("统计模型"), { target: { value: "gemini::model" } });
    await waitFor(() => expect(request).toHaveBeenLastCalledWith("getTokenStatistics", expect.objectContaining({ filters: { model: "gemini::model" } })));
    await waitForTotals();
    fireEvent.click(screen.getByRole("button", { name: "导出 CSV" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("exportTokenStatistics", { projectRoot: "G:/One", filters: { model: "gemini::model" } }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:test"));
  });

  it("shows core errors and allows a retry", async () => {
    request.mockRejectedValueOnce(new Error("Statistics unavailable"));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Statistics unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitForTotals();
  });
});
