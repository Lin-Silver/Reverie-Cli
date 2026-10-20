import { describe, expect, it } from "vitest";
import {
  BRIDGE_METHODS,
  BRIDGE_RATE_LIMIT,
  BRIDGE_REQUEST_TIMEOUT_MS,
  MAX_BRIDGE_MESSAGE_BYTES,
  MAX_BRIDGE_PENDING_REQUESTS,
  ViewChannel,
} from "./view-bridge";

const frame = { name: "view" };
const other = { name: "impostor" };
function channel(now?: () => number) { return new ViewChannel({ source: frame, sessionId: "session-a", viewId: "view-a", revision: 1, capability: "capability-token", now }); }
const envelope = (method: string, extra: Record<string, unknown> = {}) => ({ jsonrpc: "2.0", method, capability: "capability-token", ...extra });
function handshake(bridge: ViewChannel) { const verdict = bridge.accept({ source: frame, data: { jsonrpc: "2.0", id: "init", method: "ui/initialize", params: { protocolVersion: "1" } } }); bridge.settle("init"); bridge.accept({ source: frame, data: envelope("ui/notifications/initialized") }); return verdict; }

describe("restricted view bridge", () => {
  it("issues the instance capability only through the handshake and refuses traffic before it", () => {
    const bridge = channel();
    expect(BRIDGE_METHODS).toContain("ui/initialize");
    expect(BRIDGE_METHODS).toContain("tools/call");
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "1", params: {} }) })).toEqual({ accepted: false, reason: "not-initialized" });
    const verdict = handshake(bridge);
    expect(verdict).toMatchObject({ accepted: true, method: "ui/initialize", id: "init", capabilityIssued: "capability-token" });
    expect(bridge.accept({ source: frame, data: { jsonrpc: "2.0", id: "again", method: "ui/initialize" } })).toEqual({ accepted: false, reason: "duplicate-request" });
    expect(bridge.accept({ source: frame, data: envelope("ui/notifications/initialized") })).toMatchObject({ accepted: true, id: null });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "m1", params: { text: "user asked" } }) })).toMatchObject({ accepted: true, method: "ui/message", id: "m1" });
  });

  it("admits the private reverie/call-tool trigger and the standard tools/call name", () => {
    const bridge = channel();
    expect(BRIDGE_METHODS).toContain("reverie/call-tool");
    expect(BRIDGE_METHODS).toContain("tools/call");
    handshake(bridge);
    expect(bridge.accept({ source: frame, data: envelope("reverie/call-tool", { id: "t1", params: { toolName: "view_echo", callId: "c1", source: "user-gesture" } }) }))
      .toMatchObject({ accepted: true, method: "reverie/call-tool", id: "t1" });
    expect(bridge.accept({ source: frame, data: envelope("tools/call", { id: "t2", params: {} }) })).toMatchObject({ accepted: true, method: "tools/call" });
  });

  it("binds every message to the registered window, instance capability and live revision", () => {
    const bridge = channel();
    handshake(bridge);
    expect(bridge.accept({ source: other, data: envelope("ui/message", { id: "x" }) })).toEqual({ accepted: false, reason: "unknown-source" });
    expect(bridge.accept({ source: undefined, data: envelope("ui/message", { id: "x" }) })).toEqual({ accepted: false, reason: "unknown-source" });
    expect(bridge.accept({ source: frame, data: { jsonrpc: "2.0", method: "ui/message", id: "x" } })).toEqual({ accepted: false, reason: "missing-capability" });
    expect(bridge.accept({ source: frame, data: { jsonrpc: "2.0", method: "ui/message", id: "x", capability: "guessed" } })).toEqual({ accepted: false, reason: "missing-capability" });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "x", revision: 2 }) })).toEqual({ accepted: false, reason: "stale-instance" });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "x", sessionId: "session-b" }) })).toEqual({ accepted: false, reason: "stale-instance" });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "x", viewId: "view-b" }) })).toEqual({ accepted: false, reason: "stale-instance" });
    bridge.revoke();
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "y" }) })).toEqual({ accepted: false, reason: "revoked" });
  });

  it("rejects malformed envelopes, unknown methods and oversized payloads", () => {
    const bridge = channel();
    handshake(bridge);
    for (const data of ["plain string", 42, null, undefined, []]) expect(bridge.accept({ source: frame, data })).toEqual({ accepted: false, reason: "malformed" });
    expect(bridge.accept({ source: frame, data: { method: "ui/message", capability: "capability-token" } })).toEqual({ accepted: false, reason: "malformed" });
    expect(bridge.accept({ source: frame, data: envelope("files/delete", { id: "1" }) })).toEqual({ accepted: false, reason: "unsupported-method" });
    expect(bridge.accept({ source: frame, data: envelope("core:request", { id: "1" }) })).toEqual({ accepted: false, reason: "unsupported-method" });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: { nested: true } }) })).toEqual({ accepted: false, reason: "malformed" });
    const cyclic: Record<string, unknown> = envelope("ui/message", { id: "c" });
    cyclic.self = cyclic;
    expect(bridge.accept({ source: frame, data: cyclic })).toEqual({ accepted: false, reason: "malformed" });
    expect(bridge.accept({ source: frame, data: envelope("ui/message", { id: "big", params: { text: "x".repeat(MAX_BRIDGE_MESSAGE_BYTES) } }) })).toEqual({ accepted: false, reason: "oversize" });
  });

  it("caps burst rate, concurrent requests, duplicates and request lifetime under a message flood", () => {
    let clock = 1_000;
    const bridge = channel(() => clock);
    handshake(bridge);
    const flood = Array.from({ length: BRIDGE_RATE_LIMIT.messages + 40 }, (_, index) => bridge.accept({ source: frame, data: envelope("ui/notifications/initialized", { seq: index }) }));
    expect(flood.filter(verdict => verdict.accepted)).toHaveLength(BRIDGE_RATE_LIMIT.messages - 2);
    expect(flood.filter(verdict => !verdict.accepted && verdict.reason === "rate-limited")).toHaveLength(42);
    clock += BRIDGE_RATE_LIMIT.windowMs + 1;
    expect(bridge.accept({ source: frame, data: envelope("ui/notifications/initialized") })).toMatchObject({ accepted: true });

    const pending = channel(() => clock);
    handshake(pending);
    for (let index = 0; index < MAX_BRIDGE_PENDING_REQUESTS; index += 1) expect(pending.accept({ source: frame, data: envelope("reverie/view-state", { id: `r${index}` }) })).toMatchObject({ accepted: true });
    expect(pending.accept({ source: frame, data: envelope("reverie/view-state", { id: "overflow" }) })).toEqual({ accepted: false, reason: "too-many-pending" });
    expect(pending.accept({ source: frame, data: envelope("reverie/view-state", { id: "r0" }) })).toEqual({ accepted: false, reason: "duplicate-request" });
    expect(pending.settle("r0")).toBe(true);
    expect(pending.settle("r0")).toBe(false);
    expect(pending.accept({ source: frame, data: envelope("reverie/view-state", { id: "accepted-after-settle" }) })).toMatchObject({ accepted: true });
    clock += BRIDGE_REQUEST_TIMEOUT_MS + 1;
    expect(pending.expire()).toContain("r1");
    expect(pending.accept({ source: frame, data: envelope("reverie/view-state", { id: "r1" }) })).toEqual({ accepted: false, reason: "duplicate-request" });
    expect(pending.stats.byReason["rate-limited"] ?? 0).toBe(0);
    expect(bridge.stats.accepted).toBe(BRIDGE_RATE_LIMIT.messages + 1);
    expect(bridge.stats.rejected).toBe(42);
  });
});
