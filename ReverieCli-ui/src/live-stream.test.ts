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
});
