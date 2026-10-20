import { randomBytes } from "node:crypto";
import { open, lstat, readdir, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { pathIsWithin, samePath } from "./workspace-lifecycle";

export const VIEW_SCHEME = "reverie-view";
export const VIEW_POLICY_ID = "local-offline-v1";
export const VIEW_IFRAME_SANDBOX = "allow-scripts";
export const MAX_VIEW_ENTRY_BYTES = 2 * 1024 * 1024;
export const MAX_VIEW_BUNDLE_BYTES = 8 * 1024 * 1024;
export const MAX_VIEW_PATH_SEGMENTS = 8;
export const MAX_VIEW_PATH_LENGTH = 512;

/** Offline response policy from docs/INTELLIGENT_UI_SPEC.md 4.3. Inline script runs inside the view, never in the host. */
export const VIEW_CONTENT_SECURITY_POLICY = [
  "default-src 'none'", "script-src 'unsafe-inline'", "style-src 'unsafe-inline'",
  "img-src data: blob:", "font-src 'none'", "media-src data: blob:",
  "connect-src 'none'", "frame-src 'none'", "worker-src 'none'",
  "object-src 'none'", "base-uri 'none'", "form-action 'none'",
].join("; ");

export const VIEW_PERMISSIONS_POLICY = [
  "accelerometer", "ambient-light-sensor", "autoplay", "camera", "clipboard-read", "clipboard-write",
  "display-capture", "encrypted-media", "geolocation", "gyroscope", "idle-detection", "magnetometer",
  "microphone", "midi", "payment", "publickey-credentials-get", "screen-wake-lock", "serial",
  "usb", "xr-spatial-tracking",
].map(feature => `${feature}=()`).join(", ");

/** Permissions the trusted top-level host page keeps; a view frame is never granted any permission. */
const HOST_PERMISSIONS = new Set(["clipboard-read", "clipboard-sanitized-write", "clipboard-write", "fullscreen"]);
/** Script bytes are never mappable: the offline policy allows inline script only, so a view can never load one. */
const VIEW_MIME_TYPES: Readonly<Record<string, string>> = {
  ".html": "text/html", ".css": "text/css", ".json": "application/json", ".txt": "text/plain",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2",
};
const TEXTUAL_MIME = /^(?:text\/|application\/json$|image\/svg\+xml$)/;
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const RESERVED_DEVICE = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export class ViewRequestError extends Error {
  constructor(readonly status: number, message: string) { super(message); this.name = "ViewRequestError"; }
}

export type ViewRegistration = { viewId: string; revision: number; sessionId: string; directory: string; entry?: string; mimeType?: string };
export type ViewBinding = { token: string; viewId: string; revision: number; sessionId: string; directory: string; entry: string; mimeType: string; url: string; policyId: string };
export type ViewResponse = { status: number; headers: Record<string, string>; body: Buffer | null };
export type ViewPermissionDetails = { isMainFrame?: boolean; requestingUrl?: string; requestingOrigin?: string; embeddingOrigin?: string };

export function viewMimeType(relative: string): string | null {
  return VIEW_MIME_TYPES[path.posix.extname(relative).toLowerCase()] ?? null;
}

export function viewResponseHeaders(mimeType: string): Record<string, string> {
  return {
    "Content-Type": TEXTUAL_MIME.test(mimeType) ? `${mimeType}; charset=utf-8` : mimeType,
    "Content-Security-Policy": VIEW_CONTENT_SECURITY_POLICY,
    "Permissions-Policy": VIEW_PERMISSIONS_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
  };
}

function viewRelativeSegments(value: string, label: string): string[] {
  if (value.length > MAX_VIEW_PATH_LENGTH) throw new ViewRequestError(400, `${label} is too long.`);
  let decoded: string;
  try { decoded = decodeURIComponent(value); } catch { throw new ViewRequestError(400, `${label} is not decodable.`); }
  if (decoded !== value && decoded.length > MAX_VIEW_PATH_LENGTH) throw new ViewRequestError(400, `${label} is too long.`);
  const segments = decoded.split("/");
  if (segments.length === 0 || segments.length > MAX_VIEW_PATH_SEGMENTS) throw new ViewRequestError(400, `${label} is too deep.`);
  for (const segment of segments) {
    if (segment.length === 0 || segment.length > 128) throw new ViewRequestError(400, `${label} has an unusable segment.`);
    if (!SEGMENT.test(segment)) throw new ViewRequestError(400, `${label} rejects "${segment}".`);
    if (RESERVED_DEVICE.test(segment.replace(/\..*$/, ""))) throw new ViewRequestError(400, `${label} names a reserved device.`);
  }
  return segments;
}

/** Reads the bound token straight from the request text: the WHATWG parser silently folds `..` away, so it is never trusted to describe the path. */
export function viewRequestToken(url: string): string | null {
  const marker = `${VIEW_SCHEME}://`;
  if (typeof url !== "string" || !url.slice(0, marker.length).toLowerCase().startsWith(marker)) return null;
  const authority = url.slice(marker.length);
  const boundary = authority.search(/[/?#]/);
  const host = boundary === -1 ? authority : authority.slice(0, boundary);
  return /^[0-9a-f]{32}$/.test(host) ? host : null;
}

/** Maps a request URL to a relative path inside one bound view. Never a general file proxy. */
export function viewRequestPath(binding: { token: string; entry: string }, url: string): string {
  const marker = `${VIEW_SCHEME}://`;
  if (typeof url !== "string" || !url.slice(0, marker.length).toLowerCase().startsWith(marker)) throw new ViewRequestError(400, "View request uses an unexpected scheme.");
  const authority = url.slice(marker.length);
  const boundary = authority.search(/[/?#]/);
  if ((boundary === -1 ? authority : authority.slice(0, boundary)) !== binding.token) throw new ViewRequestError(404, "View token is not bound.");
  if (boundary === -1 || authority[boundary] !== "/") return binding.entry;
  const raw = authority.slice(boundary + 1).split("#")[0].split("?")[0];
  if (raw === "") return binding.entry;
  return viewRelativeSegments(raw, "View request path").join("/");
}

/** Only the first commit of a bound entry URL is allowed; every later frame navigation is refused. */
export function viewFrameNavigation(options: { frameUrl: string; targetUrl: string; isBound: (token: string) => boolean }): "allow" | "block" {
  const token = viewRequestToken(options.targetUrl);
  if (!token || !options.isBound(token)) return "block";
  const current = options.frameUrl.trim();
  return current === "" || current === "about:blank" ? "allow" : "block";
}

/** Privileged IPC is answered only for the top-level frame of the trusted host window. */
export function trustedHostFrame(
  candidate: { sender?: unknown; senderFrame?: unknown },
  host: { webContents: unknown; mainFrame: unknown } | null,
): boolean {
  if (!host || !host.webContents || !host.mainFrame) return false;
  if (!candidate.sender || candidate.sender !== host.webContents) return false;
  return Boolean(candidate.senderFrame) && candidate.senderFrame === host.mainFrame;
}

export function viewPermissionDecision(permission: string, details?: ViewPermissionDetails): boolean {
  if (!details || details.isMainFrame === false) return false;
  const origin = details.requestingOrigin ?? "";
  const requesting = details.requestingUrl ?? "";
  if (origin === "null" || origin.startsWith(`${VIEW_SCHEME}:`) || requesting.startsWith(`${VIEW_SCHEME}:`)) return false;
  return HOST_PERMISSIONS.has(permission);
}

export class ViewHost {
  readonly root: string;
  #realRoot: string | null = null;
  readonly #bindings = new Map<string, ViewBinding>();
  /** Additional realpath'd roots the core explicitly handed us (e.g. the kernel ViewStore's own views dir). */
  readonly #trustedRoots = new Set<string>();

  constructor(options: { root: string }) { this.root = path.resolve(options.root); }

  bindings(): ViewBinding[] { return [...this.#bindings.values()]; }
  binding(token: string): ViewBinding | null { return this.#bindings.get(token) ?? null; }
  entryUrl(token: string): string | null { return this.#bindings.get(token)?.url ?? null; }

  /**
   * Widen containment to one more existing directory, canonicalised. The core
   * calls this with a root it already trusts (never a model-supplied path) so a
   * view the kernel resolved outside the default artifact root can still bind.
   * Returns the realpath'd root that was trusted.
   */
  async allowRoot(root: string): Promise<string> {
    const resolved = path.resolve(String(root ?? ""));
    const real = await realpath(resolved).catch(() => null);
    if (!real || !(await stat(real).then(info => info.isDirectory(), () => false))) {
      throw new Error(`Trusted view root is not an existing directory: ${root}`);
    }
    this.#trustedRoots.add(real);
    return real;
  }

  async register(registration: ViewRegistration): Promise<ViewBinding> {
    const { viewId, revision, sessionId } = registration;
    if (!IDENTIFIER.test(String(viewId ?? ""))) throw new Error("View id is not acceptable.");
    if (!IDENTIFIER.test(String(sessionId ?? ""))) throw new Error("View session id is not acceptable.");
    if (!Number.isSafeInteger(revision) || revision < 1) throw new Error("View revision must be a positive integer.");
    const entry = viewRelativeSegments(String(registration.entry ?? "index.html"), "View entry").join("/");
    if (viewMimeType(entry) !== "text/html") throw new Error("View entry must be an HTML document.");
    const mimeType = registration.mimeType ?? "text/html";
    if (!["text/html", "text/html;profile=mcp-app"].includes(mimeType)) throw new Error("View entry MIME is not supported.");

    const realRoot = this.#realRoot ?? (this.#realRoot = await realpath(this.root).catch(() => this.root));
    const requested = path.resolve(registration.directory ?? "");
    const directory = await realpath(requested).catch(() => null);
    if (!directory || !(await stat(directory).then(info => info.isDirectory(), () => false))) throw new Error(`View directory is not available: ${requested}`);
    const containedByDefault = pathIsWithin(directory, realRoot);
    const containedByTrusted = containedByDefault || [...this.#trustedRoots].some(trusted => pathIsWithin(directory, trusted));
    if (!containedByTrusted) throw new Error("View directory must stay inside the managed artifact root.");

    const entryPath = path.join(directory, entry);
    const entryInfo = await lstat(entryPath).catch(() => null);
    if (!entryInfo?.isFile()) throw new Error(`View entry is missing: ${entry}`);
    if (entryInfo.size > MAX_VIEW_ENTRY_BYTES) throw new Error("View entry exceeds the 2 MiB entry limit.");
    const total = await this.#bundleBytes(directory);
    if (total > MAX_VIEW_BUNDLE_BYTES) throw new Error(`View bundle exceeds the total size limit (${total} bytes).`);

    this.release(viewId);
    const token = randomBytes(16).toString("hex");
    const binding: ViewBinding = { token, viewId, revision, sessionId, directory, entry, mimeType, url: `${VIEW_SCHEME}://${token}/${entry}`, policyId: VIEW_POLICY_ID };
    this.#bindings.set(token, binding);
    return binding;
  }

  release(viewId: string): number {
    let removed = 0;
    for (const [token, binding] of [...this.#bindings]) if (binding.viewId === viewId) { this.#bindings.delete(token); removed += 1; }
    return removed;
  }

  releaseSession(sessionId: string): number {
    let removed = 0;
    for (const [token, binding] of [...this.#bindings]) if (binding.sessionId === sessionId) { this.#bindings.delete(token); removed += 1; }
    return removed;
  }

  releaseAll(): number { const size = this.#bindings.size; this.#bindings.clear(); return size; }

  async respond(url: string, method = "GET"): Promise<ViewResponse> {
    if (method.toUpperCase() !== "GET") return this.#failure(405, "Only GET is served for view resources.");
    const token = viewRequestToken(url);
    const binding = token ? this.#bindings.get(token) ?? null : null;
    if (!binding) return this.#failure(404, "View token is not bound.");
    try {
      const relative = viewRequestPath(binding, url);
      const resolved = await this.#resolve(binding, relative);
      const mimeType = relative === binding.entry ? binding.mimeType : viewMimeType(relative);
      if (!mimeType) { await resolved.close(); return this.#failure(415, "View resource type is not mappable."); }
      try {
        const body = await resolved.read();
        return { status: 200, headers: { ...viewResponseHeaders(mimeType), "Content-Length": String(body.byteLength) }, body };
      } finally { await resolved.close(); }
    } catch (error) {
      if (error instanceof ViewRequestError) return this.#failure(error.status, error.message);
      throw error;
    }
  }

  #failure(status: number, message: string): ViewResponse {
    return { status, headers: { "Content-Type": "text/plain; charset=utf-8", "Content-Security-Policy": VIEW_CONTENT_SECURITY_POLICY, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store" }, body: Buffer.from(`${message}\n`, "utf8") };
  }

  async #bundleBytes(directory: string): Promise<number> {
    let total = 0;
    const pending = [directory];
    while (pending.length > 0) {
      const current = pending.pop()!;
      const entries = await readdir(current, { withFileTypes: true }).catch(() => []);
      for (const entry of entries) {
        const child = path.join(current, entry.name);
        if (entry.isSymbolicLink()) continue;
        if (entry.isDirectory()) { pending.push(child); continue; }
        if (!entry.isFile()) continue;
        total += await lstat(child).then(info => info.size, () => 0);
        if (total > MAX_VIEW_BUNDLE_BYTES) return total;
      }
    }
    return total;
  }

  /** Opens the mapped file and keeps the handle so the served bytes are the ones that passed the checks. */
  async #resolve(binding: ViewBinding, relative: string): Promise<{ read(): Promise<Buffer>; close(): Promise<void> }> {
    const candidate = path.join(binding.directory, relative);
    if (!pathIsWithin(candidate, binding.directory)) throw new ViewRequestError(403, "View resource escapes its bound directory.");
    const before = await lstat(candidate).catch(() => null);
    if (!before) throw new ViewRequestError(404, "View resource does not exist.");
    if (before.isSymbolicLink()) throw new ViewRequestError(403, "View resource is a link.");
    if (!before.isFile()) throw new ViewRequestError(404, "View resource is not a file.");
    const real = await realpath(candidate).catch(() => null);
    if (!real || !samePath(real, candidate) || !pathIsWithin(real, binding.directory)) throw new ViewRequestError(403, "View resource resolves outside its bound directory.");
    const handle = await open(candidate, "r").catch(() => null);
    if (!handle) throw new ViewRequestError(404, "View resource cannot be opened.");
    try {
      const after = await handle.stat();
      if (!after.isFile()) throw new ViewRequestError(403, "View resource changed type while opening.");
      if ((before.ino !== 0 || after.ino !== 0) && (before.ino !== after.ino || before.dev !== after.dev)) throw new ViewRequestError(403, "View resource was replaced while opening.");
      if (after.size > MAX_VIEW_ENTRY_BYTES) throw new ViewRequestError(413, "View resource exceeds the 2 MiB limit.");
    } catch (error) { await handle.close().catch(() => undefined); throw error; }
    return { read: () => handle.readFile(), close: () => handle.close().catch(() => undefined) };
  }
}
