import path from "node:path";
import { describe, expect, it } from "vitest";
import { BROWSER_PROTOCOL, browserId, browserRequest, browserSummaryUrl, browserTitle, browserUrl, observedPage, pngDimensions } from "./browser-policy";

const request = (action: unknown = { action: "list" }) => ({
  protocol: BROWSER_PROTOCOL, request_id: "request-1", host: { host_id: "host-1", generation: "generation-1" },
  scope: { project_root: path.resolve("."), session_id: "session-1", run_id: "run-1" },
  profile: { mode: "ephemeral", profile_id: "profile-1" }, action,
});
const target = { tab_id: "tab-1", observation_id: "observe-1", revision: 1 };
const element = () => ({ element_id: "e0", role: "button", name: "Save", text: "Save", editable: false,
  bounds: { x: 10, y: 20, width: 100, height: 40 }, point: { x: 60, y: 40 } });
const page = () => ({ viewport: { width: 800, height: 600, device_scale_factor: 1.25 }, elements: [element()] });

describe("browser host input policy", () => {
  it("requires explicit profile and only accepts the finite generated actions", () => {
    for (const action of [
      { action: "list" }, { action: "open", url: "https://example.invalid/" }, { action: "observe", tab_id: "tab-1" },
      { action: "click", target, element_id: "e0" }, { action: "type", target, element_id: "e0", text: "中文\n😀", replace: true },
      { action: "scroll", target, element_id: null, delta_x: -10000, delta_y: 10000 }, { action: "key", target, key: "arrow_down", shift: false },
      { action: "navigate", target, url: "about:blank" }, { action: "close", target },
    ]) expect(browserRequest(request(action)).action).toEqual(action);
    const missing = request() as Record<string, unknown>; delete missing.profile;
    expect(() => browserRequest(missing)).toThrow();
    expect(() => browserRequest(request({ action: "evaluate", script: "process.exit()" }))).toThrow();
    expect(() => browserRequest(request({ action: "key", target, key: "control+v", shift: false }))).toThrow();
    expect(() => browserRequest(request({ action: "list", command: "Network.getCookies" }))).toThrow();
  });

  it("detaches caller objects and enforces host, scope and revision structure", () => {
    const source = request({ action: "close", target: { ...target } });
    const parsed = browserRequest(source);
    source.host.host_id = "mutated"; (source.action as { target: typeof target }).target.revision = 20;
    expect(parsed.host.host_id).toBe("host-1");
    expect(parsed.action).toEqual({ action: "close", target });
    for (const value of [
      { ...request(), protocol: "other" }, { ...request(), host: { host_id: "bad id", generation: "g" } },
      { ...request(), scope: { project_root: "relative", session_id: "s", run_id: "r" } },
      request({ action: "close", target: { ...target, revision: Number.MAX_SAFE_INTEGER + 1 } }),
      request({ action: "close", target: { ...target, revision: 0 } }),
    ]) expect(() => browserRequest(value)).toThrow();
  });

  it("keeps script-like text as data and measures UTF-8 bytes rather than characters", () => {
    const payload = '`); process.exit(); //\n${secret}';
    expect(browserRequest(request({ action: "type", target, element_id: "e0", text: payload, replace: false })).action).toEqual({ action: "type", target, element_id: "e0", text: payload, replace: false });
    for (const text of ["x\0y", "中".repeat(21846)]) expect(() => browserRequest(request({ action: "type", target, element_id: "e0", text, replace: false }))).toThrow();
    expect(() => browserRequest(request({ action: "scroll", target, element_id: null, delta_x: 0.5, delta_y: 0 }))).toThrow();
    expect(() => browserRequest(request({ action: "scroll", target, element_id: null, delta_x: 0, delta_y: 10001 }))).toThrow();
  });

  it("rejects local, script, credentialed and control-character URLs", () => {
    for (const value of ["file:///C:/secret", "javascript:alert(1)", "data:text/html,hi", "chrome://settings", "blob:https://example.invalid/a", "https://user:password@example.invalid/", "https://example.invalid/\n", "https://example.invalid/\u0085", "https://example.invalid/" + "中".repeat(3000)]) expect(browserUrl(value), value.slice(0, 80)).toBe(false);
    for (const value of ["about:blank", "https://example.invalid/a?q=中文", "http://127.0.0.1:8080/"]) expect(browserUrl(value)).toBe(true);
    expect(browserId("a".repeat(256))).toBe(true); expect(browserId("a".repeat(257))).toBe(false); expect(browserId("中文")).toBe(false);
  });
});

describe("browser observation policy", () => {
  it("binds actual frame identity and keeps private hit points outside the public DTO", () => {
    const parsed = observedPage(page(), "real-main-frame");
    expect(parsed.viewport.device_scale_factor).toBe(1.25);
    expect(parsed.elements[0].element).toEqual({ ...element(), frame_id: "real-main-frame", point: undefined });
    expect(Object.keys(parsed.elements[0].element)).not.toContain("point");
    expect(parsed.elements[0].point).toEqual({ x: 60, y: 40 });
  });

  it("rejects invisible, out-of-viewport, repeated, oversized and malformed elements", () => {
    for (const modify of [
      (p: ReturnType<typeof page>) => { p.viewport.width = NaN; },
      (p: ReturnType<typeof page>) => { p.viewport.device_scale_factor = 17; },
      (p: ReturnType<typeof page>) => { p.elements[0].bounds.width = 0; },
      (p: ReturnType<typeof page>) => { p.elements[0].bounds.x = 750; },
      (p: ReturnType<typeof page>) => { p.elements[0].point.x = 110; },
      (p: ReturnType<typeof page>) => { p.elements.push(element()); },
      (p: ReturnType<typeof page>) => { p.elements[0].text = "中".repeat(6000); },
      (p: ReturnType<typeof page>) => { p.elements = Array.from({ length: 257 }, (_, i) => ({ ...element(), element_id: `e${i}` })); },
    ]) { const fixture = page(); modify(fixture); expect(() => observedPage(fixture, "frame-1")).toThrow(); }
    const large = page(); large.elements = Array.from({ length: 40 }, (_, i) => ({ ...element(), element_id: `e${i}`, text: "x".repeat(16000) }));
    expect(() => observedPage(large, "frame-1")).toThrow("too large");
  });

  it("redacts URL query and fragment from summaries and bounds titles without splitting UTF-8", () => {
    expect(browserSummaryUrl("https://user:secret@example.invalid/a?token=hidden#secret")).toBe("https://example.invalid/a");
    const title = browserTitle("中文😀".repeat(1000));
    expect(Buffer.byteLength(title)).toBeLessThanOrEqual(4096); expect(title).not.toContain("�");
    expect(browserTitle("a\n\0\u0085b")).toBe("a   b");
  });

  it("reads real PNG IHDR dimensions and refuses non-PNG or excessive returns", () => {
    const png = Buffer.alloc(33); Buffer.from([137,80,78,71,13,10,26,10]).copy(png); png.writeUInt32BE(13, 8); png.write("IHDR", 12); png.writeUInt32BE(1250, 16); png.writeUInt32BE(750, 20);
    expect(pngDimensions(png)).toEqual({ width: 1250, height: 750 });
    png.writeUInt32BE(16385, 16); expect(() => pngDimensions(png)).toThrow();
    expect(() => pngDimensions(Buffer.from("not png"))).toThrow();
  });
});
