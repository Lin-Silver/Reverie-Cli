/** Shared controller for the pinned ext-apps 2.0.3 method subset. */
import type { BridgeRequestId } from "./view-bridge";

export type ViewInteractionRef = { sessionId: string; viewId: string; revision: number; interactionId?: string };
export type FollowUpSource = "user-gesture" | "component";
export type CoreRequestFn = (action: string, payload: Record<string, unknown>) => Promise<Record<string, unknown>>;
export type ViewInteractionDeps = {
  ref: ViewInteractionRef;
  request: CoreRequestFn;
  onFollowUp?: (text: string, source: FollowUpSource) => void;
};
export type FrameReply =
  | { kind: "response"; id: BridgeRequestId | null; result: unknown }
  | { kind: "error"; id: BridgeRequestId | null; error: { code: number; message: string } }
  | { kind: "drop"; reason: string };
export type InboundVerdict = { method: string; id: BridgeRequestId | null; params: unknown };
const encoder = new TextEncoder();
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Parameters must be an object.");
  return value as Record<string, unknown>;
}
function textBlocks(value: unknown): string {
  if (!Array.isArray(value) || value.some(x => !x || x.type !== "text" || typeof x.text !== "string")) throw new Error("Only text content is supported.");
  return value.map(x => x.text).join("\n");
}
export class ViewInteractionController {
  readonly #deps: ViewInteractionDeps;
  readonly #calls = new Set<string>();
  #revoked = false;
  constructor(deps: ViewInteractionDeps) { this.#deps = deps; }
  get revoked(): boolean { return this.#revoked; }
  revoke(): void { this.#revoked = true; }
  async handle(verdict: InboundVerdict): Promise<FrameReply> {
    if (this.#revoked) return { kind: "drop", reason: "revoked" };
    const { id, method } = verdict;
    try {
      const params = object(verdict.params ?? {});
      let result: unknown;
      if (method === "tools/call" || method === "reverie/call-tool") {
        const toolName = method === "tools/call" ? params.name : params.toolName;
        const callId = method === "tools/call" && id !== null ? (this.#deps.ref.interactionId ? this.#deps.ref.interactionId + ":" : "") + JSON.stringify(id) : params.callId;
        if (typeof toolName !== "string" || !toolName.trim() || typeof callId !== "string" || !callId.trim()) throw new Error("Tool calls require a name and unique request id.");
        if (this.#calls.has(callId)) throw new Error("Duplicate tool request; this operation will not be replayed.");
        this.#calls.add(callId);
        const envelope = await this.#request("callViewTool", { toolName, callId, arguments: object(params.arguments ?? {}), source: "component" });
        if (method === "tools/call" && envelope.toolResult && typeof envelope.toolResult === "object") {
          return this.#revoked ? { kind: "drop", reason: "revoked-late-result" } : { kind: "response", id, result: envelope.toolResult };
        }
        if (envelope.status !== "success") throw new Error(String(envelope.error || envelope.reason || envelope.status || "Tool failed."));
        result = method === "tools/call" ? { content: [{ type: "text", text: String(envelope.output || "") }], structuredContent: envelope.data || {}, isError: false } : envelope;
      } else if (method === "reverie/view-state") {
        if (!Number.isSafeInteger(params.baseRevision) || Number(params.baseRevision) < 0) throw new Error("State requires a baseRevision.");
        result = await this.#request("setViewState", { state: object(params.state), baseRevision: params.baseRevision });
      } else if (method === "ui/update-model-context") {
        const summary = params.summary ?? (textBlocks(params.content ?? []) + (params.structuredContent ? "\n" + JSON.stringify(object(params.structuredContent)) : ""));
        if (typeof summary !== "string" || encoder.encode(summary).byteLength > 8 * 1024) throw new Error("Model context exceeds 8 KiB or is not text.");
        await this.#request("updateViewModelContext", { summary });
        result = {};
      } else if (method === "ui/message") {
        if (params.role !== undefined && params.role !== "user") throw new Error("Only user message proposals are supported.");
        const text = params.text ?? textBlocks(params.content);
        if (typeof text !== "string" || !text.trim() || encoder.encode(text).byteLength > 8 * 1024) throw new Error("A message requires text within 8 KiB.");
        // The frame cannot attest a user gesture. This callback only stages a proposal.
        // The trusted host's button is the sole route to a normal user turn.
        this.#deps.onFollowUp?.(text, "component");
        result = { isError: false, pendingUserConfirmation: true };
      } else if (method === "ui/notifications/initialized") {
        return { kind: "drop", reason: "notification" };
      } else {
        return { kind: "error", id, error: { code: -32601, message: "Method is not supported by this profile." } };
      }
      return this.#revoked ? { kind: "drop", reason: "revoked-late-result" } : { kind: "response", id, result };
    } catch (error) {
      return this.#revoked ? { kind: "drop", reason: "revoked-late-result" } : { kind: "error", id, error: { code: -32000, message: error instanceof Error ? error.message : String(error) } };
    }
  }
  #request(action: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.#deps.request(action, { ...payload, ...this.#deps.ref });
  }
}
