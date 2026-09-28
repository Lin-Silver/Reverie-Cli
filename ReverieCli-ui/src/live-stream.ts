import type { LiveTurn, TurnSegment } from "./types";

export const LIVE_STREAM_RENDER_INTERVAL_MS = 40;
export const LIVE_STREAM_EVENT_LIMIT = 200;

export interface LiveTurnBatch {
  assistantText: string;
  reasoningText: string;
  events: Array<Record<string, unknown>>;
  ordered?: Array<{ kind: "assistant" | "reasoning"; text: string } | { kind: "activity"; event: Record<string, unknown> }>;
}

export function emptyLiveTurnBatch(): LiveTurnBatch {
  return { assistantText: "", reasoningText: "", events: [], ordered: [] };
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
  // Index the stored events once. Scanning them per incoming event -- with a
  // JSON.stringify of each candidate for the identity check -- made a long turn
  // quadratic in the number of activity rows, and tool payloads are not small.
  const lifecycleIndexes = new Map<string, number>();
  const identities = new Set<string>();
  merged.forEach((event, index) => {
    const lifecycleKey = eventLifecycleKey(event);
    if (lifecycleKey) lifecycleIndexes.set(lifecycleKey, index);
    // Only events without a lifecycle key are ever compared by identity, so
    // stringifying the rest would be wasted work.
    else identities.add(JSON.stringify(event));
  });
  for (const event of incoming) {
    const lifecycleKey = eventLifecycleKey(event);
    if (lifecycleKey) {
      const lifecycleIndex = lifecycleIndexes.get(lifecycleKey);
      if (lifecycleIndex !== undefined) {
        merged[lifecycleIndex] = event;
        continue;
      }
      lifecycleIndexes.set(lifecycleKey, merged.length);
      merged.push(event);
      continue;
    }
    const identity = JSON.stringify(event);
    if (identities.has(identity)) continue;
    identities.add(identity);
    merged.push(event);
  }
  return merged.slice(-LIVE_STREAM_EVENT_LIMIT);
}

function mergeTurnSegments(turn: LiveTurn, batch: LiveTurnBatch): TurnSegment[] {
  const segments: TurnSegment[] = [...(turn.segments ?? [
    ...(turn.reasoningText ? [{ kind: "reasoning" as const, text: turn.reasoningText }] : []),
    ...(turn.assistantText ? [{ kind: "assistant" as const, text: turn.assistantText }] : []),
    ...(turn.events.length ? [{ kind: "activity" as const, events: turn.events }] : []),
  ])];
  const updates = batch.ordered?.length ? batch.ordered : [
    ...(batch.reasoningText ? [{ kind: "reasoning" as const, text: batch.reasoningText }] : []),
    ...(batch.assistantText ? [{ kind: "assistant" as const, text: batch.assistantText }] : []),
    ...batch.events.map(event => ({ kind: "activity" as const, event })),
  ];
  for (const update of updates) {
    const last = segments.at(-1);
    if (update.kind !== "activity") {
      if (!update.text) continue;
      if (last?.kind === update.kind) segments[segments.length - 1] = { kind: update.kind, text: last.text + update.text };
      else segments.push({ kind: update.kind, text: update.text });
      continue;
    }
    const key = eventLifecycleKey(update.event);
    let replaced = false;
    if (key) {
      for (let index = segments.length - 1; index >= 0; index -= 1) {
        const segment = segments[index];
        if (segment.kind !== "activity") continue;
        const eventIndex = segment.events.findIndex(event => eventLifecycleKey(event) === key);
        if (eventIndex < 0) continue;
        const events = [...segment.events];
        events[eventIndex] = { ...events[eventIndex], ...update.event };
        segments[index] = { kind: "activity", events };
        replaced = true;
        break;
      }
    }
    if (replaced) continue;
    if (last?.kind === "activity") segments[segments.length - 1] = { kind: "activity", events: [...last.events, update.event] };
    else segments.push({ kind: "activity", events: [update.event] });
  }
  return segments;
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
    segments: mergeTurnSegments(turn, batch),
  };
}
