import type { SessionMessage, SessionState, ViewSegment } from "./types";
import { isThinkTool } from "./thinking-tool";
import { parseRenderViewResult } from "./view-events";

export interface ToolCallRecord {
  name: string;
  arguments: string;
}

function textFragments(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(textFragments).filter(Boolean).join("\n");
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return textFragments(record.text ?? record.content ?? record.value);
}

export function messageReasoningText(message: SessionMessage): string {
  return [
    message.reasoning_content,
    message.thinking,
    message.reasoning,
    message.analysis,
  ].map(textFragments).find((value) => value.trim()) ?? "";
}

export function visibleSessionMessages(messages: SessionMessage[]): SessionMessage[] {
  return messages.filter((message) => message.role !== "system");
}

export type TranscriptRow =
  | { kind: "message"; index: number; message: SessionMessage }
  | { kind: "activity"; index: number; events: Array<Record<string, unknown>> }
  | { kind: "view"; index: number; view: ViewSegment };

// render_view and its aliases (see tools/render_view.py) announce an interactive
// view rather than an ordinary tool result.
const RENDER_VIEW_NAMES = new Set(["render_view", "show_view", "interactive_view"]);
const isRenderViewName = (name: string | undefined): boolean => RENDER_VIEW_NAMES.has((name ?? "").trim());

export function groupTranscriptMessages(messages: SessionMessage[], sessionId = ""): TranscriptRow[] {
  const rows: TranscriptRow[] = [];
  const calls = new Map<string, Record<string, unknown>>();
  const renderViewCalls = new Set<string>();
  const viewRowByViewId = new Map<string, number>();
  const appendEvent = (event: Record<string, unknown>, index: number) => {
    const last = rows.at(-1);
    if (last?.kind === "activity") last.events.push(event);
    else rows.push({ kind: "activity", index, events: [event] });
  };
  // A view handle survives a reload only as the render_view result text; dedupe by
  // viewId so the follow-up revisions (which reuse the id) collapse to one row at
  // the highest revision, matching the live stream's in-place replacement.
  const placeView = (index: number, view: ViewSegment) => {
    const existing = viewRowByViewId.get(view.viewId);
    if (existing !== undefined) {
      const current = rows[existing];
      if (current.kind === "view" && view.revision >= current.view.revision) {
        rows[existing] = { kind: "view", index: current.index, view };
      }
      return;
    }
    viewRowByViewId.set(view.viewId, rows.length);
    rows.push({ kind: "view", index, view });
  };
  for (const [index, message] of messages.entries()) {
    if (message.role === "tool") {
      const callId = message.tool_call_id ?? "";
      const mcpViewResult = String(calls.get(callId)?.tool_name ?? message.name ?? "").startsWith("mcp_") && parseRenderViewResult(message.content);
      if (renderViewCalls.has(callId) || mcpViewResult) {
        const parsed = parseRenderViewResult(message.content);
        if (parsed) {
          placeView(index, {
            sessionId,
            viewId: parsed.viewId,
            revision: parsed.revision,
            title: parsed.title ?? "",
            summary: parsed.summary ?? "",
            status: "ready",
          });
          continue;
        }
        // render_view FAILED (no handle in the text): fall through so the failure
        // stays a visible activity row and nothing fabricates a view.
      }
      const event = calls.get(callId) ?? {
        tool_name: message.name || (renderViewCalls.has(callId) ? "render_view" : "tool"), tool_call_id: message.tool_call_id,
      };
      if (!calls.has(callId)) appendEvent(event, index);
      const success = !/^\s*(error|\[error|failed|exception)/i.test(textFragments(message.content));
      Object.assign(event, { event: "tool_result", output: message.content, success, status: success ? "success" : "error", detail: "" });
      continue;
    }
    const pureThinkingCall = message.role === "assistant" && !!message.tool_calls?.length
      && message.tool_calls.every((call) => isThinkTool(call.function?.name));
    if (pureThinkingCall && messageReasoningText(message)) {
      rows.push({ kind: "message", index, message: { ...message, content: null, tool_calls: [] } });
    } else if (!pureThinkingCall && (message.role !== "assistant" || textFragments(message.content) || messageReasoningText(message))) {
      rows.push({ kind: "message", index, message: message.tool_calls?.length ? { ...message, tool_calls: [] } : message });
    }
    for (const call of message.tool_calls ?? []) {
      const name = call.function?.name ?? "tool";
      // A view call renders as its own `view` row at result time, never as a
      // generic tool_start activity card.
      if (call.id && isRenderViewName(name)) {
        renderViewCalls.add(call.id);
        continue;
      }
      const event = {
        event: "tool_start", tool_name: name, message: name,
        tool_call_id: call.id, status: "warning", detail: "No saved result. This operation may have been interrupted.",
        arguments: name.toLowerCase().startsWith("rats_") ? undefined : call.function?.arguments,
      };
      if (call.id) calls.set(call.id, event);
      appendEvent(event, index);
    }
  }
  return rows;
}

export function resolveToolResultNames(messages: SessionMessage[]): SessionMessage[] {
  const toolNames = new Map<string, string>();
  return messages.map((message) => {
    for (const call of message.tool_calls ?? []) {
      const id = String(call.id ?? "").trim();
      const name = String(call.function?.name ?? "").trim();
      if (id && name) toolNames.set(id, name);
    }
    if (message.role !== "tool" || message.name || !message.tool_call_id) return message;
    const name = toolNames.get(message.tool_call_id);
    return name ? { ...message, name } : message;
  });
}

export function sessionIsEmpty(session: SessionState | null): boolean {
  return !session || visibleSessionMessages(session.messages ?? []).length === 0;
}

export function previousTurnBoundary(messages: SessionMessage[]): number | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") return index;
  }
  return null;
}

export function toolCallNames(message: SessionMessage): string[] {
  return toolCallRecords(message).map((call) => call.name);
}

export function toolCallRecords(message: SessionMessage): ToolCallRecord[] {
  return (message.tool_calls ?? []).flatMap((call) => {
    const name = call.function?.name?.trim() ?? "";
    if (!name) return [];
    const isRatsTool = name.toLowerCase().startsWith("rats_");
    const rawArguments = call.function?.arguments;
    let argumentsText = "";
    if (!isRatsTool) {
      argumentsText = typeof rawArguments === "string"
        ? rawArguments
        : rawArguments
          ? JSON.stringify(rawArguments, null, 2)
          : "";
    }
    return [{ name, arguments: argumentsText }];
  });
}
