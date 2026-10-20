/**
 * Restricted host side of the generative-view message channel.
 *
 * Validation only: it decides whether one `message` event from an isolated view may be
 * acted on. The opaque-origin `"null"` of a sandboxed frame is not an identity, so every
 * message is bound to the registered window object plus a random per-instance capability
 * that the host only ever hands out in the `ui/initialize` response.
 */

export const MAX_BRIDGE_MESSAGE_BYTES = 256 * 1024;
export const MAX_BRIDGE_PENDING_REQUESTS = 8;
export const BRIDGE_REQUEST_TIMEOUT_MS = 10_000;
export const BRIDGE_RATE_LIMIT = { messages: 64, windowMs: 1_000 } as const;
// P3 pins the standard dialect to ext-apps 2.0.3. Generated views keep their P2 capability envelope.
export const VIEW_PROTOCOL_VERSION = "2026-01-26";
export const BRIDGE_METHODS = ["ui/initialize", "ui/notifications/initialized", "ui/notifications/size-changed", "ui/notifications/request-teardown", "ui/request-display-mode", "tools/call", "ui/message", "ui/update-model-context", "reverie/view-state", "reverie/call-tool"] as const;

export type BridgeRequestId = string | number;
export type BridgeMethod = (typeof BRIDGE_METHODS)[number];
export type BridgeRejection =
  | "revoked" | "unknown-source" | "malformed" | "oversize" | "rate-limited" | "unsupported-method"
  | "not-initialized" | "duplicate-request" | "too-many-pending" | "missing-capability" | "stale-instance" | "too-many-requests" | "unsupported-version";
export type BridgeVerdict =
  | { accepted: true; method: BridgeMethod; id: BridgeRequestId | null; params: unknown; capabilityIssued?: string }
  | { accepted: false; reason: BridgeRejection };

export type ViewChannelOptions = { source: unknown; sessionId: string; viewId: string; revision: number; capability: string; standard?: boolean; now?: () => number };

const BRIDGE_METHOD_SET: ReadonlySet<string> = new Set(BRIDGE_METHODS);
const encoder = new TextEncoder();

export class ViewChannel {
  readonly capability: string;
  readonly stats: { accepted: number; rejected: number; byReason: Partial<Record<BridgeRejection, number>> } = { accepted: 0, rejected: 0, byReason: {} };
  #initialized = false;
  #ready = false;
  readonly #seen = new Set<BridgeRequestId>();
  #revoked = false;
  readonly #accepts: number[] = [];
  readonly #pending = new Map<BridgeRequestId, { started: number; timeout: number }>();
  readonly #now: () => number;

  constructor(private readonly options: ViewChannelOptions) {
    this.capability = options.capability;
    this.#now = options.now ?? (() => Date.now());
  }

