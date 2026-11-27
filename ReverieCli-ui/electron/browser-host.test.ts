import { EventEmitter } from "node:events";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BrowserWindow, Session } from "electron";
import type { BrowserAction, BrowserRequest } from "../src/generated/core-types";
import { BROWSER_PROTOCOL } from "./browser-policy";

const mocks = vi.hoisted(() => ({ views: [] as unknown[], defaultSession: {}, load: undefined as undefined | ((url: string) => Promise<void>), command: undefined as undefined | ((method: string, params: unknown) => Promise<unknown>) }));
vi.mock("electron", async () => {
  const { EventEmitter } = await import("node:events");
  class Debugger extends EventEmitter {
    attached = false;
    attach() { this.attached = true; }
    isAttached() { return this.attached; }
    detach() { this.attached = false; this.emit("detach", {}, "requested"); }
    sendCommand(method: string, params?: unknown) { return mocks.command ? mocks.command(method, params) : Promise.resolve({}); }
  }
  class Contents extends EventEmitter {
    navigationHistory = { canGoBack: () => false, canGoForward: () => false };
    debugger = new Debugger();
    url = "about:blank"; title = "Fixture"; destroyed = false;
    windowOpen = undefined as undefined | (() => { action: string });
    async loadURL(url: string) { this.emit("did-start-navigation", { url }); await mocks.load?.(url); if (this.destroyed) throw new Error("Destroyed"); this.url = url; this.emit("did-frame-navigate", {}, url); }
    getURL() { return this.url; }
    getTitle() { return this.title; }
    isLoading() { return false; }
    isDestroyed() { return this.destroyed; }
    setWindowOpenHandler(handler: () => { action: string }) { this.windowOpen = handler; }
    close() { this.destroyed = true; this.emit("destroyed"); }
  }
  class WebContentsView {
    webContents = new Contents(); visible = false; bounds = {};
    constructor(readonly options: unknown) { mocks.views.push(this); }
    setBounds(bounds: unknown) { this.bounds = bounds; }
    setVisible(visible: boolean) { this.visible = visible; }
  }
  return { WebContentsView, session: { defaultSession: mocks.defaultSession } };
});
import { BrowserHost } from "./browser-host";

function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
interface FakeView { options: { webPreferences: Record<string, unknown> }; visible: boolean; webContents: EventEmitter & { url: string; destroyed: boolean; debugger: EventEmitter; windowOpen(): { action: string } } }
const hosts: BrowserHost[] = [];
function fixture(resolveSession?: () => Session | Promise<Session>) {
  const parent = new EventEmitter() as EventEmitter & { isDestroyed(): boolean; getContentSize(): number[]; contentView: { addChildView: ReturnType<typeof vi.fn>; removeChildView: ReturnType<typeof vi.fn> } };
  parent.isDestroyed = () => false; parent.getContentSize = () => [800, 600]; parent.contentView = { addChildView: vi.fn(), removeChildView: vi.fn() };
  const guestSession = { setPermissionCheckHandler: vi.fn(), setPermissionRequestHandler: vi.fn(), setDevicePermissionHandler: vi.fn(), setDisplayMediaRequestHandler: vi.fn(), setBluetoothPairingHandler: vi.fn(), on: vi.fn() };
  const onInvalidated = vi.fn(); const onChanged = vi.fn();
  const host = new BrowserHost({ parent: parent as unknown as BrowserWindow, host: { host_id: "host-1", generation: "generation-1" }, resolveSession: resolveSession ?? (() => guestSession as unknown as Session), onInvalidated, onChanged });
  hosts.push(host);
  return { host, parent, guestSession, onInvalidated, onChanged };
}
function request(action: BrowserAction = { action: "list" }, overrides: Partial<BrowserRequest> = {}): BrowserRequest {
  return { protocol: BROWSER_PROTOCOL, request_id: `request-${crypto.randomUUID()}`, host: { host_id: "host-1", generation: "generation-1" },
    scope: { project_root: path.resolve("."), session_id: "session-1", run_id: "run-1" }, profile: { mode: "ephemeral", profile_id: "profile-1" }, action, ...overrides };
}
function view(): FakeView { return mocks.views[mocks.views.length - 1] as FakeView; }
afterEach(async () => { for (const host of hosts.splice(0)) await host.dispose(); mocks.views.length = 0; mocks.load = undefined; mocks.command = undefined; });

