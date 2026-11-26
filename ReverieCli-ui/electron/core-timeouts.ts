// Workspace/session discovery can be cold after an update or a large history
// migration, so initialization gets a longer budget than ordinary IPC calls.
const CORE_INITIALIZE_TIMEOUT_MS = 300_000;

export function coreRequestTimeoutMs(action: string): number {
  if (["runPrompt","resumePrompt","compactContext","indexWorkspace","indexSemanticWorkspace","installSemanticResources","selectSemanticResources","rollbackSemanticResources","warmSemanticResources","queryContext","removeSemanticResources","refreshMarket","preparePlugin","updatePlugin"].includes(action)) return 0;
  // callViewTool runs the kernel's gated ToolExecutor behind the human approval
  // gate (up to the kernel's ~300s wait), so it must stream like a prompt rather
  // than trip the ordinary 60s transport deadline mid-approval.
  if (action === "callViewTool") return 0;
  if (action === "completeConnectorAuthorization") return 0;
  if (action === "initialize") return CORE_INITIALIZE_TIMEOUT_MS;
  if (action === "wstyleCommand") return 90_000;
  if (action === "refreshModelSources") return 120_000;
  if (action === "getSession") return 15_000;
  return 60_000;
}
