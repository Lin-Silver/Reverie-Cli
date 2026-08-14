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

function eventLifecycleKey(event: Record<string, unknown>): string {
  const activityId = String(event.activity_id ?? "").trim();
  if (activityId) return `activity:${activityId}`;

  const eventType = String(event.event ?? event.type ?? "").trim().toLowerCase();
  const toolCallId = String(event.tool_call_id ?? "").trim();
  if (toolCallId && ["tool_start", "tool_result"].includes(eventType)) {
    return `tool:${toolCallId}`;
  }
  return "";
}

function mergeActivityEvents(
  existing: Array<Record<string, unknown>>,
  incoming: Array<Record<string, unknown>>,
): Array<Record<string, unknown>> {
  const merged = [...existing];
  for (const event of incoming) {
    const lifecycleKey = eventLifecycleKey(event);
    if (lifecycleKey) {
      const lifecycleIndex = merged.findIndex((candidate) => eventLifecycleKey(candidate) === lifecycleKey);
      if (lifecycleIndex >= 0) {
        merged[lifecycleIndex] = event;
        continue;
      }
    }
    const identity = JSON.stringify(event);
    if (!merged.some((candidate) => JSON.stringify(candidate) === identity)) merged.push(event);
  }
  return merged.slice(-LIVE_STREAM_EVENT_LIMIT);
}

export function mergeLiveTurnBatch(turn: LiveTurn, batch: LiveTurnBatch): LiveTurn {
  const events = batch.events.length
    ? mergeActivityEvents(turn.events, batch.events)
    : turn.events;
  return {
    ...turn,
    assistantText: turn.assistantText + batch.assistantText,
    reasoningText: turn.reasoningText + batch.reasoningText,
    events,
  };
}
