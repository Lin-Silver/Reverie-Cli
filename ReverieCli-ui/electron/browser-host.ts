import { randomUUID } from "node:crypto";
import { WebContentsView, session } from "electron";
import type { BrowserWindow, Session } from "electron";
import type { AdapterResult, BrowserCompletion, BrowserHostRef, BrowserProfile, BrowserRequest, BrowserScope, BrowserTab, Delivery } from "../src/generated/core-types";
import { BROWSER_PROTOCOL, browserId, browserRequest, browserSummaryUrl, browserTitle, browserUrl } from "./browser-policy";

export interface BrowserInvalidation {
  host: BrowserHostRef;
  scope: BrowserScope;
  profile: BrowserProfile;
  tab_id: string;
  revision: number;
  closed?: boolean;
}

export interface BrowserHostState {
  host: BrowserHostRef;
  disposed: boolean;
  frame_support: "main_frame_and_open_shadow";
  busy: number;
  tabs: { tab: BrowserTab; scope: BrowserScope; profile: BrowserProfile; loading: boolean; available: boolean; active: boolean }[];
}

export interface BrowserHostOptions {
  parent: BrowserWindow;
  host: BrowserHostRef;
  /** Must return a dedicated guest Session; profile sharing policy belongs to the application. */
  resolveSession(scope: BrowserScope, profile: BrowserProfile): Session | Promise<Session>;
  onInvalidated(invalidation: BrowserInvalidation): void | Promise<void>;
  onChanged(state: BrowserHostState): void;
}

interface Guest {
  id: string;
  owner: string;
  scope: BrowserScope;
  profile: BrowserProfile;
  view: WebContentsView;
  revision: number;
  announced: boolean;
  unavailable: boolean;
  closed: boolean;
  notifications: Promise<void>;
  notificationError: boolean;
  lastReported?: BrowserTab;
}

interface ActiveRequest {
  request: BrowserRequest;
  owner: string;
  started: boolean;
  cancelled: boolean;
  settled: boolean;
  guest?: Guest;
  resolve(completion: BrowserCompletion): void;
}

function ownerOf(scope: BrowserScope, profile: BrowserProfile): string {
  return JSON.stringify([scope.project_root, scope.session_id, scope.run_id, profile.mode, profile.profile_id]);
}

function completion(request: BrowserRequest, result: AdapterResult | Delivery): BrowserCompletion {
  return { protocol: BROWSER_PROTOCOL, request_id: request.request_id, host: { ...request.host }, scope: { ...request.scope }, profile: { ...request.profile },
    outcome: typeof result === "string" ? { status: "failed", delivery: result } : { status: "completed", result } };
}

/** Main-process adapter. Remote guests have neither an application preload nor a core token. */
export class BrowserHost {
  private readonly options: BrowserHostOptions;
  private readonly tabs = new Map<string, Guest>();
  private readonly active = new Map<string, ActiveRequest>();
  private readonly busy = new Set<string>();
  private readonly configured = new WeakSet<Session>();
  private bounds: Electron.Rectangle;
  private visible = false;
  private selected?: string;
  private disposed = false;
  private readonly parentClosed = () => { void this.dispose(); };

  constructor(options: BrowserHostOptions) {
    if (!browserId(options.host.host_id) || !browserId(options.host.generation) || options.parent.isDestroyed()) throw new Error("Invalid browser host.");
    this.options = { ...options, host: { ...options.host } };
    const [width, height] = options.parent.getContentSize();
    this.bounds = { x: 0, y: 0, width: Math.max(1, width), height: Math.max(1, height) };
    options.parent.once("closed", this.parentClosed);
  }

  async receive(input: BrowserRequest): Promise<BrowserCompletion> {
    const request = browserRequest(input);
    const owner = ownerOf(request.scope, request.profile);
    if (this.disposed || request.host.host_id !== this.options.host.host_id || request.host.generation !== this.options.host.generation
      || this.active.has(request.request_id) || this.busy.has(owner)) return Promise.resolve(completion(request, "not_started"));
    const promise = new Promise<BrowserCompletion>(resolve => {
      const context: ActiveRequest = { request, owner, started: false, cancelled: false, settled: false, resolve };
      this.active.set(request.request_id, context); this.busy.add(owner);
      const release = () => { this.active.delete(request.request_id); this.busy.delete(owner); this.changed(); };
      void Promise.resolve().then(() => this.dispatch(context)).then(result => { release(); this.finish(context, result); }, () => { release(); this.finish(context, context.started ? "unknown" : "not_started"); });
    });
    this.changed();
    return promise;
  }

  cancel(requestId: string): void {
    const context = this.active.get(requestId);
    if (!context || context.settled) return;
    context.cancelled = true;
    this.finish(context, context.started ? "unknown" : "not_started");
    // Keep the ownership slot until any in-flight native operation and release cleanup settle.
  }

