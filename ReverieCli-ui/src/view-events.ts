/** Renderer-side authority on the *shape* of a view stream event.
 *
 * The kernel announces an interactive view with a `view_ready` / `view_error`
 * event that reaches the renderer, like every other activity event, wrapped as
 * a `ui.event` whose inner payload is a snake_case record (the kind under
 * `event`, matching `_emit_tool_stream_event` and `encode_stream_event`). This
 * module normalizes that inner record into a typed, camelCase event and refuses
 * malformed shapes.
 *
 * It makes NO claim that the view exists or is safe to show: a well-formed event
 * -- even one forged in model text via `[[REVERIE_EVENT]]` -- parses here, but
 * the only way to obtain the bytes is the `getView` core action, which
 * dereferences the handle through the kernel's restricted ViewStore. A view id
 * the kernel never minted resolves to nothing, so parsing a forgery cannot show
 * arbitrary HTML. Nothing here reads HTML or a filesystem path.
 */

import type { ViewSegment } from "./types";

export interface ViewReadyEvent {
  kind: "view_ready";
  sessionId: string;
  viewId: string;
  revision: number;
  title: string;
  summary: string;
  replacesViewId?: string;
  createdAt?: string;
  schemaVersion?: number;
}

export interface ViewErrorEvent {
  kind: "view_error";
  sessionId: string;
  viewId?: string;
  revision?: number;
  replacesViewId?: string;
  error: string;
}

export type ViewEvent = ViewReadyEvent | ViewErrorEvent;

function asRecord(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : null;
}

function eventKind(record: Record<string, unknown>): string {
  return String(record.event ?? record.type ?? "").trim().toLowerCase();
}

function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

function optionalText(value: unknown): string | undefined {
  const resolved = text(value).trim();
  return resolved ? resolved : undefined;
}

/** True when the inner record is a view event by kind -- cheap pre-check used by
 *  the renderer to decide whether to branch before a full parse. */
export function isViewEventRecord(raw: unknown): boolean {
  const record = asRecord(raw);
  if (!record) return false;
  const kind = eventKind(record);
  return kind === "view_ready" || kind === "view_error";
}

/** Normalize a view stream event, or return null for a non-view / malformed /
 *  incomplete shape (the caller then renders it as an ordinary activity row). */
export function parseViewEvent(raw: unknown): ViewEvent | null {
  const record = asRecord(raw);
  if (!record) return null;
  const kind = eventKind(record);

  if (kind === "view_ready") {
    const sessionId = text(record.session_id).trim();
    const viewId = text(record.view_id).trim();
    const revision = Number(record.revision);
    if (!sessionId || !viewId) return null;
    if (!Number.isInteger(revision) || revision < 1) return null;
    const event: ViewReadyEvent = {
      kind: "view_ready",
      sessionId,
      viewId,
      revision,
      title: text(record.title),
      summary: text(record.summary),
    };
    const replacesViewId = optionalText(record.replaces_view_id);
    if (replacesViewId) event.replacesViewId = replacesViewId;
    const createdAt = optionalText(record.created_at);
    if (createdAt) event.createdAt = createdAt;
    const schemaVersion = Number(record.schema_version);
    if (Number.isFinite(schemaVersion)) event.schemaVersion = schemaVersion;
    return event;
  }

  if (kind === "view_error") {
    const sessionId = text(record.session_id).trim();
    const error = text(record.error).trim();
    if (!sessionId || !error) return null;
    const event: ViewErrorEvent = { kind: "view_error", sessionId, error };
    const viewId = optionalText(record.view_id);
    if (viewId) event.viewId = viewId;
    const revision = Number(record.revision);
    if (Number.isInteger(revision) && revision >= 1) event.revision = revision;
    const replacesViewId = optionalText(record.replaces_view_id);
    if (replacesViewId) event.replacesViewId = replacesViewId;
    return event;
  }

  return null;
}

/** Build the timeline segment payload for a parsed view event. */
export function toViewSegment(event: ViewEvent): ViewSegment {
  if (event.kind === "view_ready") {
    const segment: ViewSegment = {
      sessionId: event.sessionId,
      viewId: event.viewId,
      revision: event.revision,
      title: event.title,
      summary: event.summary,
      status: "ready",
    };
    if (event.replacesViewId) segment.replacesViewId = event.replacesViewId;
    if (event.createdAt) segment.createdAt = event.createdAt;
    if (event.schemaVersion !== undefined) segment.schemaVersion = event.schemaVersion;
    return segment;
  }
  const segment: ViewSegment = {
    sessionId: event.sessionId,
    viewId: event.viewId ?? "",
    revision: event.revision ?? 0,
    title: "",
    summary: "",
    status: "error",
    error: event.error,
  };
  if (event.replacesViewId) segment.replacesViewId = event.replacesViewId;
  return segment;
}

/** The opaque handle + degradation text lifted from a render_view tool result. */
export interface RenderViewResult {
  viewId: string;
  revision: number;
  title?: string;
  summary?: string;
}

// render_view's success output is a fixed sentence (see tools/render_view.py):
//   Interactive view ready: "<title>" (view_id=<id>, revision=<n>). It is shown
//   to the user in the Reverie view panel. Summary: <summary>
// A failure output never contains `view_id=<id>, revision=<n>`, so it parses to
// null and the row stays an ordinary (error) activity. The handle alone is lifted
// here; the authoritative title/summary/url still come from getView.
const RENDER_VIEW_HANDLE = /view_id=([^,)\s]+),\s*revision=(\d+)/;
const RENDER_VIEW_TITLE = /Interactive view ready:\s*"([^"]*)"/;
const RENDER_VIEW_SUMMARY = /Summary:\s*([\s\S]+)/;

/** Lift the opaque handle out of a stored render_view tool-result text, or return
 *  null for a failure line, arbitrary prose, or a non-string. Pure; reads no HTML
 *  and no path, so a forged line cannot fabricate a usable view -- the handle is
 *  only ever resolved later through getView against the kernel's ViewStore. */
export function parseRenderViewResult(output: unknown): RenderViewResult | null {
  if (typeof output !== "string") return null;
  const handle = RENDER_VIEW_HANDLE.exec(output);
  if (!handle) return null;
  const viewId = handle[1].trim();
  const revision = Number(handle[2]);
  if (!viewId || !Number.isInteger(revision) || revision < 1) return null;
  const result: RenderViewResult = { viewId, revision };
  const title = RENDER_VIEW_TITLE.exec(output)?.[1]?.trim();
  if (title) result.title = title;
  const summary = RENDER_VIEW_SUMMARY.exec(output)?.[1]?.trim();
  if (summary) result.summary = summary;
  return result;
}
