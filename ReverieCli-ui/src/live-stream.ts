import type { LiveTurn } from "./types";

export const LIVE_STREAM_RENDER_INTERVAL_MS = 40;
export const LIVE_STREAM_EVENT_LIMIT = 200;

export interface LiveTurnBatch {
  assistantText: string;
  reasoningText: string;
  events: Array<Record<string, unknown>>;
}

export function emptyLiveTurnBatch(): LiveTurnBatch {
  return { assistantText: "", reasoningText: "", events: [] };
}

export function mergeLiveTurnBatch(turn: LiveTurn, batch: LiveTurnBatch): LiveTurn {
  const events = batch.events.length
    ? [...turn.events, ...batch.events].slice(-LIVE_STREAM_EVENT_LIMIT)
    : turn.events;
  return {
    ...turn,
    assistantText: turn.assistantText + batch.assistantText,
    reasoningText: turn.reasoningText + batch.reasoningText,
    events,
  };
}
