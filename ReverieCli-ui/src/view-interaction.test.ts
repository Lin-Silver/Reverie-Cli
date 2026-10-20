import { describe, expect, it, vi } from "vitest";
import {
  ViewInteractionController,
  type FrameReply,
  type ViewInteractionDeps,
} from "./view-interaction";

type Call = { action: string; payload: Record<string, unknown> };

function harness(overrides: Partial<ViewInteractionDeps> = {}) {
  const calls: Call[] = [];
  const responses = new Map<string, Record<string, unknown>>();
  const followUps: Array<{ text: string; source: string }> = [];
  let resolveGate: (() => void) | null = null;

  const request = vi.fn(async (action: string, payload: Record<string, unknown>) => {
    calls.push({ action, payload });
    if (resolveGate) await new Promise<void>((resolve) => { resolveGate = resolve; });
    const canned = responses.get(action);
    if (canned) return { ...canned };
    if (action === "callViewTool") {
      return { type: "view.tool_result", viewId: payload.viewId, callId: payload.callId, status: "success", output: "ok", data: {}, duplicate: false };
    }
    if (action === "updateViewModelContext") return { type: "view.model_context", status: "stored" };
    if (action === "setViewState") return { type: "view.state", revision: 2 };
    return { type: "error", error: "unexpected" };
  });

  const deps: ViewInteractionDeps = {
    ref: { sessionId: "session-a", viewId: "view-a", revision: 1 },
    request,
    onFollowUp: (text, source) => followUps.push({ text, source }),
    ...overrides,
  };
  const controller = new ViewInteractionController(deps);
  return {
    controller, calls, responses, followUps, request,
    arm() { resolveGate = () => {}; },
    release() { const r = resolveGate; resolveGate = null; r?.(); },
  };
}

const toolVerdict = (over: Record<string, unknown> = {}) => ({
  method: "reverie/call-tool" as const,
  id: "rpc-1",
  params: { toolName: "view_echo", arguments: { text: "hi" }, callId: "call-A", source: "user-gesture", ...over },
});

