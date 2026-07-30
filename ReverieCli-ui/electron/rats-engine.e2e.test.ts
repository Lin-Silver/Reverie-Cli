import { describe, expect, it } from "vitest";
import { closeSync, mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import readline from "node:readline";

const engineBinary = String(process.env.REVERIE_RATS_ENGINE_BIN ?? "").trim();
const pythonExecutable = String(process.env.REVERIE_RATS_PYTHON ?? "python").trim();

async function waitForExit(child: ReturnType<typeof spawn>, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null) return true;
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), timeoutMs);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve(true);
    });
  });
}

class CoreClient {
  private sequence = 0;
  private readonly pending = new Map<string, { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void }>();
  private readyPromise: Promise<void>;
  private resolveReady!: () => void;

  constructor(readonly child: ChildProcessWithoutNullStreams) {
    this.readyPromise = new Promise((resolve) => { this.resolveReady = resolve; });
    const lines = readline.createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      const message = JSON.parse(line) as Record<string, unknown>;
      if (message.type === "ready") {
        this.resolveReady();
        return;
      }
      const id = String(message.id ?? "");
      const waiter = this.pending.get(id);
      if (!waiter) return;
      this.pending.delete(id);
      if (message.type === "error") waiter.reject(new Error(String(message.error ?? "Core request failed.")));
      else waiter.resolve(message);
    });
    child.once("exit", (code) => {
      for (const waiter of this.pending.values()) waiter.reject(new Error(`Reverie core exited with code ${code}.`));
      this.pending.clear();
    });
  }

  ready(): Promise<void> {
    return this.readyPromise;
  }

  request(action: string, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const id = `e2e-${++this.sequence}`;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.child.stdin.write(`${JSON.stringify({ id, action, payload })}\n`);
    });
  }
}

describe.skipIf(!engineBinary)("RATS integration with a real Reverie Engine", () => {
  it("keeps the RTP session in the Python core and exposes progressive native tools to the desktop", async () => {
    const binary = path.resolve(engineBinary);
    const binaryRoot = path.dirname(binary);
    const localRoot = path.join(binaryRoot, "ReverieLocal");
    const projectRoot = path.join(localRoot, "Projects", "RatsCliDesktopE2E");
    const testTemp = path.join(localRoot, "TestTemp");
    const cliStateRoot = path.join(testTemp, "RatsCliCoreE2E");
    const logPath = path.join(testTemp, "reverie_cli_rats_engine.log");
    const cliPythonRoot = path.resolve(__dirname, "..", "..", "ReverieCli-py");
    mkdirSync(projectRoot, { recursive: true });
    mkdirSync(cliStateRoot, { recursive: true });
    writeFileSync(path.join(projectRoot, "project.godot"), [
      "; Reverie-Cli RATS desktop integration fixture.",
      "config_version=5",
      "",
      "[application]",
      'config/name="Reverie-Cli RATS Integration"',
      'config/features=PackedStringArray("4.8", "GL Compatibility")',
      "",
    ].join("\n"), "utf8");

    const log = openSync(logPath, "w");
    const engine = spawn(binary, ["--editor", "--headless", "--path", projectRoot, "--quit-after", "1200"], {
      cwd: binaryRoot,
      windowsHide: true,
      stdio: ["ignore", log, log],
      env: {
        ...process.env,
        TEMP: testTemp,
        TMP: testTemp,
        REVERIE_RATS: "1",
        REVERIE_RATS_PORT: "0",
        REVERIE_AI_BRIDGE: "0",
      },
    });
    const coreProcess = spawn(pythonExecutable, ["-m", "reverie", "--sdk-bridge"], {
      cwd: projectRoot,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONPATH: cliPythonRoot,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
        REVERIE_APP_ROOT: cliStateRoot,
        TEMP: testTemp,
        TMP: testTemp,
      },
    });
    const core = new CoreClient(coreProcess);

    try {
      await core.ready();
      await core.request("ratsAddEngine", { executable: binary });
      let rats = (await core.request("ratsState")).rats as { services: Array<Record<string, unknown>>; statePath: string };
      const deadline = Date.now() + 60_000;
      while (!rats.services.some((service) => path.resolve(String(service.executable)) === binary) && Date.now() < deadline) {
        if (engine.exitCode !== null) throw new Error(`Reverie Engine exited before RATS discovery (code ${engine.exitCode}).`);
        await new Promise((resolve) => setTimeout(resolve, 100));
        rats = (await core.request("ratsState")).rats as typeof rats;
      }
      expect(path.resolve(rats.statePath)).toBe(path.resolve(cliStateRoot, ".reverie", "rats", "settings.json"));
      const available = rats.services.find((service) => path.resolve(String(service.executable)) === binary);
      expect(available).toMatchObject({ protocol: "reverie.rtp/1", connection: "available", enabled: false });
      expect(Number(available?.nativeToolCount)).toBeGreaterThanOrEqual(35);

      rats = (await core.request("ratsSetEnabled", { executable: binary, enabled: true, permissions: ["read"] })).rats as typeof rats;
      const connected = rats.services.find((service) => path.resolve(String(service.executable)) === binary);
      expect(connected).toMatchObject({ connection: "connected", enabled: true, sessionActive: true });
      expect((connected?.tools as Array<Record<string, unknown>>).some((tool) => tool.name === "project.status")).toBe(true);
      expect(JSON.stringify(rats)).not.toContain("control_token");
      expect(JSON.stringify(rats)).not.toContain("session_token");

      const tools = (await core.request("listTools", { mode: "reverie" })).tools as Array<Record<string, unknown>>;
      expect(tools.some((tool) => tool.kind === "rats" && tool.name === "rats_catalog")).toBe(true);
      expect(tools.some((tool) => tool.kind === "rats" && tool.name === "rats_reverie_engine_ping")).toBe(true);
      expect(tools.some((tool) => tool.kind === "rats" && tool.name === "rats_reverie_engine_project_status")).toBe(true);

      const definitions = (await core.request("ratsDescribe", {
        serviceId: connected?.serviceId,
        names: ["ping", "project.status"],
      })).definitions as Array<Record<string, unknown>>;
      expect(definitions.map((definition) => definition.name)).toEqual(["ping", "project.status"]);

      rats = (await core.request("ratsSetEnabled", { executable: binary, enabled: false, permissions: [] })).rats as typeof rats;
      expect(rats.services.find((service) => path.resolve(String(service.executable)) === binary))
        .toMatchObject({ connection: "available", enabled: false, sessionActive: false });
      await core.request("shutdown");
      expect(await waitForExit(coreProcess, 10_000)).toBe(true);
      expect(await waitForExit(engine, 35_000)).toBe(true);
      expect(engine.exitCode).toBe(0);
    } finally {
      if (coreProcess.exitCode === null) {
        coreProcess.kill();
        await waitForExit(coreProcess, 10_000);
      }
      if (engine.exitCode === null) {
        engine.kill();
        await waitForExit(engine, 10_000);
      }
      closeSync(log);
      rmSync(projectRoot, { recursive: true, force: true });
      rmSync(cliStateRoot, { recursive: true, force: true });
    }
  }, 90_000);
});
