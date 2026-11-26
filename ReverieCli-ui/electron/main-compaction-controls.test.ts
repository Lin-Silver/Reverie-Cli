import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import { samePath } from "./workspace-lifecycle";

// Exercise the actual host branches without launching Electron or a provider.
const source = readFileSync(new URL("./main.ts", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const compactStart = source.indexOf('  if (action === "compactContext") {');
const compactEnd = source.indexOf('  if (["runPrompt", "resumePrompt", "callViewTool"].includes(action)) {', compactStart);
const stopStart = source.indexOf('  if (["stopPrompt", "steerPrompt", "pausePrompt", "continuePrompt"].includes(action)) {');
const stopEnd = source.indexOf('  if (action === "resolveApproval" || action === "resolveUserInput") {', stopStart);
if ([compactStart, compactEnd, stopStart, stopEnd].some(index => index < 0)) throw new Error("Compaction host routing could not be located.");
// Const assertions have no runtime behavior; all executable branches stay intact.
const body = (source.slice(compactStart, compactEnd) + source.slice(stopStart, stopEnd)).replace(/\s+as const\b/g, "");
const route = new Function("action", "payload", "bridge", "path", "randomUUID", "samePath", "compactions", "coordinator", "assertCoreResponse", "executors", "stopBeforeStart", "mainWindow", `return (async () => {${body}})();`);

function harness() {
  const root = path.resolve("compaction-project");
  const worker = { getProjectRoot: () => root, request: vi.fn(), hasActivePrompt: () => true };
  const compactions = new Map<string, { worker: typeof worker; root: string; sessionId: string; runId: string; assistantId?: "aio" }>();
  const coordinator = { find: vi.fn(), cancelQueued: vi.fn(() => false) };
  const executors = new Map<string, { worker: typeof worker; root: string; sessionId: string; runId: string }>();
  const sendEvent = vi.fn();
  const invoke = (action: string, payload: Record<string, unknown>) => route(action, payload, worker, path, () => "generated-compact-id", samePath, compactions, coordinator, (_action: string, response: unknown) => response, executors, new Set(), { webContents: { send: sendEvent } }) as Promise<unknown>;
  return { root, worker, compactions, coordinator, executors, invoke, sendEvent };
}

describe("desktop manual context compaction routing", () => {
  it("registers the real bridge and clears only its own operation after completion", async () => {
    const { root, worker, compactions, invoke } = harness();
    let release: (value: unknown) => void = () => {};
    worker.request.mockReturnValue(new Promise(resolve => { release = resolve; }));
    const pending = invoke("compactContext", { sessionId: "conversation", runId: "compact-1", focus: "Preserve the task" });
    expect(compactions.get("compact-1")).toMatchObject({ worker, root, sessionId: "conversation", runId: "compact-1" });
    expect(worker.request).toHaveBeenCalledWith("compactContext", { projectRoot: root, sessionId: "conversation", runId: "compact-1", focus: "Preserve the task" }, expect.any(Function));
    const other = { worker, root, sessionId: "another-conversation", runId: "compact-2" };
    compactions.set("compact-2", other);
    release({ type: "context.compacted", success: false });
    await expect(pending).resolves.toMatchObject({ success: false });
    expect(compactions.has("compact-1")).toBe(false);
    expect(compactions.get("compact-2")).toBe(other);
    expect(worker.request).toHaveBeenCalledTimes(1);
  });

  it("preserves a kernel failure and releases the registration", async () => {
    const { worker, compactions, invoke } = harness();
    worker.request.mockRejectedValue(new Error("Context reduction was cancelled."));
    await expect(invoke("compactContext", { sessionId: "conversation", runId: "compact-1" })).rejects.toThrow("Context reduction was cancelled.");
    expect(compactions.size).toBe(0);
  });

  it("preserves native event identities and supplies the AiO namespace", async () => {
    const { root, worker, invoke, sendEvent } = harness();
    worker.request.mockImplementation(async (_action, _payload, onEvent) => {
      onEvent({ type: "prompt.event", event: { type: "context.compaction.started", project_root: root, session_id: "branch", run_id: "compact-aio" } });
      return { type: "context.compacted", success: true };
    });
    await invoke("compactContext", { projectRoot: root, sessionId: "branch", runId: "compact-aio", assistantId: "aio" });
    expect(sendEvent).toHaveBeenCalledWith("core:event", { type: "prompt.event", event: { type: "context.compaction.started", project_root: root, session_id: "branch", run_id: "compact-aio", assistant_id: "aio" } });
  });

  it("routes a stop to the selected compaction without touching the ordinary executor", async () => {
    const { root, worker, compactions, coordinator, invoke } = harness();
    compactions.set("compact-1", { worker, root, sessionId: "conversation", runId: "compact-1" });
    worker.request.mockResolvedValue({ type: "run.control", state: "stopping", run_id: "compact-1" });
    await expect(invoke("stopPrompt", { projectRoot: root, sessionId: "conversation", runId: "compact-1" })).resolves.toMatchObject({ state: "stopping" });
    expect(worker.request).toHaveBeenCalledWith("stopPrompt", { projectRoot: root, sessionId: "conversation", runId: "compact-1" });
    expect(coordinator.find).not.toHaveBeenCalled();
    expect(coordinator.cancelQueued).not.toHaveBeenCalled();
    expect(compactions.has("compact-1")).toBe(true);
  });

  it.each([
    { projectRoot: "other-project" },
    { sessionId: "other-conversation" },
    { assistantId: "aio" },
  ])("rejects a mismatched compaction owner %j", async override => {
    const { root, worker, compactions, coordinator, invoke } = harness();
    compactions.set("compact-1", { worker, root, sessionId: "conversation", runId: "compact-1" });
    await expect(invoke("stopPrompt", { projectRoot: root, sessionId: "conversation", runId: "compact-1", ...override })).rejects.toThrow("different project or conversation");
    expect(worker.request).not.toHaveBeenCalled();
    expect(coordinator.cancelQueued).not.toHaveBeenCalled();
  });

  it("does not let an expired compaction stop a later prompt in the same conversation", async () => {
    const { root, worker, coordinator, executors, invoke } = harness();
    coordinator.find.mockReturnValue({ id: "new-executor" });
    executors.set("new-executor", { worker, root, sessionId: "conversation", runId: "new-prompt" });
    await expect(invoke("stopPrompt", { projectRoot: root, sessionId: "conversation", runId: "old-compact" })).rejects.toThrow("no longer active");
    expect(worker.request).not.toHaveBeenCalled();
    expect(coordinator.cancelQueued).not.toHaveBeenCalled();
  });
});
