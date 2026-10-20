import { describe, expect, it } from "vitest";
import { groupTranscriptMessages, messageReasoningText, previousTurnBoundary, resolveToolResultNames, sessionIsEmpty, toolCallNames, toolCallRecords, visibleSessionMessages } from "./session-utils";
import type { SessionState } from "./types";

const session = (messages: SessionState["messages"]): SessionState => ({
  id: "session-1",
  name: "Conversation",
  created_at: "",
  updated_at: "",
  metadata: {},
  messages,
});

describe("session interaction helpers", () => {
  it("keeps native reasoning from a failed answerless attempt visible in restored history", () => {
    const reasoning = "  The system prompt says to use tools. Raw model output.\n";
    const rows = groupTranscriptMessages([{ role: "assistant", content: null, reasoning_content: reasoning }]);
    expect(rows).toEqual([{ kind: "message", index: 0, message: { role: "assistant", content: null, reasoning_content: reasoning } }]);
    expect(messageReasoningText(rows[0].kind === "message" ? rows[0].message : { role: "assistant", content: null })).toBe(reasoning);
  });

  it("groups stored calls with matching results after their commentary", () => {
    const rows = groupTranscriptMessages([
      { role: "user", content: "Build it" },
      { role: "assistant", content: "Inspect first", tool_calls: [
        { id: "a", function: { name: "read_file", arguments: '{"path":"app.py"}' } },
        { id: "b", function: { name: "read_file", arguments: '{"path":"tests.py"}' } },
      ] },
      { role: "tool", tool_call_id: "b", content: "tests source" },
      { role: "tool", tool_call_id: "a", content: "app source" },
      { role: "assistant", content: "Verified" },
    ]);
    expect(rows.map(row => row.kind)).toEqual(["message", "message", "activity", "message"]);
    expect(rows[2]).toMatchObject({ events: [
      { tool_call_id: "a", output: "app source" }, { tool_call_id: "b", output: "tests source" },
    ] });
    expect(rows[1]).toMatchObject({ message: { content: "Inspect first", tool_calls: [] } });
  });
  it("does not treat hidden workspace memory as a visible conversation", () => {
    const messages = [{ role: "system", content: "memory" }];
    expect(visibleSessionMessages(messages)).toEqual([]);
    expect(sessionIsEmpty(session(messages))).toBe(true);
  });

  it("rewinds to the beginning of the latest user turn", () => {
    const messages = [
      { role: "system", content: "memory" },
      { role: "user", content: "one" },
      { role: "assistant", content: "answer one" },
      { role: "user", content: "two" },
      { role: "assistant", content: null },
      { role: "tool", content: "result" },
    ];
    expect(previousTurnBoundary(messages)).toBe(3);
  });

  it("extracts persisted tool call names without rendering empty assistant cards", () => {
    expect(toolCallNames({ role: "assistant", content: null, tool_calls: [{ function: { name: "read_file" } }] })).toEqual([
      "read_file",
    ]);
  });

  it("keeps tool arguments available for technical activity disclosures", () => {
    expect(toolCallRecords({
      role: "assistant",
      content: null,
      tool_calls: [{ function: { name: "read_file", arguments: { path: "src/App.tsx" } } }],
    })).toEqual([{ name: "read_file", arguments: '{\n  "path": "src/App.tsx"\n}' }]);
  });

  it("omits RATS tool arguments from UI activity records", () => {
    expect(toolCallRecords({
      role: "assistant",
      content: null,
      tool_calls: [{ function: { name: "rats_reverie_engine_ping", arguments: { token: "secret" } } }],
    })).toEqual([{ name: "rats_reverie_engine_ping", arguments: "" }]);
  });

  it("normalizes provider-specific reasoning fields", () => {
    expect(messageReasoningText({ role: "assistant", content: "", reasoning_content: "native" })).toBe("native");
    expect(messageReasoningText({ role: "assistant", content: "", thinking: [{ text: "provider" }, { text: "trace" }] })).toBe("provider\ntrace");
    expect(messageReasoningText({ role: "assistant", content: "", analysis: { content: "analysis" } })).toBe("analysis");
  });

  it("uses the matching model call name for persisted tool results", () => {
    const messages = resolveToolResultNames([
      { role: "assistant", content: "", tool_calls: [{ id: "call-1", function: { name: "serial_novel" } }] },
      { role: "tool", content: "done", tool_call_id: "call-1" },
    ]);
    expect(messages[1].name).toBe("serial_novel");
  });
});