  state(): BrowserHostState {
    return { host: { ...this.options.host }, disposed: this.disposed, frame_support: "main_frame_and_open_shadow", busy: this.busy.size,
      tabs: Array.from(this.tabs.values()).map(guest => ({ tab: { ...this.tabRecord(guest), url: browserSummaryUrl(guest.view.webContents.getURL()) },
        scope: { ...guest.scope }, profile: { ...guest.profile }, loading: guest.view.webContents.isLoading(),
        available: !guest.unavailable && !guest.closed, active: guest.id === this.selected })) };
  }

  setBounds(bounds: Electron.Rectangle): void {
    if (![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isSafeInteger) || bounds.x < 0 || bounds.y < 0
      || bounds.width < 1 || bounds.height < 1 || bounds.width > 16384 || bounds.height > 16384) throw new Error("Invalid browser view bounds.");
    if (JSON.stringify(bounds) === JSON.stringify(this.bounds)) return;
    this.bounds = { ...bounds };
    for (const guest of this.tabs.values()) { guest.view.setBounds(this.bounds); this.invalidate(guest); }
    this.changed();
  }

  setVisible(visible: boolean, tabId?: string): void {
    if (tabId !== undefined) {
      if (!this.tabs.has(tabId)) throw new Error("Unknown browser tab.");
      this.selected = tabId;
    }
    this.visible = visible;
    for (const guest of this.tabs.values()) guest.view.setVisible(visible && guest.id === this.selected);
    this.changed();
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.options.parent.removeListener("closed", this.parentClosed);
    for (const context of this.active.values()) this.cancel(context.request.request_id);
    const guests = Array.from(this.tabs.values());
    for (const guest of guests) this.closeGuest(guest);
    await Promise.all(guests.map(guest => guest.notifications));
    this.changed();
    // The injected Session resolver owns profile storage and its retention policy.
  }

  private check(context: ActiveRequest): void {
    if (context.cancelled || this.disposed || context.guest?.closed || context.guest?.unavailable) throw new Error("Browser request is unavailable.");
  }

  private finish(context: ActiveRequest, result: AdapterResult | Delivery): void {
    if (context.settled) return;
    context.settled = true;
    context.resolve(completion(context.request, result));
  }

  private changed(): void {
    try { this.options.onChanged(this.state()); } catch { /* A display callback cannot replay a browser operation. */ }
  }

  private bump(guest: Guest): void {
    if (guest.revision === Number.MAX_SAFE_INTEGER) { guest.unavailable = true; throw new Error("Browser revision exhausted."); }
    guest.revision++;
  }

  private invalidate(guest: Guest, closed = false): void {
    if (guest.closed && !closed) return;
    this.bump(guest);
    if (guest.announced) {
      const invalidation: BrowserInvalidation = { host: { ...this.options.host }, scope: { ...guest.scope }, profile: { ...guest.profile }, tab_id: guest.id, revision: guest.revision, ...(closed ? { closed: true } : {}) };
      guest.notifications = guest.notifications.then(() => this.options.onInvalidated(invalidation)).then(() => undefined, () => { guest.notificationError = true; guest.unavailable = true; });
    }
    this.changed();
  }

  private tabRecord(guest: Guest): BrowserTab {
    const url = guest.view.webContents.getURL() || "about:blank";
    if (!browserUrl(url)) throw new Error("Unsupported browser navigation.");
    return { tab_id: guest.id, revision: guest.revision, url, title: browserTitle(guest.view.webContents.getTitle()) };
  }

  private async report(guest: Guest, advance: boolean): Promise<BrowserTab> {
    await guest.notifications;
    if (guest.notificationError || guest.closed || guest.unavailable) throw new Error("Browser tab is unavailable.");
    const current = this.tabRecord(guest);
    if (advance || guest.lastReported && current.url !== guest.lastReported.url) this.bump(guest);
    const record = this.tabRecord(guest);
    guest.lastReported = { ...record }; guest.announced = true;
    return record;
  }

  private guest(context: ActiveRequest, tabId: string): Guest {
    const guest = this.tabs.get(tabId);
    if (!guest || guest.owner !== context.owner || guest.closed || guest.unavailable) throw new Error("Browser tab ownership does not match.");
    context.guest = guest;
    return guest;
  }

  private configureSession(guestSession: Session): void {
    if (guestSession === session.defaultSession) throw new Error("Browser guests require a dedicated Session.");
    if (this.configured.has(guestSession)) return;
    guestSession.setPermissionCheckHandler(() => false);
    guestSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    guestSession.setDevicePermissionHandler(() => false);
    guestSession.setDisplayMediaRequestHandler((_request, callback) => callback({}));
    guestSession.setBluetoothPairingHandler((_details, callback) => callback({ confirmed: false }));
    guestSession.on("will-download", event => event.preventDefault());
    this.configured.add(guestSession);
  }

