// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InteractiveView } from "./InteractiveView";
import { version as desktopVersion } from "../package.json";
import type { ResolvedViewRef, ViewSegment } from "./types";
import { I18nProvider } from "./i18n";
import { ViewPresentationProvider, useViewPresentation } from "./ViewPresentation";

// InteractiveView is the P1 presentation of a kernel-minted view. It owns NO
// interactivity round-trip (setViewState/callViewTool is P2): it resolves the
// opaque handle through getView and paints the resolved bytes in a scripts-only
// sandboxed iframe, degrading to the summary text and recovering from errors.
// The HTML never enters the renderer DOM, so these tests pin the security seam:
// a scripts-only sandbox (never allow-same-origin), an opaque reverie-view URL,
// and never srcdoc/raw HTML.

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (Element.prototype as Partial<Element>).moveBefore;
  localStorage.clear();
});

function PresentationSlots() {
  const presentation = useViewPresentation();
  return <div ref={presentation.setFullscreenSlot} data-testid="fullscreen-slot" />;
}

describe("RIU P4 presentation lifetime", () => {
  it("offers a compact pip summary without losing its text or recreating the frame", async () => {
    Element.prototype.moveBefore = function (node, child) { this.insertBefore(node, child); };
    const request = vi.fn().mockResolvedValue(resolved());
    stubReverie(request);
    render(<ViewPresentationProvider><InteractiveView segment={segment()} /></ViewPresentationProvider>);
    const frame = await waitFor(() => { const frame = document.querySelector("iframe"); expect(frame).toBeTruthy(); return frame!; });
    fireEvent.click(screen.getByRole("button", { name: "画中画" }));
    const expand = screen.getByRole("button", { name: "展开摘要" });
    expect(expand.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText("Q3 bars.")).toBeTruthy();
    fireEvent.click(expand);
    expect(screen.getByRole("button", { name: "收起摘要" }).getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelector(".view-pip-slot iframe")).toBe(frame);
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
  });

  it("keeps one instance when live and historical references hand off in one commit", async () => {
    Element.prototype.moveBefore = function (node, child) { this.insertBefore(node, child); };
    const request = vi.fn().mockResolvedValue(resolved({ interactionId: "handoff" }));
    stubReverie(request);
    const ui = (history: boolean) => <ViewPresentationProvider>
      <div data-testid="live">{!history && <InteractiveView segment={segment()} />}</div>
      <div data-testid="history">{history && <InteractiveView segment={segment()} />}</div>
    </ViewPresentationProvider>;
    const { rerender, unmount } = render(ui(false));
    const frame = await waitFor(() => { const frame = screen.getByTestId("live").querySelector("iframe"); expect(frame).toBeTruthy(); return frame!; });
    rerender(ui(true));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("history").querySelector("iframe")).toBe(frame);
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
    expect(request).not.toHaveBeenCalledWith("releaseView", expect.anything());
    unmount();
    expect(request).toHaveBeenCalledWith("releaseView", { interactionId: "handoff" });
  });

  it("rejects layout names as display modes and accepts the three standard modes", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    const { win, posted } = await readyFrame(request);
    post(win, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: {} });
    const capability = String(posted[0].result?.capability);
    post(win, { jsonrpc: "2.0", method: "ui/notifications/initialized", capability });
    post(win, { jsonrpc: "2.0", id: "bad", method: "ui/request-display-mode", capability, params: { mode: "carousel" } });
    expect(posted.find(message => message.id === "bad")?.error?.message).toContain("layouts");
    post(win, { jsonrpc: "2.0", id: "good", method: "ui/request-display-mode", capability, params: { mode: "inline" } });
    expect(posted.find(message => message.id === "good")?.result).toEqual({ mode: "inline" });
    expect(request).not.toHaveBeenCalledWith("callViewTool", expect.anything());
  });

  it("releases a late resolution after unmount and rejects a mismatched instance", async () => {
    let resolve: (value: ReturnType<typeof resolved>) => void = () => {};
    const request = vi.fn().mockImplementation(() => new Promise(value => { resolve = value; }));
    stubReverie(request);
    const { unmount } = render(<InteractiveView segment={segment()} />);
    unmount();
    await act(async () => resolve(resolved({ interactionId: "late" })));
    expect(request).toHaveBeenCalledWith("releaseView", { interactionId: "late" });
    request.mockResolvedValue(resolved({ sessionId: "other", interactionId: "wrong" }));
    render(<InteractiveView segment={segment()} />);
    await screen.findByRole("alert");
    expect(request).toHaveBeenCalledWith("releaseView", { interactionId: "wrong" });
  });

  it("moves the same surface and frame between inline, Workbench and pip without resolving again", async () => {
    // Chromium's state-preserving move is exercised in the packaged acceptance.
    const move = vi.fn(function (this: Element, node: Node, child: Node | null) { this.insertBefore(node, child); });
    vi.stubGlobal("IntersectionObserver", undefined);
    Element.prototype.moveBefore = move;
    const request = vi.fn().mockResolvedValue(resolved({ interactionId: "lease-1" }));
    stubReverie(request);
    const { container } = render(<ViewPresentationProvider><InteractiveView segment={segment()} /><PresentationSlots /></ViewPresentationProvider>);
    const frame = await waitFor(() => { const frame = container.querySelector("iframe"); expect(frame).toBeTruthy(); return frame!; });
    const registeredWindow = frame.contentWindow!;
    fireEvent.click(screen.getByRole("button", { name: "在工作面板中放大" }));
    expect(screen.getByTestId("fullscreen-slot").querySelector("iframe")).toBe(frame);
    fireEvent.click(screen.getByRole("button", { name: "画中画" }));
    expect(document.querySelector(".view-pip-slot iframe")).toBe(frame);
    post(window, { type: "reverie:view-escape" });
    expect(document.querySelector(".view-pip-slot iframe")).toBe(frame);
    act(() => post(registeredWindow, { type: "reverie:view-escape" }));
    expect(container.querySelector(".interactive-view-anchor iframe")).toBe(frame);
    fireEvent.click(screen.getByRole("button", { name: "返回对话内" }));
    expect(container.querySelector(".interactive-view-anchor iframe")).toBe(frame);
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
    expect(request).not.toHaveBeenCalledWith("releaseView", expect.anything());
    expect(document.activeElement?.getAttribute("data-view-mode")).toBe("fullscreen");
    delete (Element.prototype as Partial<Element>).moveBefore;
  });

  it("restores collapsed host presentation without resolving hidden content", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    stubReverie(request);
    const first = render(<InteractiveView segment={segment()} />);
    await waitFor(() => expect(first.container.querySelector("iframe")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "收起" }));
    await waitFor(() => expect(first.container.querySelector("iframe")).toBeNull());
    const persisted = JSON.parse(localStorage.getItem("reverie.view-presentation.v1") || "{}");
    first.unmount(); request.mockClear();
    localStorage.clear();
    render(<ViewPresentationProvider persisted={persisted}><InteractiveView segment={segment()} /></ViewPresentationProvider>);
    expect(screen.getByRole("button", { name: "展开" }).getAttribute("aria-expanded")).toBe("false");
    expect(request).not.toHaveBeenCalled();
  });

  it("updates language and host context without recreating the instance", async () => {
    const request = vi.fn().mockResolvedValue(resolved({ interactionId: "lease-1" }));
    stubReverie(request);
    const ui = (language: "zh-CN" | "en-US") => <I18nProvider language={language}><InteractiveView segment={segment()} /></I18nProvider>;
    const { container, rerender } = render(ui("zh-CN"));
    const frame = await waitFor(() => { const frame = container.querySelector("iframe"); expect(frame).toBeTruthy(); return frame!; });
    const postMessage = vi.spyOn(frame.contentWindow!, "postMessage");
    post(frame.contentWindow!, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: {} });
    const capability = postMessage.mock.calls[0][0].result.capability;
    post(frame.contentWindow!, { jsonrpc: "2.0", method: "ui/notifications/initialized", capability });
    rerender(ui("en-US"));
    expect(container.querySelector("iframe")).toBe(frame);
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ method: "ui/notifications/host-context-changed", params: expect.objectContaining({ locale: "en-US" }) }), "*"));
  });

  it("does not resolve 100 offscreen historical views and releases an instance leaving the viewport", async () => {
    const observers: Array<(entries: Partial<IntersectionObserverEntry>[]) => void> = [];
    const disconnect = vi.fn();
    vi.stubGlobal("IntersectionObserver", class {
      constructor(callback: (entries: Partial<IntersectionObserverEntry>[]) => void) { observers.push(callback); }
      observe() {} disconnect = disconnect;
    });
    const request = vi.fn().mockResolvedValue(resolved({ interactionId: "lease-1" }));
    stubReverie(request);
    const { unmount } = render(<>{Array.from({ length: 100 }, (_, i) => <InteractiveView key={i} segment={segment({ viewId: i ? `view-${i}` : "vabc123" })} />)}</>);
    expect(request).not.toHaveBeenCalled();
    act(() => observers[0]([{ isIntersecting: true }]));
    await waitFor(() => expect(document.querySelectorAll("iframe")).toHaveLength(1));
    const activeFrame = document.querySelector("iframe")!;
    const surface = activeFrame.closest("section")!.parentElement!;
    const posted = vi.spyOn(activeFrame.contentWindow!, "postMessage");
    post(activeFrame.contentWindow!, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: {} });
    const capability = posted.mock.calls[0][0].result.capability;
    post(activeFrame.contentWindow!, { jsonrpc: "2.0", method: "ui/notifications/initialized", capability });
    post(activeFrame.contentWindow!, { jsonrpc: "2.0", method: "ui/notifications/size-changed", capability, params: { height: 650 } });
    act(() => activeFrame.focus());
    act(() => observers[0]([{ isIntersecting: false }]));
    expect(document.querySelectorAll("iframe")).toHaveLength(1);
    await act(async () => { activeFrame.blur(); await Promise.resolve(); });
    await waitFor(() => expect(request).toHaveBeenCalledWith("releaseView", { interactionId: "lease-1" }));
    expect(document.querySelectorAll("iframe")).toHaveLength(0);
    expect(surface.style.getPropertyValue("--view-inline-height")).toBe("650px");
    expect(surface.querySelector(".interactive-view-placeholder")).toBeTruthy();
    act(() => observers[0]([{ isIntersecting: true }]));
    await waitFor(() => expect(document.querySelectorAll("iframe")).toHaveLength(1));
    expect(surface.style.getPropertyValue("--view-inline-height")).toBe("650px");
    unmount();
    expect(disconnect).toHaveBeenCalledTimes(100);
    vi.unstubAllGlobals();
  });
});

