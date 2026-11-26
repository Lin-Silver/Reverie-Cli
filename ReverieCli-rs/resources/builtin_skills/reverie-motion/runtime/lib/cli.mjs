// Command-line adapter: `reverie-motion <command> [--flags]` → typed tool call → JSON on stdout.
// This is the path Reverie CLI 3.0 uses (native command_exec, subject to its approval policy).
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { TOOLS, TOOL_BY_CLI, callTool, toolSchemas, VERSION } from "./tools.mjs";
import os from "node:os";
import { findBrowsers, launchBrowser } from "./cdp.mjs";
import { Store } from "./store.mjs";

const SKILL_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const HELP = `reverie-motion ${VERSION} — agent-native motion design runtime

Usage: node <skill>/runtime/bin/reverie-motion.mjs <command> [--project DIR] [options]

Commands (each maps to one typed tool; see \`schema\`):
${TOOLS.map((t) => `  ${t.cli.padEnd(10)} ${t.name}`).join("\n")}
  schema     print all tool JSON schemas
  doctor     check Node, vendored bundle integrity, browsers (--launch to start one)
  mcp        serve the same tools over MCP stdio
  install    copy this skill into <project>/.agents/skills (--scope workspace, default)
             or ~/.agents/skills (--scope user); --update overwrites changed files

Options:
  --input FILE.json        tool input object (merged under explicit flags)
  --KEY VALUE              any top-level tool parameter; repeat for arrays
  --param NAME=VALUE       template parameter (design)
  --action KIND:ARG        click:SEL hover:SEL play:ID toggle:ID flip:ID flip-reverse:ID wait:MS
  --viewport NAME          desktop | mobile (repeatable)
  --story-intent NAME --selector SEL ...   storytelling (design)
Output: one JSON object {ok, tool, result | error}. Exit 0 = ok, 1 = tool error, 2 = usage error.`;

function coerce(prop, raw, name) {
  if (!prop) return raw;
  const type = prop.type ?? prop.anyOf?.[0]?.type;
  if (type === "integer" || type === "number") {
    const n = Number(raw);
    if (!Number.isFinite(n)) throw usage(`--${name} expects a number`);
    return n;
  }
  if (type === "boolean") return raw === true || raw === "true" || raw === "1";
  if (type === "array") {
    const itemType = prop.items?.type;
    const parts = String(raw).split(",").map((s) => s.trim()).filter(Boolean);
    return itemType === "number" ? parts.map(Number) : parts;
  }
  if (type === "object" && typeof raw === "string" && raw.trim().startsWith("{")) return JSON.parse(raw);
  return raw;
}

function usage(message) {
  return Object.assign(new Error(message), { code: "USAGE" });
}

function parseAction(text) {
  const i = text.indexOf(":");
  if (i < 1) throw usage(`--action expects KIND:ARG, got "${text}"`);
  const kind = text.slice(0, i);
  const arg = text.slice(i + 1);
  if (kind === "click" || kind === "hover") return { type: kind, selector: arg };
  if (["play", "toggle", "reverse", "flip"].includes(kind)) return { type: kind, id: arg };
  if (kind === "flip-reverse") return { type: "flip", id: arg, reverse: true };
  if (kind === "wait") return { type: "wait", ms: Number(arg) };
  throw usage(`Unknown action kind "${kind}"`);
}

export function parseArgs(tool, argv) {
  const input = {};
  const flags = [];
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith("--")) throw usage(`Unexpected argument "${a}"`);
    let key = a.slice(2);
    let value;
    const eq = key.indexOf("=");
    if (eq !== -1) {
      value = key.slice(eq + 1);
      key = key.slice(0, eq);
    } else if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) {
      value = argv[++i];
    } else value = true;
    flags.push([key, value]);
  }
  const fromFile = flags.find(([k]) => k === "input");
  if (fromFile) {
    try {
      Object.assign(input, JSON.parse(fs.readFileSync(String(fromFile[1]), "utf8").replace(/^﻿/, "")));
    } catch (error) {
      throw usage(`--input could not be read as JSON: ${error.message}`);
    }
  }
  const props = tool.inputSchema.properties;
  for (const [key, value] of flags) {
    if (key === "input") continue;
    if (key === "param") {
      const s = String(value);
      const eq = s.indexOf("=");
      if (eq < 1) throw usage("--param expects NAME=VALUE");
      const name = s.slice(0, eq);
      const raw = s.slice(eq + 1);
      input.params = input.params ?? {};
      input.params[name] = raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw === "true" ? true : raw === "false" ? false : raw;
      continue;
    }
    if (key === "action") {
      input.actions = [...(input.actions ?? []), parseAction(String(value))];
      continue;
    }
    if (key === "viewport") {
      input.viewports = [...(input.viewports ?? []), String(value)];
      continue;
    }
    if (key === "story-intent" || key === "selector") {
      input.story = input.story ?? {};
      if (key === "story-intent") input.story.intent = String(value);
      else input.story.selectors = [...(input.story.selectors ?? []), String(value)];
      continue;
    }
    const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const prop = props[camel];
    if (!prop) throw usage(`Unknown option --${key} for ${tool.cli}`);
    const v = coerce(prop, value, key);
    if (prop.type === "array" && input[camel] && Array.isArray(v)) input[camel] = [...input[camel], ...v];
    else input[camel] = v;
  }
  return input;
}

function simpleOpts(argv) {
  const opts = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith("--")) throw usage(`Unexpected argument "${argv[i]}"`);
    const key = argv[i].slice(2);
    opts[key] = argv[i + 1] !== undefined && !argv[i + 1].startsWith("--") ? argv[++i] : true;
  }
  return opts;
}

