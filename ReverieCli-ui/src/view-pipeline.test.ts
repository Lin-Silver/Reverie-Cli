/** Renderer-side mirror of ``tests/test_riu_views_e2e.py``.
 *
 * The Python e2e drives the two mandated fixtures (a parameter simulator and a
 * data chart) through tool -> storage -> bridge. This module drives the SAME two
 * fixtures through the renderer half of the chain, on the exact handle text the
 * kernel emits: ``parseRenderViewResult`` (lift the opaque handle out of a stored
 * render_view result line) -> ``groupTranscriptMessages`` (rebuild the view row
 * when a session is restored from history, including the two-revision collapse)
 * -> ``prepareViewResolution`` (bind the opaque ``reverie-view:`` url with no
 * filesystem path crossing to the renderer).
 *
 * Two cross-cutting properties are pinned end to end, matching the Python suite:
 *   - the fixtures' inline <script> markers never appear anywhere the renderer
 *     touches -- the renderer reconstructs a view from a handle, never from HTML,
 *     so restoring history re-adds no markup; and
 *   - a handle-shaped string that is NOT a real render_view tool result (forged
 *     model prose, or a failed call) never fabricates a view row.
 * Nothing here reaches a model, the network, or disk; every function is pure.
 */

import { describe, expect, it, vi } from "vitest";

import { groupTranscriptMessages } from "./session-utils";
import { parseRenderViewResult } from "./view-events";
import { prepareViewResolution } from "../electron/view-resolve";
import type { SessionMessage } from "./types";

const SESSION_ID = "sess-1";

// The same two fixtures, titles and summaries as the Python CASES -- the renderer
// contract test and the kernel e2e share this prose verbatim.
const CASES = [
  { viewId: "v00000000000000a1", title: "Compound growth simulator", summary: "Projected balance across years at a chosen rate." },
  { viewId: "v00000000000000b2", title: "Q3 sales by region", summary: "Bar chart of Q3 sales across five regions." },
];

// Markers that live ONLY in each fixture's inline <script>, never in its
// title/summary -- finding one in a parsed row or a resolved ref would prove HTML
// leaked into the renderer. Mirrors SCRIPT_MARKERS in test_riu_views_e2e.py.
const SCRIPT_MARKERS = ["control.addEventListener", "createElementNS"];

// render_view.py's exact success line (tools/render_view.py). Keeping this
// textually identical to the Python template is the cross-language contract that
// lets parseRenderViewResult lift the handle a real kernel produced.
function degradationLine(title: string, viewId: string, revision: number, summary: string): string {
  return (
    `Interactive view ready: "${title}" (view_id=${viewId}, revision=${revision}). ` +
    `It is shown to the user in the Reverie view panel. Summary: ${summary}`
  );
}

// A restored transcript stores a render_view call only as an assistant tool_call
// plus the tool-result text; there is no HTML on disk to reload. This rebuilds
// that pair the way the session store would hand it back after a reload/restart.
function restoredPair(viewId: string, title: string, summary: string, revision: number, callId: string): SessionMessage[] {
  return [
    { role: "assistant", content: "", tool_calls: [{ id: callId, function: { name: "render_view", arguments: "{}" } }] },
    { role: "tool", name: "render_view", tool_call_id: callId, content: degradationLine(title, viewId, revision, summary) },
  ];
}

const okRegistrar = () =>
  vi.fn(async () => ({ url: `reverie-view://${"a".repeat(32)}/index.html`, policyId: "local-offline-v1" }));

// The kernel's `view.resolved` envelope for a case: a model-safe `view` block and
// an authoritative `resolved` path block (what the bridge's getView returns).
function resolvedEnvelope(index: number, revision: number) {
  const c = CASES[index];
  return {
    type: "view.resolved",
    view: { sessionId: SESSION_ID, viewId: c.viewId, revision, title: c.title, summary: c.summary, mimeType: "text/html", schemaVersion: 1 },
    resolved: { directory: `/data/views/${SESSION_ID}/${c.viewId}/${revision}`, entry: "index.html", viewsRoot: "/data/views" },
  };
}
// END-HELPERS