describe("RIU P2 view interaction controller", () => {
  it("funnels reverie/call-tool into the gated callViewTool action with the bound view id", async () => {
    const h = harness();
    const reply = await h.controller.handle(toolVerdict({ viewId: "spoofed-view" }));

    expect(h.calls).toEqual([
      { action: "callViewTool", payload: { viewId: "view-a", toolName: "view_echo", arguments: { text: "hi" }, callId: "call-A", source: "component", sessionId: "session-a", revision: 1 } },
    ]);
    expect(reply.kind).toBe("response");
    const body = (reply as Extract<FrameReply, { kind: "response" }>).result as Record<string, unknown>;
    expect(body.status).toBe("success");
    expect(body.callId).toBe("call-A");
  });

  it("clamps an unknown source to component and defaults a missing source to component", async () => {
    const h = harness();
    await h.controller.handle(toolVerdict({ source: "root" }));
    await h.controller.handle(toolVerdict({ callId: "call-B", source: undefined }));
    expect(h.calls.map((c) => c.payload.source)).toEqual(["component", "component"]);
  });

  it("rejects a reverie/call-tool without a toolName or callId before any dispatch", async () => {
    const h = harness();
    const noTool = await h.controller.handle(toolVerdict({ toolName: "" }));
    const noCall = await h.controller.handle(toolVerdict({ callId: "" }));
    expect(noTool.kind).toBe("error");
    expect(noCall.kind).toBe("error");
    expect(h.calls).toEqual([]);
  });

  it("rejects a settled duplicate without dispatching it again", async () => {
    const h = harness();
    const first = await h.controller.handle(toolVerdict({ id: "rpc-1", callId: "dup" }));
    const second = await h.controller.handle(toolVerdict({ id: "rpc-2", callId: "dup" }));
    expect(h.calls).toHaveLength(1);
    expect(first.kind).toBe("response");
    expect(second.kind).toBe("error");
  });

  it("coalesces a concurrent duplicate callId onto a single in-flight dispatch", async () => {
    const h = harness();
    h.arm();
    const p1 = h.controller.handle(toolVerdict({ id: "rpc-1", callId: "dup" }));
    const p2 = h.controller.handle(toolVerdict({ id: "rpc-2", callId: "dup" }));
    h.release();
    await Promise.all([p1, p2]);
    expect(h.calls).toHaveLength(1);
  });

  it("drops a tool result that resolves after revoke instead of posting into a torn-down frame", async () => {
    const h = harness();
    h.arm();
    const pending = h.controller.handle(toolVerdict());
    h.controller.revoke();
    h.release();
    const reply = await pending;
    expect(reply.kind).toBe("drop");
    expect(h.controller.revoked).toBe(true);
  });

  it("refuses every method once revoked", async () => {
    const h = harness();
    h.controller.revoke();
    const reply = await h.controller.handle(toolVerdict());
    expect(reply).toEqual({ kind: "drop", reason: "revoked" });
    expect(h.calls).toEqual([]);
  });

  it("maps ui/update-model-context to updateViewModelContext with the bound view id", async () => {
    const h = harness();
    const reply = await h.controller.handle({ method: "ui/update-model-context", id: "u1", params: { summary: "safe blurb", source: "component" } });
    expect(h.calls).toEqual([{ action: "updateViewModelContext", payload: { viewId: "view-a", sessionId: "session-a", revision: 1, summary: "safe blurb" } }]);
    expect((reply as Extract<FrameReply, { kind: "response" }>).result).toEqual({});
  });

  it("maps reverie/view-state to setViewState with the bound view id and base revision", async () => {
    const h = harness();
    const reply = await h.controller.handle({ method: "reverie/view-state", id: "s1", params: { state: { tab: 2 }, baseRevision: 1 } });
    expect(h.calls).toEqual([{ action: "setViewState", payload: { viewId: "view-a", sessionId: "session-a", revision: 1, state: { tab: 2 }, baseRevision: 1 } }]);
    expect((reply as Extract<FrameReply, { kind: "response" }>).result).toMatchObject({ revision: 2 });
  });

  it("stages all messages as component proposals regardless of their claimed source", async () => {
    const h = harness();
    for (const source of ["user-gesture", "component", undefined]) {
      const reply = await h.controller.handle({ method: "ui/message", id: String(source), params: { role: "user", content: [{ type: "text", text: "proposal" }], source } });
      expect(reply).toMatchObject({ kind: "response", result: { pendingUserConfirmation: true } });
    }
    expect(h.followUps).toEqual(Array(3).fill({ text: "proposal", source: "component" }));
    expect(h.calls).toEqual([]);
  });

  it("routes standard tools/call and caps standard model context without a prompt", async () => {
    const h = harness();
    expect(await h.controller.handle({ method: "tools/call", id: "standard", params: { name: "view_echo", arguments: { text: "hi" } } })).toMatchObject({ kind: "response", result: { content: [{ type: "text", text: "ok" }], isError: false } });
    expect(h.calls[0].payload).toMatchObject({ callId: JSON.stringify("standard"), source: "component" });
    expect(await h.controller.handle({ method: "ui/update-model-context", id: "ctx", params: { content: [{ type: "text", text: "选中" }], structuredContent: { x: 3 } } })).toMatchObject({ kind: "response" });
    expect(h.calls[1].payload.summary).toContain("选中");
    expect(await h.controller.handle({ method: "ui/update-model-context", id: "big", params: { summary: "中".repeat(8192) } })).toMatchObject({ kind: "error" });
    expect(h.calls).toHaveLength(2);
  });

  it("drops a handshake or notification method without a core request", async () => {
    const h = harness();
    const init = await h.controller.handle({ method: "ui/initialize", id: "i", params: {} });
    const ack = await h.controller.handle({ method: "ui/notifications/initialized", id: null, params: {} });
    expect(init.kind).toBe("error");
    expect(ack.kind).toBe("drop");
    expect(h.calls).toEqual([]);
  });

  it("surfaces a kernel error (busy / restricted / denied) as a JSON-RPC error reply", async () => {
    const h = harness();
    h.responses.set("callViewTool", { type: "view.tool_result", viewId: "view-a", callId: "call-A", status: "error", error: "A run is already active in this executor." });
    const reply = await h.controller.handle(toolVerdict());
    expect(reply.kind).toBe("error");
    expect((reply as Extract<FrameReply, { kind: "error" }>).error.message).toContain("active");
  });
});