const segment = (over: Partial<ViewSegment> = {}): ViewSegment => ({
  sessionId: "sess-1",
  viewId: "vabc123",
  revision: 1,
  title: "Sales chart",
  summary: "Q3 bars.",
  status: "ready",
  ...over,
});

const resolved = (over: Partial<ResolvedViewRef> = {}) => ({
  type: "view.resolved" as const,
  view: {
    sessionId: "sess-1",
    viewId: "vabc123",
    revision: 1,
    title: "Sales chart",
    summary: "Q3 bars.",
    mimeType: "text/html",
    policyId: "local-offline-v1",
    url: "reverie-view://sess-1/vabc123/1/index.html",
    state: null,
    ...over,
  } satisfies ResolvedViewRef,
});

const stubReverie = (request: ReturnType<typeof vi.fn>) => {
  window.reverie = { request } as unknown as typeof window.reverie;
};

describe("InteractiveView", () => {
  it("resolves the opaque handle through getView and paints a scripts-only sandboxed iframe", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    stubReverie(request);
    const { container } = render(<InteractiveView segment={segment()} />);
    const frame = await waitFor(() => {
      const found = container.querySelector("iframe");
      if (!found) throw new Error("iframe not yet rendered");
      return found;
    });
    expect(request).toHaveBeenCalledWith("getView", { sessionId: "sess-1", viewId: "vabc123", revision: 1 });
    expect(frame.getAttribute("src")).toBe("reverie-view://sess-1/vabc123/1/index.html");
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame.hasAttribute("srcdoc")).toBe(false);
  });

  it("always shows the title and summary as degradation text", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    stubReverie(request);
    render(<InteractiveView segment={segment()} />);
    expect(screen.getByText("Sales chart")).toBeTruthy();
    expect(screen.getByText("Q3 bars.")).toBeTruthy();
    await waitFor(() => expect(request).toHaveBeenCalled());
  });

  it("expands a long summary without replacing the running view", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    stubReverie(request);
    const summary = "中文长摘要与参数比较。".repeat(30);
    const { container } = render(<I18nProvider language="zh-CN"><InteractiveView segment={segment({ summary })} /></I18nProvider>);
    const frame = await waitFor(() => { const found = container.querySelector("iframe"); expect(found).toBeTruthy(); return found; });
    const toggle = screen.getByRole("button", { name: "展开摘要" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "收起摘要" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(summary).textContent).toBe(summary);
    expect(container.querySelector("iframe")).toBe(frame);
    expect(request.mock.calls.filter(([action]) => action === "getView")).toHaveLength(1);
  });

  it("recovers from a getView failure and retries on demand", async () => {
    const request = vi
      .fn()
      .mockRejectedValueOnce(new Error("view vabc123 is not stored"))
      .mockResolvedValueOnce(resolved());
    stubReverie(request);
    const { container } = render(<InteractiveView segment={segment()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("view vabc123 is not stored")).toBeTruthy();
    expect(container.querySelector("iframe")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试加载视图" }));
    await waitFor(() => {
      if (!container.querySelector("iframe")) throw new Error("iframe not rendered after retry");
    });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("shows the kernel error for a view_error segment and never calls getView", () => {
    const request = vi.fn();
    stubReverie(request);
    const { container } = render(
      <InteractiveView segment={segment({ status: "error", error: "artifact resolves outside the workspace", viewId: "", title: "", summary: "" })} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("artifact resolves outside the workspace");
    expect(container.querySelector("iframe")).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it("degrades to the summary for a view minted by a newer schema, without fetching", () => {
    const request = vi.fn();
    stubReverie(request);
    const { container } = render(<InteractiveView segment={segment({ schemaVersion: 2 })} />);
    expect(screen.getByText("Q3 bars.")).toBeTruthy();
    expect(container.querySelector("iframe")).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });
});

// RIU P2 host wiring: InteractiveView mounts the restricted ViewChannel + the
// ViewInteractionController against the live frame. These pin the host seam -- the
// capability is issued ONLY through the handshake, a message that lacks it never
// routes, an accepted gated call reaches the SAME frame as a JSON-RPC reply, and
// tearing the frame down drops any later message (no post into a dead frame).

type Posted = { id?: string | null; result?: Record<string, unknown>; error?: { message: string } };

async function readyFrame(request: ReturnType<typeof vi.fn>) {
  stubReverie(request);
  const utils = render(<InteractiveView segment={segment()} />);
  const frame = (await waitFor(() => {
    const found = utils.container.querySelector("iframe");
    if (!found) throw new Error("iframe not yet rendered");
    return found;
  })) as HTMLIFrameElement;
  const win = frame.contentWindow as Window;
  const posted: Posted[] = [];
  vi.spyOn(win, "postMessage").mockImplementation((message: unknown) => { posted.push(message as Posted); });
  return { ...utils, frame, win, posted };
}

function post(win: Window, data: Record<string, unknown>) {
  window.dispatchEvent(new MessageEvent("message", { source: win, data }));
}

describe("InteractiveView P2 interactivity", () => {
  it("initializes an unchanged standard component and keeps its transparent canvas on the host theme", async () => {
    const response = resolved();
    const toolResult = { content: [{ type: "text", text: "Public" }], _meta: { private: "UI only" } };
    const request = vi.fn().mockResolvedValue({ ...response, view: { ...response.view, mcpApp: { toolInput: { arguments: {} }, toolResult } } });
    const { win, posted, frame } = await readyFrame(request);
    expect(frame.style.background).toBe("var(--bg)");
    post(win, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: { protocolVersion: "2026-01-26", appInfo: { name: "Standard", version: "1" }, appCapabilities: {} } });
    expect(posted[0]).toMatchObject({ id: "init", result: { hostInfo: { name: "Reverie", version: desktopVersion } } });
    post(win, { jsonrpc: "2.0", method: "ui/notifications/initialized" });
    expect(posted).toEqual(expect.arrayContaining([
      expect.objectContaining({ method: "ui/notifications/tool-input", params: { arguments: {} } }),
      expect.objectContaining({ method: "ui/notifications/tool-result", params: toolResult }),
    ]));
  });

  it("a frame claiming user-gesture can only stage a proposal until the host button is clicked", async () => {
    const request = vi.fn().mockResolvedValue(resolved());
    const listener = vi.fn((event: Event) => event.preventDefault());
    window.addEventListener("reverie:view-followup", listener);
    try {
      const { win, posted } = await readyFrame(request);
      post(win, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: {} });
      const capability = String(posted[0].result?.capability);
      post(win, { jsonrpc: "2.0", method: "ui/notifications/initialized", capability });
      post(win, { jsonrpc: "2.0", id: "auto", method: "ui/message", capability, params: { source: "user-gesture", text: "Explain selection" } });
      const confirm = await screen.findByRole("button", { name: "发送追问" });
      expect(listener).not.toHaveBeenCalled();
      fireEvent.click(confirm);
      expect(listener).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "发送追问" })).toBeTruthy();
      window.removeEventListener("reverie:view-followup", listener);
      fireEvent.click(confirm);
      expect(screen.queryByRole("button", { name: "发送追问" })).toBeNull();
      expect(request).not.toHaveBeenCalledWith("runPrompt", expect.anything());
    } finally { window.removeEventListener("reverie:view-followup", listener); }
  });

  it("answers the frame handshake with a scoped capability and routes a gated tool call back", async () => {
    const request = vi.fn().mockImplementation((action: string) =>
      action === "getView"
        ? Promise.resolve(resolved())
        : Promise.resolve({ type: "view.tool_result", viewId: "vabc123", callId: "c1", status: "success", output: "ok", duplicate: false }),
    );
    const { win, posted } = await readyFrame(request);

    post(win, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: { protocolVersion: "1" } });
    await waitFor(() => expect(posted.length).toBeGreaterThan(0));
    const capability = String(posted[0].result?.capability ?? "");
    expect(capability.length).toBeGreaterThan(0);

    post(win, { jsonrpc: "2.0", method: "ui/notifications/initialized", capability });
    post(win, { jsonrpc: "2.0", id: "t1", method: "reverie/call-tool", capability, params: { toolName: "view_echo", callId: "c1", arguments: { text: "hi" }, source: "user-gesture" } });
    await waitFor(() => expect(request).toHaveBeenCalledWith("callViewTool", expect.objectContaining({ viewId: "vabc123", toolName: "view_echo", callId: "c1", source: "component" })));
    await waitFor(() => expect(posted.some((m) => m.id === "t1")).toBe(true));
    expect(posted.find((m) => m.id === "t1")?.result?.status).toBe("success");
  });

  it("ignores a frame message that never presented the issued capability", async () => {
    const request = vi.fn().mockImplementation((action: string) =>
      action === "getView" ? Promise.resolve(resolved()) : Promise.resolve({ type: "view.tool_result", viewId: "vabc123", callId: "c1", status: "success" }),
    );
    const { win } = await readyFrame(request);
    post(win, { jsonrpc: "2.0", id: "t1", method: "reverie/call-tool", capability: "guessed", params: { toolName: "view_echo", callId: "c1" } });
    await new Promise((r) => setTimeout(r, 25));
    expect(request).not.toHaveBeenCalledWith("callViewTool", expect.anything());
  });

  it("drops a late frame message after the view is torn down", async () => {
    const request = vi.fn().mockImplementation((action: string) =>
      action === "getView" ? Promise.resolve(resolved()) : Promise.resolve({ type: "view.tool_result", viewId: "vabc123", callId: "c1", status: "success" }),
    );
    const { win, posted, unmount } = await readyFrame(request);
    post(win, { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: {} });
    await waitFor(() => expect(posted.length).toBeGreaterThan(0));
    const capability = String(posted[0].result?.capability ?? "");
    unmount();
    post(win, { jsonrpc: "2.0", id: "t1", method: "reverie/call-tool", capability, params: { toolName: "view_echo", callId: "c1", source: "user-gesture" } });
    await new Promise((r) => setTimeout(r, 25));
    expect(request).not.toHaveBeenCalledWith("callViewTool", expect.anything());
  });
});
