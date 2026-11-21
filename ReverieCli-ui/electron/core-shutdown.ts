import type { ChildProcessWithoutNullStreams } from "node:child_process";

export function requestCoreShutdown(child: ChildProcessWithoutNullStreams, sessionId?: string): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);
  return new Promise<boolean>((resolve) => {
    let finished = false;
    const finish = (exited: boolean) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      child.removeListener("exit", onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    const onError = () => finish(false);
    const timer = setTimeout(() => finish(false), 5_000);
    child.once("exit", onExit);
    child.stdin.once("error", onError);
    child.once("close", () => child.stdin.removeListener("error", onError));
    const messages = [
      ...(sessionId === undefined ? [] : [{ id: "desktop-stop-for-shutdown", action: "stopPrompt", payload: { sessionId } }]),
      { id: "desktop-shutdown", action: "shutdown", payload: {} },
    ];
    try {
      child.stdin.end(messages.map(message => JSON.stringify(message)).join("\n") + "\n", "utf8");
    } catch {
      finish(false);
    }
  });
}