// Reconstructing an interactive view from a reloaded transcript: the live
// view_ready event is gone, so the render_view tool result must become a `view`
// row carrying the opaque handle (dereferenced later via getView). The handle is
// bound to the kernel session, which the renderer threads in -- the stored text
// never carries it. A render_view FAILURE must stay an ordinary activity row so
// errors remain visible and nothing fabricates a view.
describe("view timeline reconstruction", () => {
  it("restores a registered MCP App handle while keeping plain MCP text as activity", () => {
    const rows = groupTranscriptMessages([
      { role: "assistant", content: "", tool_calls: [{ id: "mcp-1", function: { name: "mcp_official_get_time" } }] },
      { role: "tool", tool_call_id: "mcp-1", content: "2026-10-16T14:00:00Z\nInteractive view ready (view_id=v123, revision=1)." },
      { role: "assistant", content: "", tool_calls: [{ id: "mcp-2", function: { name: "mcp_fixture_missing" } }] },
      { role: "tool", tool_call_id: "mcp-2", content: "Useful text. UI unavailable." },
    ], "session");
    expect(rows.filter(x => x.kind === "view")).toEqual([expect.objectContaining({ view: expect.objectContaining({ viewId: "v123", sessionId: "session" }) })]);
    expect(JSON.stringify(rows)).toContain("Useful text. UI unavailable.");
  });

  const ready = (callId: string, viewId: string, revision: number, title: string, summary: string) => ({
    role: "tool" as const,
    tool_call_id: callId,
    name: "render_view",
    content:
      `Interactive view ready: "${title}" (view_id=${viewId}, revision=${revision}). ` +
      `It is shown to the user in the Reverie view panel. Summary: ${summary}`,
  });

  it("reconstructs a render_view result as a view row carrying the kernel-bound handle", () => {
    const rows = groupTranscriptMessages([
      { role: "user", content: "chart it" },
      { role: "assistant", content: "", tool_calls: [{ id: "c1", function: { name: "render_view" } }] },
      ready("c1", "vabc123", 1, "Sales", "Q3 bars."),
    ], "sess-9");
    expect(rows.map((row) => row.kind)).toEqual(["message", "view"]);
    expect(rows[1]).toMatchObject({
      kind: "view",
      view: { sessionId: "sess-9", viewId: "vabc123", revision: 1, title: "Sales", summary: "Q3 bars.", status: "ready" },
    });
  });

  it("collapses revisions of one view to a single row at the highest revision", () => {
    const rows = groupTranscriptMessages([
      { role: "assistant", content: "", tool_calls: [{ id: "c1", function: { name: "render_view" } }] },
      ready("c1", "vabc", 1, "Chart", "first"),
      { role: "assistant", content: "", tool_calls: [{ id: "c2", function: { name: "render_view" } }] },
      ready("c2", "vabc", 2, "Chart v2", "second"),
    ], "sess-1");
    expect(rows.filter((row) => row.kind === "view")).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "view", view: { viewId: "vabc", revision: 2, title: "Chart v2", summary: "second" } });
  });

  it("keeps a failed render_view as an activity row, never a view", () => {
    const rows = groupTranscriptMessages([
      { role: "assistant", content: "", tool_calls: [{ id: "c1", function: { name: "render_view" } }] },
      { role: "tool", tool_call_id: "c1", name: "render_view", content: "render_view rejected the artifact: artifact resolves outside the workspace and is refused." },
    ], "sess-1");
    expect(rows).toHaveLength(1);
    expect(rows[0].kind).toBe("activity");
  });
});
