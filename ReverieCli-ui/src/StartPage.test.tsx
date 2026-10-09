// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { I18nProvider } from "./i18n";
import { StarterActions, WelcomeHeader } from "./StartPage";

afterEach(cleanup);

it("shows the current workspace and sends each complete starter prompt to the composer", () => {
  const choose = vi.fn();
  render(<><WelcomeHeader workspace="Reverie-Cli" /><StarterActions choose={choose} /></>);
  expect(screen.getByText("Reverie-Cli")).toBeTruthy();
  const actions = within(screen.getByRole("navigation", { name: "从这里开始" }));
  fireEvent.click(actions.getByRole("button", { name: /理解代码库/ }));
  fireEvent.click(actions.getByRole("button", { name: /实现功能/ }));
  fireEvent.click(actions.getByRole("button", { name: /审查变更/ }));
  fireEvent.click(actions.getByRole("button", { name: /整理文档/ }));
  expect(choose.mock.calls.map(([prompt]) => prompt)).toEqual([
    "分析这个项目的架构、入口和关键模块，并指出最值得关注的技术风险。",
    "检查当前工作区，提出并实现一个最有价值且范围明确的改进，完成后运行验证。",
    "审查当前未提交的改动，重点找出正确性、安全性和回归风险。",
    "检查项目文档与实现是否一致，并修复最重要的文档缺口。",
  ]);
});

it("localizes the new welcome and starter prompt without translating workspace names", () => {
  const choose = vi.fn();
  render(<I18nProvider language="en-US"><WelcomeHeader workspace="我的项目" /><StarterActions choose={choose} /></I18nProvider>);
  expect(screen.getByRole("heading", { name: "It starts with an idea." })).toBeTruthy();
  expect(screen.getByText("我的项目")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Review changes/ }));
  expect(choose).toHaveBeenCalledWith(expect.stringContaining("Review"));
  expect(choose.mock.calls[0][0]).not.toMatch(/[\u4e00-\u9fff]/);
});
