/**
 * Session and frame guards for the generative-view host.
 *
 * Type-only Electron imports keep this module loadable outside a packaged app, so the same
 * guard wiring the probe measures is the wiring the production window installs.
 */

import type { Session, WebContents } from "electron";
import { VIEW_SCHEME, ViewHost, viewFrameNavigation, viewPermissionDecision, viewRequestToken } from "./view-host";

export type PermissionDecisionRecord = { permission: string; granted: boolean; isMainFrame: boolean; origin: string; kind: "request" | "check" | "device" | "display-media" };
export type NavigationRecord = { url: string; frameUrl: string; verdict: "allow" | "block" };
export type ViewGuardLog = {
  permissions: PermissionDecisionRecord[];
  navigations: NavigationRecord[];
  downloads: { url: string; cancelled: boolean }[];
  windowOpens: string[];
  blockedRequests: string[];
};

export type ViewProtocolHandler = (request: Request) => Promise<Response>;

export function createViewGuardLog(): ViewGuardLog {
  return { permissions: [], navigations: [], downloads: [], windowOpens: [], blockedRequests: [] };
}

/** Builds the `protocol.handle` callback for one host. Exported so a probe can exercise the exact registered function. */
export function createViewProtocolHandler(host: ViewHost): ViewProtocolHandler {
  return async (request: Request) => {
    const served = await host.respond(request.url, request.method);
    // `Response` does not take a Node Buffer, and a Buffer can sit in a shared pool, so the
    // body is copied into an ArrayBuffer-backed view that only covers this resource.
    const body = served.body === null ? null : new Uint8Array(served.body);
    return new Response(body, { status: served.status, headers: served.headers });
  };
}

/**
 * Installs the resource protocol for one session. Safe in production: the scheme is new, so
 * before any view is registered every request under it answers 404.
 */
export function attachViewProtocol(target: Session, host: ViewHost): ViewProtocolHandler {
  const handler = createViewProtocolHandler(host);
  if (target.protocol.isProtocolHandled(VIEW_SCHEME)) target.protocol.unhandle(VIEW_SCHEME);
  target.protocol.handle(VIEW_SCHEME, handler);
  return handler;
}

/**
 * Cancels downloads that originate from view resources. Scoped to `reverie-view:` so the
 * application's own save flows keep Electron's behaviour.
 */
export function attachViewDownloadGuard(target: Session, log: ViewGuardLog): void {
  target.on("will-download", (event, item) => {
    const url = item.getURL();
    if (!url.startsWith(`${VIEW_SCHEME}:`)) return;
    event.preventDefault();
    log.downloads.push({ url, cancelled: true });
  });
}

/**
 * Refuses every permission a view frame or view origin asks for, and narrows the trusted top
 * frame to the host allowlist. This replaces a session's permission behaviour wholesale, so it
 * belongs to sessions that actually host views — not to the application shell in P0.
 */
export function attachViewPermissionGuards(target: Session, log: ViewGuardLog): void {
  const record = (permission: string, granted: boolean, kind: PermissionDecisionRecord["kind"], isMainFrame: boolean, origin: string) => {
    log.permissions.push({ permission, granted, isMainFrame, origin, kind });
    return granted;
  };

  target.setPermissionRequestHandler((_contents, permission, callback, details) => {
    const resolved = details as { isMainFrame?: boolean; requestingUrl?: string; securityOrigin?: string } | undefined;
    const granted = viewPermissionDecision(permission, { isMainFrame: resolved?.isMainFrame, requestingUrl: resolved?.requestingUrl, requestingOrigin: resolved?.securityOrigin });
    callback(record(permission, granted, "request", resolved?.isMainFrame !== false, resolved?.securityOrigin ?? resolved?.requestingUrl ?? ""));
  });

  target.setPermissionCheckHandler((_contents, permission, requestingOrigin, details) => {
    const resolved = details as { isMainFrame?: boolean; requestingUrl?: string; securityOrigin?: string } | undefined;
    return record(
      permission,
      viewPermissionDecision(permission, { isMainFrame: resolved?.isMainFrame, requestingUrl: resolved?.requestingUrl, requestingOrigin: requestingOrigin || resolved?.securityOrigin }),
      "check",
      resolved?.isMainFrame !== false,
      requestingOrigin || "",
    );
  });

  target.setDevicePermissionHandler(details => record(String(details.deviceType ?? "device"), false, "device", true, String(details.origin ?? "")));
  target.setDisplayMediaRequestHandler((_request, callback) => {
    record("display-media", false, "display-media", true, "");
    callback({});
  });
}

/**
 * Every session-level boundary a view must not cross, for a session that hosts views:
 * the resource protocol, blanket permission refusal outside the trusted top frame, and the
 * download guard. `webSecurity` is never touched.
 */
export function attachViewSession(target: Session, host: ViewHost, log = createViewGuardLog()): { log: ViewGuardLog; handler: ViewProtocolHandler } {
  const handler = attachViewProtocol(target, host);
  attachViewPermissionGuards(target, log);
  attachViewDownloadGuard(target, log);
  return { log, handler };
}

/**
 * Blocks every frame navigation except the first commit of a bound view URL. The top frame
 * of the trusted window keeps its own existing guard, and the window-open handler the
 * application already installs is deliberately left untouched.
 */
export function attachViewFrameGuards(contents: WebContents, host: ViewHost, log: ViewGuardLog): void {
  // OOPIF key events need not pass through the top WebContents input hook.
  // This fixed host listener grants no API/IPC and does not rewrite app HTML.
  contents.on("did-frame-finish-load", (_event, isMainFrame, processId, routingId) => {
    if (isMainFrame) return;
    const frame = contents.mainFrame.framesInSubtree.find(candidate => candidate.processId === processId && candidate.routingId === routingId);
    const token = frame ? viewRequestToken(frame.url) : null;
    if (!frame || !token || !host.binding(token)) return;
    void frame.executeJavaScript(`addEventListener("keydown", event => { if (event.key === "Escape") parent.postMessage({type:"reverie:view-escape"}, "*"); }, true);`).catch(() => {});
  });
  contents.on("will-frame-navigate", event => {
    const frame = (event as unknown as { frame?: { url?: string } | null }).frame ?? null;
    if ((event as unknown as { isMainFrame?: boolean }).isMainFrame) return;
    const verdict = viewFrameNavigation({ frameUrl: frame?.url ?? "", targetUrl: event.url, isBound: token => host.binding(token) !== null });
    log.navigations.push({ url: event.url, frameUrl: frame?.url ?? "", verdict });
    if (verdict === "block") event.preventDefault();
  });
}

/** Probe-only: records and denies popups on a window that has no other open handler. */
export function recordProbeWindowOpens(contents: WebContents, log: ViewGuardLog): void {
  contents.setWindowOpenHandler(({ url }) => {
    log.windowOpens.push(url);
    return { action: "deny" };
  });
}

/**
 * Probe-only: cancels and records every request that is not a local resource, so "the view
 * reached no network" is an observation rather than an inference from the response policy.
 */
export function recordProbeNetwork(target: Session, log: ViewGuardLog): void {
  target.webRequest.onBeforeRequest((details, callback) => {
    const url = String(details.url ?? "");
    const allowed = /^(?:file|devtools|blob|data):/i.test(url) || viewRequestToken(url) !== null;
    if (!allowed) log.blockedRequests.push(url);
    callback({ cancel: !allowed });
  });
}
