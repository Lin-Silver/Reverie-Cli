import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { once } from "node:events";
import { afterEach, describe, expect, it } from "vitest";
import { requestCoreShutdown } from "./core-shutdown";

const children: ChildProcessWithoutNullStreams[] = [];
const closeEvents = new Map<ChildProcessWithoutNullStreams, Promise<unknown>>();

function launch(source: string) {
  const child = spawn(process.execPath, ["-e", source], { windowsHide: true, stdio: "pipe" });
  children.push(child);
  closeEvents.set(child, once(child, "close"));
  return child;
}

afterEach(async () => {
  for (const child of children.splice(0)) {
    if (child.exitCode === null && child.signalCode === null) child.kill();
    await closeEvents.get(child);
    closeEvents.delete(child);
  }
});

describe("desktop kernel shutdown", () => {
  it("lets a real protocol child read shutdown and exit normally", async () => {
    const child = launch(`
      const readline = require("node:readline");
      const lines = readline.createInterface({ input: process.stdin });
      lines.on("line", line => {
        const message = JSON.parse(line);
        if (message.action === "shutdown") process.stdout.write("shutdown received\\n", () => process.exit(0));
      });
    `);
    let output = "";
    child.stdout.on("data", data => { output += data.toString(); });
    expect(await requestCoreShutdown(child)).toBe(true);
    await closeEvents.get(child);
    expect(output).toContain("shutdown received");
    expect(child.exitCode).toBe(0);
    expect(child.signalCode).toBeNull();
    expect(child.killed).toBe(false);
  });

  it("stops the active conversation before closing its protocol child", async () => {
    const child = launch(`
      const readline = require("node:readline");
      let stopped = false;
      readline.createInterface({ input: process.stdin }).on("line", line => {
        const message = JSON.parse(line);
        if (message.action === "stopPrompt" && message.payload.sessionId === "original-conversation") stopped = true;
        if (message.action === "shutdown") process.exit(stopped ? 0 : 7);
      });
    `);
    expect(await requestCoreShutdown(child, "original-conversation")).toBe(true);
    await closeEvents.get(child);
    expect(child.exitCode).toBe(0);
  });

  it("bounds waiting when a real child ignores shutdown and EOF", async () => {
    const child = launch("process.stdin.resume(); setInterval(() => {}, 1000);");
    expect(await requestCoreShutdown(child)).toBe(false);
    expect(child.exitCode).toBeNull();
    expect(child.killed).toBe(false);
  });

  it("reports a closed input pipe without an unhandled stream error", async () => {
    const child = launch('process.stdin.destroy(); process.stdout.write("ready\\n"); setInterval(() => {}, 1000);');
    await once(child.stdout, "data");
    expect(await requestCoreShutdown(child)).toBe(false);
    expect(child.killed).toBe(false);
  });
});