describe("Electron browser host lifecycle", () => {
  it("lazily creates isolated guests and applies deny-by-default permissions", async () => {
    const { host, guestSession } = fixture();
    expect(mocks.views).toHaveLength(0);
    expect((await host.receive(request())).outcome).toEqual({ status: "completed", result: { type: "listed", tabs: [] } });
    const result = await host.receive(request({ action: "open", url: "https://example.invalid/?token=hidden#private" }));
    expect(result.outcome.status).toBe("completed");
    expect(view().options.webPreferences).toMatchObject({ show: true, sandbox: true, contextIsolation: true, nodeIntegration: false, nodeIntegrationInWorker: false, nodeIntegrationInSubFrames: false, webviewTag: false, webSecurity: true });
    expect(view().options.webPreferences).not.toHaveProperty("preload");
    expect(view().webContents.windowOpen()).toEqual({ action: "deny" });
    expect(guestSession.setPermissionCheckHandler.mock.calls[0][0]()).toBe(false);
    const reply = vi.fn(); guestSession.setPermissionRequestHandler.mock.calls[0][0]({}, "media", reply); expect(reply).toHaveBeenCalledWith(false);
    const preventDefault = vi.fn(); guestSession.on.mock.calls[0][1]({ preventDefault }); expect(preventDefault).toHaveBeenCalledOnce();
    expect(host.state().tabs[0].tab.url).toBe("https://example.invalid/");
  });

  it("binds tabs to the full ownership and explicit profile tuple", async () => {
    const { host } = fixture(); await host.receive(request({ action: "open", url: "about:blank" }));
    for (const overrides of [
      { scope: { ...request().scope, session_id: "other" } }, { scope: { ...request().scope, run_id: "other" } },
      { scope: { ...request().scope, project_root: path.resolve("..") } }, { profile: { mode: "persistent" as const, profile_id: "profile-1" } },
      { profile: { mode: "ephemeral" as const, profile_id: "other" } },
    ]) expect((await host.receive(request({ action: "list" }, overrides))).outcome).toEqual({ status: "completed", result: { type: "listed", tabs: [] } });
    const listed = await host.receive(request()); expect(listed.outcome.status === "completed" && listed.outcome.result.type === "listed" && listed.outcome.result.tabs).toHaveLength(1);
  });

  it("rejects mismatched hosts and the application's default Session before opening pages", async () => {
    const { host } = fixture(() => mocks.defaultSession as Session);
    expect((await host.receive(request({ action: "open", url: "about:blank" }))).outcome).toEqual({ status: "failed", delivery: "not_started" });
    expect((await host.receive(request({ action: "open", url: "about:blank" }, { host: { host_id: "host-1", generation: "wrong" } }))).outcome).toEqual({ status: "failed", delivery: "not_started" });
    expect(mocks.views).toHaveLength(0);
  });

  it("cancels before dispatch without creating guests or resolving profile storage", async () => {
    const resolveSession = vi.fn(); const { host } = fixture(resolveSession);
    const input = request({ action: "open", url: "about:blank" }); const pending = host.receive(input); host.cancel(input.request_id);
    expect((await pending).outcome).toEqual({ status: "failed", delivery: "not_started" });
    expect(resolveSession).not.toHaveBeenCalled(); expect(mocks.views).toHaveLength(0);
  });

  it("reports unknown after delivery begins and quarantines the owner until the native call settles", async () => {
    const loading = deferred<void>(), entered = deferred<void>(); mocks.load = async () => { entered.resolve(); await loading.promise; };
    const { host } = fixture(); const input = request({ action: "open", url: "https://example.invalid/" }); const pending = host.receive(input);
    await entered.promise; host.cancel(input.request_id);
    expect((await pending).outcome).toEqual({ status: "failed", delivery: "unknown" });
    expect((await host.receive(request())).outcome).toEqual({ status: "failed", delivery: "not_started" });
    expect(host.state().busy).toBe(1);
    loading.resolve(); await vi.waitFor(() => expect(host.state().busy).toBe(0));
    expect(view().webContents.destroyed).toBe(true); expect(host.state().tabs).toHaveLength(0);
  });

  it("moves stable list results without needless revision changes and invalidates resized views", async () => {
    const { host, onInvalidated } = fixture(); await host.receive(request({ action: "open", url: "about:blank" }));
    const first = host.state().tabs[0].tab.revision; await host.receive(request()); await host.receive(request());
    expect(host.state().tabs[0].tab.revision).toBe(first);
    host.setBounds({ x: 10, y: 20, width: 640, height: 480 });
    await host.receive(request()); expect(onInvalidated).toHaveBeenCalledOnce(); expect(host.state().tabs[0].tab.revision).toBeGreaterThan(first);
    expect(() => host.setBounds({ x: -1, y: 0, width: 640, height: 480 })).toThrow();
  });

  it("closes every guest rather than only removing its view and releases listeners", async () => {
    const { host, parent } = fixture(); await host.receive(request({ action: "open", url: "about:blank" })); const first = view();
    await host.receive(request({ action: "open", url: "about:blank" })); const second = view();
    host.setVisible(true, host.state().tabs[0].tab.tab_id); expect(first.visible).toBe(true); expect(second.visible).toBe(false);
    await host.dispose();
    expect(first.webContents.destroyed).toBe(true); expect(second.webContents.destroyed).toBe(true);
    expect(parent.contentView.removeChildView).toHaveBeenCalledTimes(2); expect(first.webContents.eventNames()).toEqual([]); expect(second.webContents.debugger.eventNames()).toEqual([]);
    expect((await host.receive(request())).outcome).toEqual({ status: "failed", delivery: "not_started" });
  });

  it("blocks dangerous navigations and retires a detached debugger without reloading", async () => {
    const { host } = fixture(); await host.receive(request({ action: "open", url: "about:blank" }));
    for (const name of ["will-frame-navigate", "will-navigate", "will-redirect"]) { const preventDefault = vi.fn(); view().webContents.emit(name, { url: "file:///C:/secret", preventDefault }); expect(preventDefault).toHaveBeenCalledOnce(); }
    view().webContents.debugger.emit("detach", {}, "DevTools");
    expect(host.state().tabs[0].available).toBe(false);
    expect((await host.receive(request())).outcome).toEqual({ status: "completed", result: { type: "listed", tabs: [] } });
    expect(mocks.views).toHaveLength(1);
  });
});
