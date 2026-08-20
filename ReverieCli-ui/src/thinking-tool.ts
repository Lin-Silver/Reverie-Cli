/**
 * Shared vocabulary for the experimental Thinking Tool.
 *
 * Mirrors `reverie/thinking_tool.py` so the desktop transcript and the terminal
 * agree on which calls are reasoning and on what text they show.
 */

/** Every accepted spelling of the tool, lowercased. */
export const THINK_TOOL_NAMES = new Set(["deep_think", "think", "think_tool", "deep_thinking"]);

/** Whether a tool name refers to the Thinking Tool scratchpad. */
export function isThinkTool(name: unknown): boolean {
  return THINK_TOOL_NAMES.has(String(name ?? "").trim().toLowerCase());
}

function clean(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return String(value).trim();
}

/**
 * Renderable thinking text from a `deep_think` call's arguments.
 *
 * Accepts the raw JSON string the model streamed as well as a parsed object, so
 * a half-finished call still shows something instead of collapsing to nothing.
 */
export function thinkToolText(args: unknown): string {
  let payload: unknown = args;
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    if (!trimmed) return "";
    try {
      payload = JSON.parse(trimmed);
    } catch {
      // Arguments still streaming in, or not JSON at all -- show them verbatim.
      return trimmed;
    }
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
  const record = payload as Record<string, unknown>;
  const topic = clean(record.topic);
  const thought = clean(record.thought);
  const nextStep = clean(record.next_step);
  const sections: string[] = [];
  if (topic) sections.push(`**${topic}**`);
  if (thought) sections.push(thought);
  if (nextStep) sections.push(`Next: ${nextStep}`);
  return sections.join("\n\n").trim();
}
