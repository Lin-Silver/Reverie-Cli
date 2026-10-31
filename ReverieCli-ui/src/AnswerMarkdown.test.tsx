// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { I18nProvider } from "./i18n";
import { answerExternalUrl, answerImageUrl, parseAnswerBlock } from "./answer-blocks";

const fence = (value: unknown) => "```reverie-ui\n" + JSON.stringify(value) + "\n```";
const external = vi.fn();
beforeEach(() => { window.reverie = { openExternal: external } as unknown as typeof window.reverie; });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("rich answer content", () => {
  it("displays actual metric values including zero without replacing them with defaults", () => {
    render(<AnswerMarkdown>{fence({ type: "metrics", items: [{ label: "待处理", value: 0 }, { label: "已完成", value: "4", detail: "本周" }] })}</AnswerMarkdown>);
    expect(screen.getByText("0").tagName).toBe("DD");
    expect(screen.getByText("待处理").tagName).toBe("DT");
    expect(screen.getByText("本周")).toBeTruthy();
    expect(document.querySelector("pre")).toBeNull();
  });

  it("renders all table cells, semantic headers, status text and falsy data", () => {
    render(<AnswerMarkdown>{fence({ type: "table", title: "项目总览表", columns: ["项目", "状态", "数量", "归档"], rows: [["Reverie CLI", { text: "开发中", tone: "info" }, 0, false], ["空值", null, 1, true]], caption: "按项目统计" })}</AnswerMarkdown>);
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
    expect(screen.getByRole("region", { name: "项目总览表" }).tabIndex).toBe(0);
    expect(screen.getByText("开发中").className).toContain("answer-badge-info");
    expect(screen.getByText("0")).toBeTruthy();
    expect(screen.getByText("否")).toBeTruthy();
    expect(screen.getByText("是")).toBeTruthy();
    expect(screen.getByText("按项目统计").tagName).toBe("CAPTION");
  });

  it("supports an empty table without inventing rows", () => {
    render(<AnswerMarkdown>{fence({ type: "table", columns: ["项目"], rows: [] })}</AnswerMarkdown>);
    expect(screen.getByText("暂无数据")).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(1);
  });

  it("renders image-and-text recommendations, sources and working native external links", () => {
    render(<AnswerMarkdown>{fence({ type: "cards", numbered: true, items: [{ title: "Plane", description: "项目管理界面", badge: { text: "综合首选", tone: "success" }, image: { url: "https://example.com/plane.png", alt: "Plane 看板截图" }, details: ["支持看板和工作项。"], sources: [{ label: "Plane", url: "https://plane.so/" }], links: [{ label: "GitHub 源码", url: "https://github.com/makeplane/plane" }] }] })}</AnswerMarkdown>);
    expect(screen.getByRole("heading", { name: "1. Plane" })).toBeTruthy();
    const image = screen.getByRole("img", { name: "Plane 看板截图" }) as HTMLImageElement;
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(image.crossOrigin).toBe("anonymous");
    expect(screen.getByRole("group", { name: "来源" })).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "GitHub 源码" }));
    expect(external).toHaveBeenCalledWith("https://github.com/makeplane/plane");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: "Plane 看板截图" }).tagName).toBe("SPAN");
    expect(document.querySelector("img")).toBeNull();
  });

  it("handles actual streaming fragments, then renders the completed block", () => {
    const { rerender } = render(<AnswerMarkdown streaming>{"```reverie-ui\n{\"type\":\"metrics\",\"items\":["}</AnswerMarkdown>);
    expect(screen.getByRole("status").textContent).toBe("正在整理内容…");
    expect(document.querySelector("pre")).toBeNull();
    rerender(<AnswerMarkdown>{fence({ type: "metrics", items: [{ label: "计划中", value: 7 }] })}</AnswerMarkdown>);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("7")).toBeTruthy();
  });

  it("retains images and focused links when later streaming text is appended", () => {
    const body = fence({ type: "cards", items: [{ title: "图片", description: "说明", image: { url: "https://example.com/screen.png", alt: "截图" }, links: [{ label: "官网", url: "https://example.com" }] }] });
    const { rerender } = render(<AnswerMarkdown streaming>{body}</AnswerMarkdown>);
    const image = screen.getByRole("img", { name: "截图" });
    const link = screen.getByRole("link", { name: "官网" });
    link.focus();
    rerender(<AnswerMarkdown streaming>{body + "\n\n继续补充说明。"}</AnswerMarkdown>);
    expect(screen.getByRole("img", { name: "截图" })).toBe(image);
    expect(document.activeElement).toBe(link);
    rerender(<AnswerMarkdown>{body + "\n\n继续补充说明。"}</AnswerMarkdown>);
    expect(screen.getByRole("img", { name: "截图" })).toBe(image);
    expect(document.activeElement).toBe(link);
  });

  it("shows the full invalid block when streaming ends without a text change", () => {
    const body = fence({ type: "table", columns: ["项目"], rows: [["项目一", "不能丢失"]] });
    const { rerender } = render(<AnswerMarkdown streaming>{body}</AnswerMarkdown>);
    expect(screen.getByRole("status").textContent).toBe("正在整理内容…");
    rerender(<AnswerMarkdown>{body}</AnswerMarkdown>);
    expect(screen.queryByRole("status")).toBeNull();
    expect(document.querySelector("pre")?.textContent).toContain("不能丢失");
  });

  it("preserves invalid or unsupported final blocks in full instead of silently hiding data", () => {
    const malformed = { type: "table", columns: ["名称"], rows: [["项目", "不能丢失的第二格"]] };
    render(<AnswerMarkdown>{fence(malformed)}</AnswerMarkdown>);
    expect(document.querySelector("pre")?.textContent).toContain("不能丢失的第二格");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("keeps an unrecognized table note visible with the complete original data", () => {
    const source = '{"type":"table","columns":["项目"],"rows":[["Reverie CLI"]],"note":"尚有两项未完成"}';
    render(<AnswerMarkdown>{"```reverie-ui\n" + source + "\n```"}</AnswerMarkdown>);
    expect(document.querySelector("pre")?.textContent).toContain(source);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("keeps normal Markdown formatting, code, file navigation and horizontally scrollable tables", () => {
    const open = vi.fn(); window.addEventListener("reverie:file-open", open);
    render(<AnswerMarkdown>{"## 标题\n\n| 项目 | 状态 |\n| --- | --- |\n| CLI | 开发中 |\n\n[源码](/workspace/demo/app.py:12)\n\n```python\nprint(0)\n```"}</AnswerMarkdown>);
    expect(within(screen.getByRole("region", { name: "表格" })).getByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "项目" }).getAttribute("scope")).toBe("col");
    fireEvent.click(screen.getByRole("link", { name: "源码" }));
    expect((open.mock.calls[0][0] as CustomEvent).detail).toEqual({ path: "/workspace/demo/app.py", line: 12 });
    expect(document.querySelector("code.language-python")?.textContent).toContain("print(0)");
    window.removeEventListener("reverie:file-open", open);
  });

  it("never executes raw HTML, arbitrary actions or dangerous links", () => {
    render(<AnswerMarkdown>{"<script>window.answerInjected=true</script>\n\n[危险](javascript:alert(1))\n\n" + fence({ type: "sources", items: [{ label: "伪装链接", url: "file:///etc/passwd" }, { label: "脚本链接", url: "javascript:alert(1)" }] })}</AnswerMarkdown>);
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(external).not.toHaveBeenCalled();
  });

  it("localizes host-owned feedback while preserving the answer language", () => {
    render(<I18nProvider language="en-US"><AnswerMarkdown>{fence({ type: "table", columns: ["中文列名"], rows: [] })}</AnswerMarkdown></I18nProvider>);
    expect(screen.getByText("No data")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "中文列名" })).toBeTruthy();
  });
});

describe("answer boundary", () => {
  it.each(["javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "https://user:secret@example.com/x", "/etc/passwd"])("refuses non-web or credential-bearing external URL %s", url => {
    expect(answerExternalUrl(url)).toBeNull();
  });
  it("loads only raster data or HTTPS images", () => {
    expect(answerImageUrl("data:image/png;base64,aGVsbG8=")).toBeTruthy();
    for (const url of ["file:///tmp/private.png", "http://example.com/image.png", "data:image/svg+xml;base64,PHN2Zz4=", "blob:private", "../secret.png"]) expect(answerImageUrl(url)).toBeNull();
  });
  it.each([{}, { type: "metrics", items: [{ label: "坏值", value: null }] }, { type: "table", columns: ["项目"], rows: [[{}]] }, { type: "cards", items: [{ title: "无说明" }] }])("leaves unsupported shapes as original content", value => {
    expect(parseAnswerBlock(JSON.stringify(value))).toBeNull();
  });
});