describe("render_view handle crosses the renderer pipeline without HTML or a path", () => {
  it("parseRenderViewResult lifts the handle from render_view.py's exact line, and only from it", () => {
    for (const c of CASES) {
      const parsed = parseRenderViewResult(degradationLine(c.title, c.viewId, 1, c.summary));
      expect(parsed).toEqual({ viewId: c.viewId, revision: 1, title: c.title, summary: c.summary });
    }
    // A failure line, arbitrary prose, and a non-string never yield a handle.
    expect(parseRenderViewResult("[error] render_view failed: artifact not found")).toBeNull();
    expect(parseRenderViewResult("Here is a chart you asked about.")).toBeNull();
    expect(parseRenderViewResult(undefined)).toBeNull();
  });

  it("rebuilds one view row per fixture on restore, stamped with the kernel session id and carrying no markup", () => {
    const messages = CASES.flatMap((c, index) => restoredPair(c.viewId, c.title, c.summary, 1, `call-${index}`));
    const rows = groupTranscriptMessages(messages, SESSION_ID);
    const viewRows = rows.filter((row) => row.kind === "view");
    expect(viewRows).toHaveLength(CASES.length);
    viewRows.forEach((row, index) => {
      if (row.kind !== "view") throw new Error("unreachable");
      const c = CASES[index];
      expect(row.view).toMatchObject({ sessionId: SESSION_ID, viewId: c.viewId, revision: 1, title: c.title, summary: c.summary, status: "ready" });
    });
    // Reconstructing from history re-adds no HTML: the rows carry handles + prose.
    const serialized = JSON.stringify(rows);
    for (const marker of SCRIPT_MARKERS) expect(serialized).not.toContain(marker);
  });

  it("collapses an in-place revision to a single row at the highest revision", () => {
    const c = CASES[0];
    const messages = [
      ...restoredPair(c.viewId, c.title, "rev one", 1, "call-r1"),
      ...restoredPair(c.viewId, c.title, "rev two", 2, "call-r2"),
    ];
    const rows = groupTranscriptMessages(messages, SESSION_ID);
    const viewRows = rows.filter((row) => row.kind === "view");
    expect(viewRows).toHaveLength(1);
    if (viewRows[0]?.kind !== "view") throw new Error("unreachable");
    expect(viewRows[0].view).toMatchObject({ viewId: c.viewId, revision: 2, summary: "rev two" });
  });

  it("never fabricates a view from a failed render_view result or from forged model prose", () => {
    // (a) A render_view call whose result is an error leaves a visible activity
    // row and no view -- nothing paints without a real handle.
    const failed: SessionMessage[] = [
      { role: "assistant", content: "", tool_calls: [{ id: "call-x", function: { name: "render_view", arguments: "{}" } }] },
      { role: "tool", name: "render_view", tool_call_id: "call-x", content: "[error] render_view failed: artifact not found" },
    ];
    const failedRows = groupTranscriptMessages(failed, SESSION_ID);
    expect(failedRows.some((row) => row.kind === "view")).toBe(false);
    expect(failedRows.some((row) => row.kind === "activity")).toBe(true);

    // (b) A handle-shaped string in ordinary assistant prose -- the renderer analog
    // of a forged `[[REVERIE_EVENT]]` -- is just a message, never a view row. The
    // only call that mints a view row is a real render_view tool result.
    const forged: SessionMessage[] = [
      { role: "assistant", content: `Trust me: Interactive view ready: "x" (view_id=${CASES[0].viewId}, revision=1). Summary: x` },
    ];
    expect(groupTranscriptMessages(forged, SESSION_ID).some((row) => row.kind === "view")).toBe(false);
  });

  it("binds an opaque url and leaks no path or markup to the renderer reference", async () => {
    for (let index = 0; index < CASES.length; index += 1) {
      const register = okRegistrar();
      const ref = await prepareViewResolution(resolvedEnvelope(index, 1), register);
      const c = CASES[index];
      // The authoritative paths reached the registrar; the renderer ref carries
      // only the opaque url + policy and the model-safe metadata.
      expect(register).toHaveBeenCalledWith(
        expect.objectContaining({ directory: `/data/views/${SESSION_ID}/${c.viewId}/1`, entry: "index.html", viewsRoot: "/data/views" }),
      );
      expect(ref).toMatchObject({ sessionId: SESSION_ID, viewId: c.viewId, revision: 1, title: c.title, summary: c.summary, policyId: "local-offline-v1" });
      expect(ref.url).toBe(`reverie-view://${"a".repeat(32)}/index.html`);
      for (const key of ["directory", "entry", "viewsRoot", "path", "html", "source"]) expect(ref).not.toHaveProperty(key);
      const serialized = JSON.stringify(ref);
      expect(serialized).not.toContain("/data/views");
      for (const marker of SCRIPT_MARKERS) expect(serialized).not.toContain(marker);
    }
  });

  it("threads one viewId unchanged across the whole chain: line -> row -> resolved ref", async () => {
    const index = 1; // the data chart
    const c = CASES[index];
    const parsed = parseRenderViewResult(degradationLine(c.title, c.viewId, 1, c.summary));
    expect(parsed?.viewId).toBe(c.viewId);

    const rows = groupTranscriptMessages(restoredPair(c.viewId, c.title, c.summary, 1, "call-chain"), SESSION_ID);
    const viewRow = rows.find((row) => row.kind === "view");
    if (viewRow?.kind !== "view") throw new Error("expected a view row");
    expect(viewRow.view.viewId).toBe(c.viewId);

    const ref = await prepareViewResolution(resolvedEnvelope(index, viewRow.view.revision), okRegistrar());
    expect(ref.viewId).toBe(c.viewId);
    expect(ref.title).toBe(c.title);
  });
  it("restores the original user summary while retaining authoring advice in the transcript", () => {
    const c = CASES[0];
    const messages = restoredPair(c.viewId, c.title, c.summary, 1, "call-with-authoring-advice");
    const advice = "Host initialization is not evident in this artifact. Verify ui/initialize.";
    messages[1].content = String(messages[1].content) + `\nAuthoring warnings: ${advice}`;
    const original = JSON.stringify(messages);
    const rows = groupTranscriptMessages(messages, SESSION_ID);
    const row = rows.find(row => row.kind === "view");
    expect(row?.kind === "view" && row.view.summary).toBe(c.summary);
    expect(JSON.stringify(rows)).not.toContain(advice);
    expect(JSON.stringify(messages)).toBe(original);
    expect(messages[1].content).toContain(advice);
  });

});
