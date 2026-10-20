import { describe, expect, it, vi } from "vitest";
import { ViewChannel } from "./view-bridge";
import { McpAppLifecycle } from "./mcp-app-lifecycle";

describe("standard MCP Apps transport", () => {
  it("refuses unknown versions and private RPC methods in the standard profile", () => {
    const source = {};
    for (const version of [undefined, "1", "2099-01-01"]) {
      const channel = new ViewChannel({ source, sessionId: "s", viewId: "v", revision: 1, capability: "host", standard: true });
      expect(channel.accept({ source, data: { jsonrpc: "2.0", id: 1, method: "ui/initialize", params: { protocolVersion: version } } })).toEqual({ accepted: false, reason: "unsupported-version" });
      expect(channel.initialized).toBe(false);
      expect(channel.accept({ source, data: { jsonrpc: "2.0", id: 2, method: "reverie/view-state", params: {} } })).toEqual({ accepted: false, reason: "unsupported-method" });
    }
  });

  it("uses the registered window and host lease without requiring proprietary envelope keys", () => {
    const source = {};
    const channel = new ViewChannel({ source, sessionId: "s", viewId: "v", revision: 1, capability: "private", standard: true });
    const send = (data: unknown, from = source) => channel.accept({ source: from, data });
    expect(send({ jsonrpc: "2.0", id: 1, method: "ui/initialize", params: { protocolVersion: "2026-01-26", appInfo: { name: "Official", version: "1" }, appCapabilities: {} } }).accepted).toBe(true);
    channel.settle(1);
    expect(send({ jsonrpc: "2.0", method: "ui/notifications/initialized" }).accepted).toBe(true);
    expect(send({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get-time", arguments: {} } }).accepted).toBe(true);
    expect(send({ jsonrpc: "2.0", id: 3, method: "tools/call", params: {} }, {}).accepted).toBe(false);
    channel.revoke();
    expect(send({ jsonrpc: "2.0", id: 4, method: "tools/call", params: {} }).accepted).toBe(false);
  });

  it("delivers input before result once, after initialized; never sends private data early", () => {
    const post = vi.fn();
    const source = {};
    const result = { content: [{ type: "text", text: "Public" }], _meta: { private: "Only UI" } };
    const lifecycle = new McpAppLifecycle(source, post, { toolInput: { arguments: { n: 2 } }, toolResult: result });
    expect(post).not.toHaveBeenCalled();
    lifecycle.ready(); lifecycle.ready();
    expect(post.mock.calls.map(x => x[0].method)).toEqual(["ui/notifications/tool-input", "ui/notifications/tool-result"]);
    expect(post.mock.calls[1][0].params).toEqual(result);
  });

  it("tears down with standard request/ack, rejects a foreign response and times out safely", async () => {
    vi.useFakeTimers();
    const post = vi.fn(); const source = {};
    const lifecycle = new McpAppLifecycle(source, post, { toolInput: {}, toolResult: {} });
    lifecycle.ready();
    const done = lifecycle.teardown();
    const request = post.mock.calls.at(-1)![0];
    expect(request.method).toBe("ui/resource-teardown");
    expect(lifecycle.receive({ source: {}, data: { jsonrpc: "2.0", id: request.id, result: {} } })).toBe(false);
    expect(lifecycle.receive({ source, data: { jsonrpc: "2.0", id: request.id, result: {} } })).toBe(true);
    await done;
    lifecycle.ready(); expect(post).toHaveBeenCalledTimes(3);
    const unresponsive = new McpAppLifecycle(source, post, { toolInput: {}, toolResult: {} });
    unresponsive.ready(); const timeout = unresponsive.teardown();
    await vi.advanceTimersByTimeAsync(500); await timeout;
    vi.useRealTimers();
  });
});