async function doctor(argv) {
  const opts = simpleOpts(argv);
  const provenance = JSON.parse(fs.readFileSync(path.join(SKILL_ROOT, "PROVENANCE.json"), "utf8"));
  const bundle = fs.readFileSync(path.join(SKILL_ROOT, provenance.output.path));
  const digest = crypto.createHash("sha256").update(bundle).digest("hex");
  const browsers = findBrowsers(process.env.REVERIE_MOTION_BROWSER);
  const node = process.versions.node.split(".").map(Number);
  const report = {
    node: process.versions.node,
    nodeOk: node[0] > 20 || (node[0] === 20 && node[1] >= 10),
    vendor: { path: provenance.output.path, sha256: digest, matchesProvenance: digest === provenance.output.sha256, upstream: provenance.upstream },
    browsers,
  };
  if (opts.project) {
    const st = new Store(opts.project).ensure();
    report.workspace = { dir: st.rel(st.root) || ".reverie-motion", writable: true };
  }
  if (opts.launch) {
    const profileDir = path.join(new Store(opts.project ?? ".").root, "browser-profile");
    try {
      const b = await launchBrowser({ profileDir });
      report.launch = { ok: true, executable: b.executable, version: (await b.send("Browser.getVersion")).product, skipped: b.failedCandidates };
      await b.close();
    } catch (error) {
      report.launch = { ok: false, code: error.code, error: error.message };
    }
  }
  report.ok = report.nodeOk && report.vendor.matchesProvenance && browsers.length > 0 && (!report.launch || report.launch.ok);
  return report;
}

const INSTALL_SKIP = new Set([".reverie-motion", "node_modules", ".doctor-profile"]);

/** Copy the skill package; never deletes, refuses to touch changed files without --update. */
export function install(argv) {
  const opts = simpleOpts(argv);
  const scope = opts.scope ?? "workspace";
  let base;
  if (scope === "workspace") {
    if (!opts.project) throw usage("install --scope workspace needs --project DIR");
    base = path.join(path.resolve(String(opts.project)), ".agents", "skills");
  } else if (scope === "user") {
    base = path.join(os.homedir(), ".agents", "skills");
  } else throw usage("--scope must be workspace or user");
  const target = path.join(base, "reverie-motion");
  if (path.resolve(target) === path.resolve(SKILL_ROOT)) return { target, copied: 0, unchanged: 0, note: "already running from the install location" };
  const conflicts = [];
  const plan = [];
  const walk = (from, to) => {
    for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
      if (INSTALL_SKIP.has(entry.name)) continue;
      const src = path.join(from, entry.name);
      const dst = path.join(to, entry.name);
      if (entry.isDirectory()) walk(src, dst);
      else if (entry.isFile()) {
        const bytes = fs.readFileSync(src);
        const exists = fs.existsSync(dst);
        if (exists && Buffer.compare(fs.readFileSync(dst), bytes) === 0) plan.push({ dst, bytes, same: true });
        else {
          if (exists && !opts.update) conflicts.push(path.relative(target, dst));
          plan.push({ dst, bytes, same: false });
        }
      }
    }
  };
  walk(SKILL_ROOT, target);
  if (conflicts.length) {
    throw Object.assign(new Error(`${conflicts.length} installed file(s) differ; re-run with --update to overwrite them.`), { code: "INSTALL_CONFLICT", conflicts: conflicts.slice(0, 20) });
  }
  let copied = 0;
  for (const item of plan) {
    if (item.same) continue;
    fs.mkdirSync(path.dirname(item.dst), { recursive: true });
    fs.writeFileSync(item.dst, item.bytes);
    copied += 1;
  }
  return { scope, target, copied, unchanged: plan.length - copied, entry: path.join(target, "runtime", "bin", "reverie-motion.mjs") };
}

export async function main(argv = process.argv.slice(2)) {
  const [command, ...rest] = argv;
  const print = (obj) => process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
  if (!command || command === "help" || command === "--help" || command === "-h") {
    process.stdout.write(HELP + "\n");
    return 0;
  }
  if (command === "version" || command === "--version") {
    print({ ok: true, version: VERSION });
    return 0;
  }
  if (command === "schema") {
    print({ ok: true, tools: toolSchemas() });
    return 0;
  }
  if (command === "mcp") {
    const { serveMcp } = await import("./mcp.mjs");
    await serveMcp();
    return 0;
  }
  if (command === "install") {
    try {
      print({ ok: true, tool: "install", result: install(rest) });
      return 0;
    } catch (error) {
      print({ ok: false, tool: "install", error: { code: error.code ?? "INTERNAL", message: error.message, ...(error.conflicts ? { conflicts: error.conflicts } : {}) } });
      return error.code === "USAGE" ? 2 : 1;
    }
  }
  if (command === "doctor") {
    const result = await doctor(rest);
    print({ ok: result.ok, tool: "doctor", result });
    return result.ok ? 0 : 1;
  }
  const tool = TOOL_BY_CLI.get(command);
  if (!tool) {
    print({ ok: false, error: { code: "USAGE", message: `Unknown command "${command}". Run "help".` } });
    return 2;
  }
  let input;
  try {
    input = parseArgs(tool, rest);
  } catch (error) {
    print({ ok: false, tool: tool.name, error: { code: error.code ?? "USAGE", message: error.message } });
    return 2;
  }
  try {
    const result = await callTool(tool.name, input);
    print({ ok: true, tool: tool.name, result });
    return 0;
  } catch (error) {
    const details = {};
    for (const key of ["errors", "problems", "failures", "conflicts", "written"]) if (error[key]) details[key] = error[key];
    print({ ok: false, tool: tool.name, error: { code: error.code ?? "INTERNAL", message: error.message, ...details } });
    return error.code === "INPUT_INVALID" ? 2 : 1;
  }
}
