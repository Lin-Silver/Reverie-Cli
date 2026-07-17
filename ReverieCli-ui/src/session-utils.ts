import type { SessionMessage, SessionState } from "./types";

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
    const rawArguments = call.function?.arguments;
    const argumentsText = typeof rawArguments === "string"
      ? rawArguments
      : rawArguments
        ? JSON.stringify(rawArguments, null, 2)
        : "";
    return [{ name, arguments: argumentsText }];
  });
}