  get initialized(): boolean { return this.#initialized; }
  get ready(): boolean { return this.#ready; }
  get pending(): number { return this.#pending.size; }

  accept(event: { source?: unknown; data?: unknown }): BridgeVerdict {
    const verdict = this.#judge(event);
    if (verdict.accepted) this.stats.accepted += 1;
    else { this.stats.rejected += 1; this.stats.byReason[verdict.reason] = (this.stats.byReason[verdict.reason] ?? 0) + 1; }
    return verdict;
  }

  /** Marks a request answered so its id frees a concurrency slot. */
  settle(id: BridgeRequestId): boolean { return this.#pending.delete(id); }

  /** Drops requests the host never answered in time and reports their ids. */
  expire(now = this.#now()): BridgeRequestId[] {
    const stale = [...this.#pending].filter(([, request]) => now - request.started > request.timeout).map(([id]) => id);
    for (const id of stale) this.#pending.delete(id);
    return stale;
  }

  /** Invalidates the instance on navigation, reload, revision change or session switch. */
  revoke(): void { this.#revoked = true; this.#pending.clear(); }

  #judge(event: { source?: unknown; data?: unknown }): BridgeVerdict {
    if (this.#revoked) return { accepted: false, reason: "revoked" };
    if (!event.source || event.source !== this.options.source) return { accepted: false, reason: "unknown-source" };
    const data = event.data;
    if (typeof data !== "object" || data === null || Array.isArray(data)) return { accepted: false, reason: "malformed" };
    let serialized: string;
    try { serialized = JSON.stringify(data) ?? ""; } catch { return { accepted: false, reason: "malformed" }; }
    if (serialized === "" || encoder.encode(serialized).byteLength > MAX_BRIDGE_MESSAGE_BYTES) return { accepted: false, reason: "oversize" };
    if (!this.#admit()) return { accepted: false, reason: "rate-limited" };

    const envelope = data as Record<string, unknown>;
    if (envelope.jsonrpc !== "2.0" || typeof envelope.method !== "string") return { accepted: false, reason: "malformed" };
    const method = envelope.method;
    if (!BRIDGE_METHOD_SET.has(method)) return { accepted: false, reason: "unsupported-method" };
    if (this.options.standard && method.startsWith("reverie/")) return { accepted: false, reason: "unsupported-method" };
    const handshake = method === "ui/initialize";
    if (handshake) {
      const version = (envelope.params as { protocolVersion?: unknown } | undefined)?.protocolVersion;
      if (this.options.standard ? version !== VIEW_PROTOCOL_VERSION : version !== undefined && version !== "1" && version !== VIEW_PROTOCOL_VERSION) return { accepted: false, reason: "unsupported-version" };
      if (this.options.standard) {
        const params = envelope.params as Record<string, unknown>;
        const info = params.appInfo as Record<string, unknown> | undefined;
        if (!info || typeof info.name !== "string" || typeof info.version !== "string" || !params.appCapabilities || typeof params.appCapabilities !== "object" || Array.isArray(params.appCapabilities)) return { accepted: false, reason: "malformed" };
      }
    }
    if (handshake && this.#initialized) return { accepted: false, reason: "duplicate-request" };
    if (!handshake && (!this.#initialized || (!this.#ready && method !== "ui/notifications/initialized"))) return { accepted: false, reason: "not-initialized" };
    if (!handshake && !this.options.standard && envelope.capability !== this.capability) return { accepted: false, reason: "missing-capability" };
    if (
      (envelope.sessionId !== undefined && envelope.sessionId !== this.options.sessionId)
      || (envelope.viewId !== undefined && envelope.viewId !== this.options.viewId)
      || (envelope.revision !== undefined && envelope.revision !== this.options.revision)
    ) return { accepted: false, reason: "stale-instance" };

    const rawId = envelope.id;
    if (rawId !== undefined && rawId !== null && typeof rawId !== "string" && typeof rawId !== "number") return { accepted: false, reason: "malformed" };
    if (typeof rawId === "number" && !Number.isFinite(rawId)) return { accepted: false, reason: "malformed" };
    const id = rawId === undefined || rawId === null ? null : rawId as BridgeRequestId;
    if (handshake && id === null) return { accepted: false, reason: "malformed" };
    if (id !== null) {
      if (this.#seen.has(id)) return { accepted: false, reason: "duplicate-request" };
      if (this.#pending.size >= MAX_BRIDGE_PENDING_REQUESTS) return { accepted: false, reason: "too-many-pending" };
      if (this.#seen.size >= 1024) return { accepted: false, reason: "too-many-requests" };
      this.#seen.add(id);
      this.#pending.set(id, { started: this.#now(), timeout: method === "tools/call" || method === "reverie/call-tool" ? 330_000 : BRIDGE_REQUEST_TIMEOUT_MS });
    }
    const notification = method.startsWith("ui/notifications/");
    if (this.options.standard && notification && id !== null) return { accepted: false, reason: "malformed" };
    if (!handshake && !notification && id === null) return { accepted: false, reason: "malformed" };
    if (handshake) this.#initialized = true;
    if (method === "ui/notifications/initialized") this.#ready = true;
    const accepted: BridgeVerdict = { accepted: true, method: method as BridgeMethod, id, params: envelope.params };
    return handshake ? { ...accepted, capabilityIssued: this.capability } : accepted;
  }

  #admit(): boolean {
    const now = this.#now();
    while (this.#accepts.length > 0 && now - this.#accepts[0] >= BRIDGE_RATE_LIMIT.windowMs) this.#accepts.shift();
    if (this.#accepts.length >= BRIDGE_RATE_LIMIT.messages) return false;
    this.#accepts.push(now);
    return true;
  }
}
