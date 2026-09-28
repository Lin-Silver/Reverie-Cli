import { describe, expect, it } from "vitest";

import {
  LIVE_STREAM_EVENT_LIMIT,
  emptyLiveTurnBatch,
  mergeLiveTurnBatch,
} from "./live-stream";
import type { LiveTurn } from "./types";

const turn: LiveTurn = {
  userText: "hello",
  assistantText: "A",
  reasoningText: "R",
  events: [],
  error: "",
  startedAt: 1,
};

describe("live stream batching", () => {
  it("interleaves commentary and tools even when they arrive in one render batch", () => {
    const merged = mergeLiveTurnBatch({ ...turn, assistantText: "", reasoningText: "", segments: [] }, {
      ...emptyLiveTurnBatch(),
      ordered: [
        { kind: "assistant", text: "I will inspect the files." },
        { kind: "activity", event: { event: "tool_start", tool_call_id: "a", tool_name: "read_file" } },
        { kind: "activity", event: { event: "tool_result", tool_call_id: "a", output: "source" } },
        { kind: "assistant", text: "Now I will run the tests." },
        { kind: "activity", event: { event: "tool_start", tool_call_id: "b", tool_name: "command_exec" } },
      ],
    });
    expect(merged.segments?.map(segment => segment.kind)).toEqual(["assistant", "activity", "assistant", "activity"]);
    expect(merged.segments?.[1]).toMatchObject({ events: [{ tool_name: "read_file", output: "source" }] });
  });

  it("attaches out-of-order parallel results to their original tool group", () => {
    const existing = mergeLiveTurnBatch({ ...turn, segments: [] }, {
      ...emptyLiveTurnBatch(),
      ordered: [
        { kind: "activity", event: { event: "tool_start", tool_call_id: "a" } },
        { kind: "activity", event: { event: "tool_start", tool_call_id: "b" } },
        { kind: "assistant", text: "An update." },
      ],
    });
    const merged = mergeLiveTurnBatch(existing, {
      ...emptyLiveTurnBatch(),
      ordered: [
        { kind: "activity", event: { event: "tool_result", tool_call_id: "b", output: "second" } },
        { kind: "activity", event: { event: "tool_result", tool_call_id: "a", output: "first" } },
      ],
    });
    expect(merged.segments).toMatchObject([
      { kind: "activity", events: [{ tool_call_id: "a", output: "first" }, { tool_call_id: "b", output: "second" }] },
      { kind: "assistant", text: "An update." },
    ]);
  });
  it("merges assistant and reasoning deltas without losing their order", () => {
    const merged = mergeLiveTurnBatch(turn, {
      assistantText: "BC",
      reasoningText: "ST",
      events: [{ type: "tool.started" }],
    });

    expect(merged.assistantText).toBe("ABC");
    expect(merged.reasoningText).toBe("RST");
    expect(merged.events).toEqual([{ type: "tool.started" }]);
  });

  it("bounds ephemeral activity history while keeping the newest events", () => {
    const events = Array.from({ length: LIVE_STREAM_EVENT_LIMIT + 25 }, (_, index) => ({ index }));
    const merged = mergeLiveTurnBatch(turn, { ...emptyLiveTurnBatch(), events });

    expect(merged.events).toHaveLength(LIVE_STREAM_EVENT_LIMIT);
    expect(merged.events[0]).toEqual({ index: 25 });
    expect(merged.events.at(-1)).toEqual({ index: LIVE_STREAM_EVENT_LIMIT + 24 });
  });

  it("deduplicates identical lifecycle events without touching text deltas", () => {
    const existing = { ...turn, events: [{ kind: "stream_event", event: "tool_start", tool_call_id: "call-1" }] };
    const merged = mergeLiveTurnBatch(existing, {
      assistantText: "same same",
      reasoningText: "",
      events: [
        { kind: "stream_event", event: "tool_start", tool_call_id: "call-1" },
        { kind: "stream_event", event: "tool_end", tool_call_id: "call-1" },
      ],
    });

    expect(merged.assistantText).toBe("Asame same");
    expect(merged.events).toHaveLength(2);
    expect(merged.events[1]).toMatchObject({ event: "tool_end" });
  });

  it("replaces model and tool lifecycle starts with their completed state", () => {
    const existing = {
      ...turn,
      events: [
        { event: "model_request", activity_id: "model-1", status: "working" },
        { event: "tool_start", tool_call_id: "call-1", status: "working" },
      ],
    };
    const merged = mergeLiveTurnBatch(existing, {
      assistantText: "",
      reasoningText: "",
      events: [
        { event: "model_response", activity_id: "model-1", status: "success" },
        { event: "tool_result", tool_call_id: "call-1", status: "success", success: true },
      ],
    });

    expect(merged.events).toEqual([
      { event: "model_response", activity_id: "model-1", status: "success" },
      { event: "tool_result", tool_call_id: "call-1", status: "success", success: true },
    ]);
  });
});