  private async createGuest(context: ActiveRequest): Promise<Guest> {
    const guestSession = await this.options.resolveSession({ ...context.request.scope }, { ...context.request.profile });
    this.check(context); this.configureSession(guestSession);
    if (this.tabs.size >= 1024 || Array.from(this.tabs.values()).filter(guest => guest.owner === context.owner).length >= 64) throw new Error("Browser tab limit reached.");
    context.started = true;
    const view = new WebContentsView({ webPreferences: { session: guestSession, sandbox: true, contextIsolation: true, nodeIntegration: false,
      nodeIntegrationInWorker: false, nodeIntegrationInSubFrames: false, webviewTag: false, webSecurity: true,
      allowRunningInsecureContent: false, navigateOnDragDrop: false, disableDialogs: true, safeDialogs: true, devTools: false, spellcheck: false } });
    const guest: Guest = { id: `tab-${randomUUID()}`, owner: context.owner, scope: { ...context.request.scope }, profile: { ...context.request.profile },
      view, revision: 1, announced: false, unavailable: false, closed: false, notifications: Promise.resolve(), notificationError: false };
    context.guest = guest; this.tabs.set(guest.id, guest);
    this.selected = guest.id; this.options.parent.contentView.addChildView(view); view.setBounds(this.bounds); this.setVisible(this.visible);
    const contents = view.webContents;
    contents.setWindowOpenHandler(() => ({ action: "deny" }));
    contents.on("will-attach-webview", event => event.preventDefault());
    contents.on("will-frame-navigate", event => { if (!browserUrl(event.url)) event.preventDefault(); });
    contents.on("will-navigate", event => { if (!browserUrl(event.url)) event.preventDefault(); });
    contents.on("will-redirect", event => { if (!browserUrl(event.url)) event.preventDefault(); });
    contents.on("did-start-navigation", () => this.invalidate(guest));
    contents.on("did-navigate-in-page", () => this.invalidate(guest));
    contents.on("did-frame-navigate", () => this.invalidate(guest));
    contents.on("page-title-updated", () => this.invalidate(guest));
    contents.on("render-process-gone", () => { guest.unavailable = true; this.invalidate(guest); for (const active of this.active.values()) if (active.guest === guest) this.cancel(active.request.request_id); });
    contents.once("destroyed", () => this.retireGuest(guest));
    contents.debugger.on("detach", () => { if (!guest.closed) { guest.unavailable = true; this.invalidate(guest); for (const active of this.active.values()) if (active.guest === guest) this.cancel(active.request.request_id); } });
    try {
      contents.debugger.attach("1.3");
      await contents.debugger.sendCommand("Page.enable"); this.check(context);
      await contents.debugger.sendCommand("Runtime.enable"); this.check(context);
      await contents.debugger.sendCommand("Page.setInterceptFileChooserDialog", { enabled: true, cancel: true }); this.check(context);
      return guest;
    } catch (error) { this.closeGuest(guest); throw error; }
  }

  private retireGuest(guest: Guest): void {
    if (guest.closed) return;
    guest.closed = true;
    this.invalidate(guest, true);
    this.tabs.delete(guest.id);
    if (this.selected === guest.id) this.selected = this.tabs.keys().next().value;
    for (const active of this.active.values()) if (active.guest === guest && active.request.action.action !== "close") this.cancel(active.request.request_id);
    this.changed();
  }

  private closeGuest(guest: Guest): void {
    if (guest.closed) return;
    if (!this.options.parent.isDestroyed()) this.options.parent.contentView.removeChildView(guest.view);
    this.retireGuest(guest);
    if (guest.view.webContents.debugger.isAttached()) guest.view.webContents.debugger.detach();
    if (!guest.view.webContents.isDestroyed()) guest.view.webContents.close({ waitForBeforeUnload: false });
    guest.view.webContents.removeAllListeners(); guest.view.webContents.debugger.removeAllListeners();
    this.setVisible(this.visible);
  }

  private async dispatch(context: ActiveRequest): Promise<AdapterResult> {
    this.check(context);
    const action = context.request.action;
    if (action.action === "open") {
      const guest = await this.createGuest(context);
      try {
        this.check(context); await guest.view.webContents.loadURL(action.url); this.check(context);
        return { type: "opened", tab: await this.report(guest, true) };
      } catch (error) { this.closeGuest(guest); throw error; }
    }
    if (action.action === "list") {
      const tabs: BrowserTab[] = [];
      for (const guest of this.tabs.values()) if (guest.owner === context.owner && !guest.closed && !guest.unavailable) tabs.push(await this.report(guest, false));
      this.check(context); context.started = true;
      return { type: "listed", tabs };
    }
    throw new Error("Browser action is not available in this implementation slice.");
  }
}
