import { describe, expect, it } from "vitest";
import { messageReasoningText, previousTurnBoundary, resolveToolResultNames, sessionIsEmpty, toolCallNames, toolCallRecords, visibleSessionMessages } from "./session-utils";
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
