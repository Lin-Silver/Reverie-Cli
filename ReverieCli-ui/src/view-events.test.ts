import { describe, expect, it } from "vitest";

import { isViewEventRecord, parseRenderViewResult, parseViewEvent, toViewSegment } from "./view-events";

// The renderer receives the *inner* event (already `asRecord(event.event)`): a
// snake_case record whose kind lives under `event` (what `_emit_tool_stream_event`
// and `encode_stream_event` both write) or, for activity-feed rows, under `type`.
// These tests pin the parser as the renderer-side authority on SHAPE only -- it
// normalizes a well-formed view event and refuses a malformed one. It makes NO
// claim that the view exists; that is the ViewStore's job, re-checked by getView.

const READY = {
  kind: "stream_event",
  event: "view_ready",
  session_id: "sess-1",
  turn_id: "turn-1",
  schema_version: 1,
  view_id: "v0123456789abcdef",
  revision: 1,
  title: "Sales chart",
  summary: "A bar chart of Q3 sales.",
  mime_type: "text/html",
  created_at: "2026-10-11T07:55:00+00:00",
  replaces_view_id: null,
};

describe("parseViewEvent", () => {
  it("normalizes a well-formed view_ready into a camelCase typed event", () => {
    const event = parseViewEvent(READY);
    expect(event).toEqual({
      kind: "view_ready",
      sessionId: "sess-1",
      viewId: "v0123456789abcdef",
      revision: 1,
      title: "Sales chart",
      summary: "A bar chart of Q3 sales.",
      createdAt: "2026-10-11T07:55:00+00:00",
      schemaVersion: 1,
    });
  });

  it("carries replaces_view_id through for a revision", () => {
    const event = parseViewEvent({ ...READY, revision: 2, replaces_view_id: "v0123456789abcdef" });
    expect(event).toMatchObject({ kind: "view_ready", revision: 2, replacesViewId: "v0123456789abcdef" });
  });

  it("accepts the kind under `type` as well as `event`", () => {
    const { event: _dropped, ...rest } = READY;
    expect(parseViewEvent({ ...rest, type: "view_ready" })).toMatchObject({ kind: "view_ready", viewId: READY.view_id });
  });

  it("normalizes a view_error with the failing session and reason", () => {
    const event = parseViewEvent({
      kind: "stream_event",
      event: "view_error",
      session_id: "sess-1",
      error: "artifact resolves outside the workspace and is refused.",
    });
    expect(event).toEqual({
      kind: "view_error",
      sessionId: "sess-1",
      error: "artifact resolves outside the workspace and is refused.",
    });
  });

  it("returns null for a view_ready missing the view id (incomplete/forged shape)", () => {
    expect(parseViewEvent({ ...READY, view_id: "" })).toBeNull();
    const { view_id: _dropped, ...withoutId } = READY;
    expect(parseViewEvent(withoutId)).toBeNull();
  });

  it("returns null for a view_ready missing or non-positive revision", () => {
    expect(parseViewEvent({ ...READY, revision: 0 })).toBeNull();
    expect(parseViewEvent({ ...READY, revision: "x" })).toBeNull();
    const { revision: _dropped, ...withoutRevision } = READY;
    expect(parseViewEvent(withoutRevision)).toBeNull();
  });

  it("returns null for a view_error without a session or reason", () => {
    expect(parseViewEvent({ event: "view_error", session_id: "sess-1" })).toBeNull();
    expect(parseViewEvent({ event: "view_error", error: "boom" })).toBeNull();
  });

  it("returns null for a non-view event or a non-object", () => {
    expect(parseViewEvent({ event: "tool_start", tool_call_id: "a" })).toBeNull();
    expect(parseViewEvent(null)).toBeNull();
    expect(parseViewEvent("view_ready")).toBeNull();
  });
});

describe("isViewEventRecord", () => {
  it("recognizes view_ready / view_error under event or type, nothing else", () => {
    expect(isViewEventRecord(READY)).toBe(true);
    expect(isViewEventRecord({ type: "view_error" })).toBe(true);
    expect(isViewEventRecord({ event: "tool_start" })).toBe(false);
    expect(isViewEventRecord(42)).toBe(false);
  });
});

describe("toViewSegment", () => {
  it("builds a ready segment carrying the authoritative handle and summary", () => {
    const segment = toViewSegment(parseViewEvent(READY)!);
    expect(segment).toMatchObject({
      sessionId: "sess-1",
      viewId: "v0123456789abcdef",
      revision: 1,
      title: "Sales chart",
      summary: "A bar chart of Q3 sales.",
      status: "ready",
    });
  });

  it("builds an error segment that keeps the reason for degradation", () => {
    const segment = toViewSegment(parseViewEvent({ event: "view_error", session_id: "sess-1", error: "boom" })!);
    expect(segment).toMatchObject({ sessionId: "sess-1", status: "error", error: "boom" });
  });
});

// `parseRenderViewResult` is the HISTORY/RESTART authority on SHAPE. On reload the
// live view_ready event is gone; all that survives is the render_view tool-result
// TEXT in the transcript (the SessionMessage carries only `content`, never HTML or
// a path). This helper lifts the opaque handle + degradation text out of that text
// so the row can be re-dereferenced through getView. It must refuse a render_view
// FAILURE line and arbitrary prose so a forgery cannot fabricate a view row.
describe("parseRenderViewResult", () => {
  const OUTPUT =
    'Interactive view ready: "Sales chart" (view_id=v0123456789abcdef, revision=1). ' +
    "It is shown to the user in the Reverie view panel. Summary: A bar chart of Q3 sales.";

  it("lifts the opaque handle and degradation text from the tool-result text", () => {
    expect(parseRenderViewResult(OUTPUT)).toEqual({
      viewId: "v0123456789abcdef",
      revision: 1,
      title: "Sales chart",
      summary: "A bar chart of Q3 sales.",
    });
  });

  it("reads a later revision from a replaces_view_id follow-up", () => {
    const out =
      'Interactive view ready: "Chart v2" (view_id=v0123456789abcdef, revision=4). ' +
      "It is shown to the user in the Reverie view panel. Summary: refreshed.";
    expect(parseRenderViewResult(out)).toMatchObject({ viewId: "v0123456789abcdef", revision: 4, title: "Chart v2" });
  });

  it("returns null for a render_view failure line or unrelated prose", () => {
    expect(
      parseRenderViewResult("render_view rejected the artifact: artifact resolves outside the workspace and is refused."),
    ).toBeNull();
    expect(parseRenderViewResult("Here is prose that mentions a view_id but carries no handle.")).toBeNull();
    expect(parseRenderViewResult("")).toBeNull();
  });

  it("refuses a non-string, a non-positive revision, or a non-numeric revision", () => {
    expect(parseRenderViewResult(null)).toBeNull();
    expect(parseRenderViewResult({ viewId: "v1", revision: 1 })).toBeNull();
    expect(parseRenderViewResult("ready (view_id=vx, revision=0).")).toBeNull();
    expect(parseRenderViewResult("ready (view_id=vx, revision=two).")).toBeNull();
  });
});
