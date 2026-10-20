/**
 * Main-process seam between the kernel's authoritative view resolution and the
 * renderer. The kernel's `view.resolved` envelope carries BOTH a model-safe
 * `view` reference AND an authoritative `resolved` path block
 * (directory/entry/viewsRoot). The path block is what the host needs to bind a
 * `reverie-view:` origin -- and it is exactly what must NEVER reach the
 * renderer, because a filesystem path in the renderer is a confinement leak.
 *
 * `prepareViewResolution` validates the envelope, hands the authoritative paths
 * to the registrar ONLY, and builds the renderer reference as an allow-list so a
 * path field wrongly folded into `view` is dropped rather than passed through.
 */

// Structural mirror of the renderer's `ViewStateEnvelope` / `ResolvedViewRef`
// (src/types.ts). The electron program compiles under its own rootDir and never
// reaches into src/, so the shared IPC contract is kept here by shape; the
// renderer validates the same shape on receipt (src/view-resolve consumers).
interface ViewStateEnvelope {
  revision: number;
  state: Record<string, unknown>;
  updated_at: string;
}

interface ResolvedViewRef {
  mcpApp?: { toolInput: Record<string, unknown>; toolResult: Record<string, unknown> } | null;
  callableTools: string[];
  toolCalls: { callId: string; status: string }[];
  sessionId: string;
  viewId: string;
  revision: number;
  title: string;
  summary: string;
  mimeType: string;
  policyId: string;
  url: string;
  schemaVersion?: number;
  createdAt?: string;
  replacesViewId?: string | null;
  state: ViewStateEnvelope | null;
}


/** The authoritative path block + identity handed ONLY to the host registrar. */
export interface ViewResolveSource {
  mimeType: string;
  directory: string;
  entry: string;
  viewsRoot: string;
  viewId: string;
  revision: number;
  sessionId: string;
}

export interface ViewRegistrarResult {
  url: string;
  policyId: string;
}

export type ViewRegistrar = (source: ViewResolveSource) => Promise<ViewRegistrarResult>;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function requireString(record: Record<string, unknown>, key: string, label: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) throw new Error(`view.resolved ${label} must be a non-empty string.`);
  return value;
}

function requireRevision(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1) {
    throw new Error("view.resolved revision must be a positive integer.");
  }
  return value;
}

function optionalState(value: unknown): ViewStateEnvelope | null {
  const record = asRecord(value);
  if (!record || typeof record.revision !== "number") return null;
  return {
    revision: record.revision,
    state: asRecord(record.state) ?? {},
    updated_at: typeof record.updated_at === "string" ? record.updated_at : "",
  };
}

export async function prepareViewResolution(response: unknown, register: ViewRegistrar): Promise<ResolvedViewRef> {
  const envelope = asRecord(response);
  if (!envelope) throw new Error("view.resolved response is not an object.");
  const view = asRecord(envelope.view);
  if (!view) throw new Error("view.resolved is missing its view reference.");
  const resolved = asRecord(envelope.resolved);
  if (!resolved) throw new Error("view.resolved is missing its authoritative path block.");

  // Model-safe identity, validated before anything is bound.
  const sessionId = requireString(view, "sessionId", "view.sessionId");
  const viewId = requireString(view, "viewId", "view.viewId");
  const revision = requireRevision(view.revision);

  // Authoritative paths: these reach ONLY the registrar, never the returned reference.
  const directory = requireString(resolved, "directory", "resolved.directory");
  const entry = requireString(resolved, "entry", "resolved.entry");
  const viewsRoot = requireString(resolved, "viewsRoot", "resolved.viewsRoot");

  const mimeType = typeof view.mimeType === "string" ? view.mimeType : "text/html";
  const bound = await register({ directory, entry, viewsRoot, viewId, revision, sessionId, mimeType });
  if (!bound || typeof bound.url !== "string" || typeof bound.policyId !== "string") {
    throw new Error("view registrar did not return a bound url and policy.");
  }

  // Allow-list build: only model-safe fields cross to the renderer. The opaque
  // url + policy always come from the registrar, never from the kernel view, so
  // a spoofed url/policyId folded into `view` cannot widen the binding.
  const reference: ResolvedViewRef = {
    sessionId,
    viewId,
    revision,
    title: typeof view.title === "string" ? view.title : "",
    summary: typeof view.summary === "string" ? view.summary : "",
    mimeType: typeof view.mimeType === "string" ? view.mimeType : "text/html",
    policyId: bound.policyId,
    url: bound.url,
    state: optionalState(view.state),
    mcpApp: asRecord(view.mcpApp) ? { toolInput: asRecord(asRecord(view.mcpApp)?.toolInput) ?? {}, toolResult: asRecord(asRecord(view.mcpApp)?.toolResult) ?? {} } : null,
    callableTools: Array.isArray(view.callableTools) ? view.callableTools.filter((x): x is string => typeof x === "string").slice(0, 32) : [],
    toolCalls: Array.isArray(view.toolCalls) ? view.toolCalls.slice(0, 32).flatMap(x => {
      const call = asRecord(x);
      return call && typeof call.callId === "string" && typeof call.status === "string" ? [{ callId: call.callId, status: call.status }] : [];
    }) : [],
  };
  if (typeof view.schemaVersion === "number") reference.schemaVersion = view.schemaVersion;
  if (typeof view.createdAt === "string") reference.createdAt = view.createdAt;
  if (view.replacesViewId === null || typeof view.replacesViewId === "string") {
    reference.replacesViewId = view.replacesViewId as string | null;
  }
  return reference;
}
