import type { SessionMessage, SessionState } from "./types";
import { isThinkTool } from "./thinking-tool";

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
  ].map(textFragments).find((value) => value.trim())?.trim() ?? "";
}

export function visibleSessionMessages(messages: SessionMessage[]): SessionMessage[] {
  return messages.filter((message) => message.role !== "system");
}

export type TranscriptRow =
  | { kind: "message"; index: number; message: SessionMessage }
  | { kind: "activity"; index: number; events: Array<Record<string, unknown>> };

export function groupTranscriptMessages(messages: SessionMessage[]): TranscriptRow[] {
  const rows: TranscriptRow[] = [];
  const calls = new Map<string, Record<string, unknown>>();
  const appendEvent = (event: Record<string, unknown>, index: number) => {
    const last = rows.at(-1);
    if (last?.kind === "activity") last.events.push(event);
    else rows.push({ kind: "activity", index, events: [event] });
  };
  for (const [index, message] of messages.entries()) {
    if (message.role === "tool") {
      const event = calls.get(message.tool_call_id ?? "") ?? {
        tool_name: message.name || "tool", tool_call_id: message.tool_call_id,
      };
      if (!calls.has(message.tool_call_id ?? "")) appendEvent(event, index);
      const success = !/^\s*(error|\[error|failed|exception)/i.test(textFragments(message.content));
      Object.assign(event, { event: "tool_result", output: message.content, success, status: success ? "success" : "error" });
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
      const event = {
        event: "tool_start", tool_name: name, message: name,
        tool_call_id: call.id, status: "working",
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
