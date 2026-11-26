// MCP stdio server (newline-delimited JSON-RPC 2.0) exposing the same typed
// tools. For MCP-capable hosts; Reverie CLI 3.0 uses the CLI path until its
// MCP support lands. Zero dependencies.
import readline from "node:readline";
import { toolSchemas, callTool, VERSION } from "./tools.mjs";

const SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"];

export async function handleMessage(msg) {
  const reply = (result) => ({ jsonrpc: "2.0", id: msg.id, result });
  const fail = (code, message) => ({ jsonrpc: "2.0", id: msg.id ?? null, error: { code, message } });
  if (msg.jsonrpc !== "2.0" || typeof msg.method !== "string") return fail(-32600, "Invalid Request");
  const isNotification = msg.id === undefined;
  switch (msg.method) {
    case "initialize": {
      const requested = msg.params?.protocolVersion;
      return reply({
        protocolVersion: SUPPORTED.includes(requested) ? requested : SUPPORTED[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "reverie-motion", version: VERSION },
        instructions: "Motion design runtime: inspect → design → preview → critique/autofix → export. All tools take `project` (directory); files stay inside it.",
      });
    }
    case "notifications/initialized":
    case "notifications/cancelled":
      return null;
    case "ping":
      return reply({});
    case "tools/list":
      return reply({ tools: toolSchemas() });
    case "tools/call": {
      const name = msg.params?.name;
      try {
        const result = await callTool(name, msg.params?.arguments ?? {});
        return reply({ content: [{ type: "text", text: JSON.stringify(result, null, 2) }], structuredContent: result, isError: false });
      } catch (error) {
        if (error.code === "TOOL_UNKNOWN") return fail(-32602, error.message);
        const payload = { code: error.code ?? "INTERNAL", message: error.message, ...(error.errors ? { errors: error.errors } : {}), ...(error.problems ? { problems: error.problems } : {}) };
        return reply({ content: [{ type: "text", text: JSON.stringify(payload, null, 2) }], isError: true });
      }
    }
    default:
      return isNotification ? null : fail(-32601, `Method not found: ${msg.method}`);
  }
}

export async function serveMcp(input = process.stdin, output = process.stdout) {
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  const pending = new Set();
  for await (const line of rl) {
    if (!line.trim()) continue;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      output.write(JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }) + "\n");
      continue;
    }
    const job = handleMessage(msg).then((res) => {
      if (res) output.write(JSON.stringify(res) + "\n");
    });
    pending.add(job);
    job.finally(() => pending.delete(job));
  }
  await Promise.all(pending);
}
