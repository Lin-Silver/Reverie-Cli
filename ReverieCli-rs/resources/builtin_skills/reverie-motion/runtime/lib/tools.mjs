// Typed agent tools — one definition shared by the CLI (Reverie command_exec
// path) and the MCP stdio server. Every tool takes `project` (default ".") and
// confines reads/writes to it.
import fs from "node:fs";
import path from "node:path";
import { Store } from "./store.mjs";
import { inspectProject } from "./stack.mjs";
import { listTemplates, buildTemplate, composeSpecs } from "../templates/index.mjs";
import { normalizeSpec } from "./spec.mjs";
import { critique } from "./critique.mjs";
import { autofix } from "./autofix.mjs";
import { generateVariants, transferStyle, listArchetypes, storySpec, listNarratives, synthesize, motionDna, compareDna } from "./intelligence.mjs";
import { compileCss, compileModule, compileFramework, compilePreviewHtml, compileTypes } from "./compile.mjs";
import { runPreview, DEFAULT_VIEWPORTS } from "./preview.mjs";

export const VERSION = "0.1.0";

const project = { type: "string", description: "Target project directory (default: current directory). All files stay inside it." };
const specRef = { description: "Spec reference: id (latest revision), id@version, a .json path inside the project, or an inline spec object.", anyOf: [{ type: "string" }, { type: "object" }] };
const viewportsSchema = {
  type: "array",
  description: "Viewport names (desktop, mobile) or {name,width,height,deviceScaleFactor,mobile} objects. Default: desktop + mobile.",
  items: { anyOf: [{ type: "string", enum: ["desktop", "mobile"] }, { type: "object" }] },
};
const actionsSchema = {
  type: "array",
  description: "Interactions before sampling: {type:'click'|'hover', selector} for any page; {type:'play'|'reverse'|'toggle'|'flip', id, reverse?} for reverie previews; {type:'wait', ms}.",
  items: { type: "object" },
};

function store(input) {
  return new Store(input.project ?? ".");
}

function resolveViewports(list) {
  if (!list) return DEFAULT_VIEWPORTS;
  return list.map((v) => (typeof v === "string" ? DEFAULT_VIEWPORTS.find((d) => d.name === v) ?? (() => { throw Object.assign(new Error(`Unknown viewport "${v}"`), { code: "VIEWPORT_UNKNOWN" }); })() : v));
}

function specSummary(spec) {
  return {
    id: spec.id,
    revisionId: spec.meta?.revisionId,
    name: spec.name,
    purpose: spec.intent.purpose,
    components: spec.components.map((c) => ({
      id: c.id, kind: c.kind, selector: c.selector ?? c.flip?.from, trigger: c.trigger, durationMs: c.durationMs, delayMs: c.delayMs,
      easing: c.easing.type === "preset" ? c.easing.name : c.easing.type === "spring" ? `spring(k=${c.easing.stiffness}, c=${c.easing.damping})` : `cubic-bezier(${[...c.easing.p1, ...c.easing.p2].join(",")})`,
      iterationCount: c.iterationCount, reducedMotion: c.reducedMotion, ...(c.stagger ? { stagger: c.stagger } : {}),
      properties: [...new Set(c.keyframes.flatMap((k) => Object.keys(k.properties)))],
    })),
  };
}

function writePreview(st, spec, engine, manualClock = false) {
  st.ensure();
  const file = path.join(st.root, "previews", `${spec.meta?.revisionId ?? spec.id}-${engine}.html`.replace(/@/g, "_v"));
  fs.writeFileSync(file, compilePreviewHtml(spec, { engine, manualClock }));
  return file;
}

function compactPreview(report, st, dir) {
  return {
    passed: report.passed,
    score: report.score,
    browser: report.browser.version,
    target: report.target,
    evidenceDir: st.rel(dir),
    report: st.rel(path.join(dir, "preview-report.json")),
    findings: report.findings,
    viewports: report.viewports.map((v) => ({
      name: v.name,
      size: `${v.width}x${v.height}@${v.deviceScaleFactor}`,
      errors: v.errors,
      animations: v.timeline.count,
      timelineMs: v.timeline.endTime,
      perf: { fps: v.perf.fps, p95FrameMs: v.perf.p95Ms, droppedFrames: v.perf.droppedFrames, layoutsPerFrame: v.perf.layoutsPerFrame, layoutCount: v.perf.layoutCount, cls: v.perf.cumulativeLayoutShift, longTasks: v.perf.longTasks },
      sampling: v.sampling,
      frames: v.samples.map((s) => s.file),
      contactSheet: v.visual?.contactSheet,
      visual: v.visual ? { motionEnergy: v.visual.motionEnergy, firstToLast: v.visual.firstToLast, coverage: v.visual.frames.map((f) => f.coverage) } : null,
      reducedMotion: v.reducedMotion ? { mediaMatched: v.reducedMotion.mediaMatched, longRunning: v.reducedMotion.longRunning.length, screenshot: v.reducedMotion.file, particleCanvases: v.reducedMotion.particleCanvases } : null,
    })),
  };
}

async function preview(input) {
  const st = store(input).ensure();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  let spec = null;
  let htmlFile;
  let url;
  let label;
  if (input.url) {
    url = input.url;
    label = "url";
  } else if (input.file) {
    htmlFile = st.inside(input.file);
    if (!fs.existsSync(htmlFile)) throw Object.assign(new Error(`File not found: ${input.file}`), { code: "FILE_NOT_FOUND" });
    label = path.basename(htmlFile).replace(/[^\w.-]/g, "_");
  } else {
    spec = st.loadSpec(input.spec);
    htmlFile = writePreview(st, spec, input.engine ?? "waapi");
    label = (spec.meta?.revisionId ?? spec.id).replace(/@/g, "_v");
  }
  const dir = path.join(st.root, "evidence", `${label}-${input.engine ?? "waapi"}-${stamp}`);
  const report = await runPreview({
    htmlFile, url, spec, outDir: dir, allowRemote: input.allowRemote === true, serveRoot: st.project,
    viewports: resolveViewports(input.viewports), actions: input.actions ?? [],
    samples: input.samples, sampleCount: input.sampleCount, sampleEndMs: input.sampleEndMs,
    track: input.track, fineTrack: input.fineTrack, fineStepMs: input.fineStepMs,
    reducedMotion: input.reducedMotion, browser: input.browser, profileDir: path.join(st.root, "browser-profile"),
  });
  const out = compactPreview(report, st, dir);
  if (htmlFile && spec) out.previewHtml = st.rel(htmlFile);
  if (input.full) out.full = report;
  return out;
}

export const TOOLS = [
  {
    name: "motion_inspect_project",
    cli: "inspect",
    description: "Read-only scan of the target project: frameworks, existing motion libraries, styling, reduced-motion coverage, HTML entries, and the export targets that fit the stack. Run first.",
    inputSchema: { type: "object", properties: { project }, additionalProperties: false },
    handler: async (input) => inspectProject(store(input).project),
  },
  {
    name: "motion_templates",
    cli: "templates",
    description: "List motion templates (with parameters), style archetypes for style transfer, and narrative intents for storytelling.",
    inputSchema: { type: "object", properties: { project }, additionalProperties: false },
    handler: async () => ({ templates: listTemplates(), archetypes: listArchetypes(), narratives: listNarratives() }),
  },
  {
    name: "motion_design",
    cli: "design",
    description: "Create and save a validated MotionSpec revision from a template (+params), a composition of templates, a storytelling intent, or an authored spec. Returns the revision id, validation warnings and a static critique summary.",
    inputSchema: {
      type: "object",
      properties: {
        project,
        template: { type: "string", description: "Template id (see motion_templates)." },
        params: { type: "object", description: "Template parameters." },
        compose: { type: "array", description: "[{template, params}] composed into one spec.", items: { type: "object" } },
        story: { type: "object", description: "{intent, selectors[], totalDurationMs} — OpenMotion narrative planner bound to your selectors." },
        spec: specRef,
        id: { type: "string", description: "Override the spec id (letters, digits, - _)." },
        name: { type: "string" },
      },
      additionalProperties: false,
    },
    handler: async (input) => {
      const st = store(input);
      let raw;
      let operation = "template";
      let extra = {};
      if (input.compose) raw = composeSpecs(input.compose.map((x) => buildTemplate(x.template, x.params ?? {})));
      else if (input.template) raw = buildTemplate(input.template, input.params ?? {});
      else if (input.story) {
        const s = storySpec({ ...input.story, id: input.id ?? input.story.id ?? "story" });
        raw = s.spec;
        operation = "story-beat";
        extra = { story: s.sequence };
      } else if (input.spec) {
        raw = typeof input.spec === "object" ? input.spec : JSON.parse(fs.readFileSync(st.inside(input.spec), "utf8").replace(/^﻿/, ""));
        operation = "original";
      } else throw Object.assign(new Error("Provide template, compose, story or spec."), { code: "DESIGN_INPUT" });
      if (input.id) raw.id = input.id;
      if (input.name) raw.name = input.name;
      const { ok, spec, errors, warnings } = normalizeSpec(raw);
      if (!ok) throw Object.assign(new Error(`Spec is invalid: ${errors.map((e) => `${e.path}: ${e.message}`).join("; ")}`), { code: "SPEC_INVALID", errors });
      const saved = st.saveSpec(spec, { operation, params: raw.meta?.params ?? {} });
      const report = critique(saved.spec);
      return { revisionId: saved.revisionId, file: saved.file, latest: saved.latest, warnings, spec: specSummary(saved.spec), critique: { score: report.score, passed: report.passed, counts: report.counts, fixable: report.fixable }, ...extra, next: "motion_preview → motion_critique/motion_autofix → motion_export" };
    },
  },
  {
    name: "motion_variants",
    cli: "variants",
    description: "Generate alternative versions of a spec (OpenMotion variant strategies: easing, timing, choreography, intensity, direction; plus native spring-feel variants) and save each as its own spec with a critique score.",
    inputSchema: {
      type: "object",
      properties: {
        project, spec: specRef,
        count: { type: "integer", minimum: 1, maximum: 8, default: 3 },
        strategies: { type: "array", items: { type: "string", enum: ["easing", "timing", "choreography", "intensity", "direction", "palette"] } },
        seed: { type: "integer", default: 1 },
        springFeels: { type: "boolean", default: true },
      },
      required: ["spec"],
      additionalProperties: false,
    },
    handler: async (input) => {
      const st = store(input);
      const spec = st.loadSpec(input.spec);
      const variants = generateVariants(spec, { count: input.count ?? 3, strategies: input.strategies, seed: input.seed ?? 1, springFeels: input.springFeels !== false });
      return {
        parent: spec.meta?.revisionId ?? spec.id,
        variants: variants.map((v) => {
          const saved = st.saveSpec(v.spec, { operation: "variation", parents: [spec.meta?.revisionId ?? spec.id], params: { strategy: v.strategy } });
          return { revisionId: saved.revisionId, file: saved.file, strategy: v.strategy, source: v.source, description: v.description, divergence: v.divergence, critique: v.critique };
        }),
      };
    },
  },
  {
    name: "motion_style",
    cli: "style",
    description: "Style intelligence: transfer an archetype's or another spec's motion style (keeps brand colours and one-shot behaviour), synthesize a hybrid from several specs, extract Motion DNA, or compare two specs' DNA.",
    inputSchema: {
      type: "object",
      properties: {
        project,
        mode: { type: "string", enum: ["transfer", "synthesize", "dna", "compare", "archetypes"], default: "transfer" },
        spec: specRef,
        archetype: { type: "string", description: "minimalist | energetic | cinematic | playful | corporate | organic | mechanical | elegant" },
        from: { ...specRef, description: "Source spec whose style is transferred (transfer) or compared (compare)." },
        sources: { type: "array", description: "Specs whose DNA is blended (synthesize).", items: specRef },
        strength: { type: "number", minimum: 0, maximum: 1, default: 0.8 },
        keepColors: { type: "boolean", default: true },
        allowLoops: { type: "boolean", default: false },
        strategy: { type: "string", enum: ["blend", "dominant", "crossover", "mutation"], default: "blend" },
        seed: { type: "integer", default: 1 },
      },
      additionalProperties: false,
    },
    handler: async (input) => {
      const st = store(input);
      const mode = input.mode ?? "transfer";
      if (mode === "archetypes") return { archetypes: listArchetypes() };
      const spec = st.loadSpec(input.spec);
      if (mode === "dna") return { revisionId: spec.meta?.revisionId, dna: motionDna(spec) };
      if (mode === "compare") return { a: spec.meta?.revisionId, b: input.from, comparison: compareDna(spec, st.loadSpec(input.from)) };
      if (mode === "synthesize") {
        const sources = (input.sources ?? []).map((s) => st.loadSpec(s));
        const r = synthesize(sources, spec, { strategy: input.strategy, seed: input.seed ?? 1 });
        const saved = st.saveSpec(r.spec, { operation: "synthesis", parents: [spec.meta?.revisionId ?? spec.id, ...sources.map((s) => s.meta?.revisionId ?? s.id)], params: { strategy: input.strategy ?? "blend" } });
        return { revisionId: saved.revisionId, file: saved.file, summary: r.summary, attributions: r.attributions, critique: r.critique, spec: specSummary(saved.spec) };
      }
      const from = input.from ? st.loadSpec(input.from) : undefined;
      const r = transferStyle(spec, { archetype: input.archetype, from, strength: input.strength ?? 0.8, keepColors: input.keepColors !== false, allowLoops: input.allowLoops === true });
      const parents = [spec.meta?.revisionId ?? spec.id, ...(from ? [from.meta?.revisionId ?? from.id] : [])];
      const saved = st.saveSpec(r.spec, { operation: "style-transfer", parents, params: { source: r.source, strength: input.strength ?? 0.8 } });
      return { revisionId: saved.revisionId, file: saved.file, source: r.source, fieldsTransferred: r.fieldsTransferred, similarityToSource: r.similarityToSource, description: r.description, critique: r.critique, spec: specSummary(saved.spec) };
    },
  },
  {
    name: "motion_critique",
    cli: "critique",
    description: "Static critique of a spec: native UI-motion rules (RM codes with machine fixes) + OpenMotion critique, accessibility, performance and genome analysers. Score 0–100; passed = no critical and score ≥ 70.",
    inputSchema: { type: "object", properties: { project, spec: specRef }, required: ["spec"], additionalProperties: false },
    handler: async (input) => critique(store(input).loadSpec(input.spec)),
  },
  {
    name: "motion_autofix",
    cli: "autofix",
    description: "Apply machine fixes for open critique findings (native fixers + OpenMotion auto-fix filtered by a UI policy), save a new revision and report applied/rejected changes with before/after scores.",
    inputSchema: { type: "object", properties: { project, spec: specRef, passes: { type: "integer", minimum: 1, maximum: 5, default: 3 } }, required: ["spec"], additionalProperties: false },
    handler: async (input) => {
      const st = store(input);
      const spec = st.loadSpec(input.spec);
      const r = autofix(spec, { passes: input.passes ?? 3 });
      if (!r.applied.length) return { changed: false, revisionId: spec.meta?.revisionId, before: r.before, after: r.after, rejected: r.rejected, remaining: r.remaining };
      const saved = st.saveSpec(r.spec, { operation: "autofix", parents: [spec.meta?.revisionId ?? spec.id] });
      return { changed: true, revisionId: saved.revisionId, file: saved.file, applied: r.applied, rejected: r.rejected, before: r.before, after: r.after, remaining: r.remaining };
    },
  },
  {
    name: "motion_preview",
    cli: "preview",
    description: "Run motion in a real headless Chromium: runtime errors, frame pacing, layout/style work, layout shift, deterministic keyframe screenshots + element states, visual motion metrics, contact sheet, and a prefers-reduced-motion pass. Works on a spec, a local HTML file, or a localhost URL.",
    inputSchema: {
      type: "object",
      properties: {
        project, spec: specRef,
        file: { type: "string", description: "Local HTML file inside the project." },
        url: { type: "string", description: "Local URL (localhost/127.0.0.1/*.localhost/*.test); remote needs allowRemote and user consent." },
        allowRemote: { type: "boolean", default: false },
        engine: { type: "string", enum: ["waapi", "css"], default: "waapi" },
        viewports: viewportsSchema,
        actions: actionsSchema,
        samples: { type: "array", items: { type: "number" }, description: "Explicit sample times in ms." },
        sampleCount: { type: "integer", minimum: 2, maximum: 24, default: 8 },
        sampleEndMs: { type: "number" },
        track: { type: "array", items: { type: "string" }, description: "Selectors whose computed state is recorded per sample." },
        fineTrack: { type: "array", items: { type: "string" }, description: "Selectors sampled densely (no screenshots) to verify curves." },
        fineStepMs: { type: "number", default: 16 },
        reducedMotion: { type: "boolean", default: true, description: "Run the prefers-reduced-motion pass." },
        browser: { type: "string", description: "Browser executable override." },
        full: { type: "boolean", default: false, description: "Include the full report inline." },
      },
      additionalProperties: false,
    },
    handler: preview,
  },
  {
    name: "motion_export",
    cli: "export",
    description: "Write native, dependency-free code for the target project: css, waapi (ES module), react/vue/svelte wrappers, dts typings, standalone html, and optional scaffold markup. Refuses to overwrite unless overwrite=true.",
    inputSchema: {
      type: "object",
      properties: {
        project, spec: specRef,
        targets: { type: "array", items: { type: "string", enum: ["css", "waapi", "react", "vue", "svelte", "dts", "html", "scaffold"] }, default: ["css", "waapi"] },
        outDir: { type: "string", default: "src/motion", description: "Directory inside the project." },
        fileBase: { type: "string", description: "Base file name (default: spec id)." },
        includeStyles: { type: "boolean", default: false, description: "Also emit component static styles in the CSS." },
        overwrite: { type: "boolean", default: false },
      },
      required: ["spec"],
      additionalProperties: false,
    },
    handler: async (input) => {
      const st = store(input);
      const spec = st.loadSpec(input.spec);
      const outDir = st.inside(input.outDir ?? "src/motion");
      fs.mkdirSync(outDir, { recursive: true });
      const base = (input.fileBase ?? spec.id).replace(/[^\w.-]/g, "-");
      const targets = input.targets ?? ["css", "waapi"];
      const moduleName = `${base}.motion.js`;
      const files = {};
      for (const t of targets) {
        if (t === "css") files[`${base}.motion.css`] = compileCss(spec, { includeStyles: input.includeStyles === true });
        else if (t === "waapi") files[moduleName] = compileModule(spec);
        else if (t === "dts") files[`${base}.motion.d.ts`] = compileTypes(spec);
        else if (["react", "vue", "svelte"].includes(t)) {
          if (!targets.includes("waapi")) files[moduleName] = compileModule(spec);
          files[`${base}.${t}.js`] = compileFramework(spec, t, `./${moduleName}`);
        } else if (t === "html") files[`${base}.preview.html`] = compilePreviewHtml(spec, { engine: "waapi" });
        else if (t === "scaffold") files[`${base}.scaffold.html`] = `<!-- reverie-motion scaffold for ${spec.id}: markup + styles the spec selectors expect -->\n<style>\n${spec.stage.css}\n</style>\n${spec.stage.html}\n`;
      }
      const written = [];
      const conflicts = [];
      for (const [name, content] of Object.entries(files)) {
        const full = path.join(outDir, name);
        if (fs.existsSync(full) && !input.overwrite && fs.readFileSync(full, "utf8") !== content) {
          conflicts.push(st.rel(full));
          continue;
        }
        fs.writeFileSync(full, content);
        written.push({ file: st.rel(full), bytes: Buffer.byteLength(content) });
      }
      if (conflicts.length) {
        throw Object.assign(new Error(`Refusing to overwrite changed files: ${conflicts.join(", ")}. Re-run with overwrite=true after reviewing them.`), { code: "EXPORT_CONFLICT", written, conflicts });
      }
      return {
        revisionId: spec.meta?.revisionId,
        written,
        usage: {
          css: `Link ${base}.motion.css. onLoad components animate immediately; click/manual components play when the class "rm-${spec.id}-<componentId>-play" is added; staggered items read --rm-i (set by the module or inline style="--rm-i:N").`,
          waapi: `import { mount } from "./${moduleName}"; const motion = mount(rootElement); // motion.play(id), motion.toggle(id), motion.flip(id), motion.destroy()`,
        },
        note: "Run motion_preview on the integrated page (file or local dev URL) to verify the real integration.",
      };
    },
  },
  {
    name: "motion_verify",
    cli: "verify",
    description: "Closed loop: critique → auto-fix (new revision when needed) → real-browser preview, repeated up to maxRounds until both static and runtime checks pass. Returns every round and the final verdict.",
    inputSchema: {
      type: "object",
      properties: {
        project, spec: specRef,
        engine: { type: "string", enum: ["waapi", "css"], default: "waapi" },
        viewports: viewportsSchema,
        actions: actionsSchema,
        autofix: { type: "boolean", default: true },
        maxRounds: { type: "integer", minimum: 1, maximum: 4, default: 2 },
      },
      required: ["spec"],
      additionalProperties: false,
    },
    handler: async (input) => {
      const st = store(input);
      let spec = st.loadSpec(input.spec);
      const rounds = [];
      for (let round = 1; round <= (input.maxRounds ?? 2); round += 1) {
        const stat = critique(spec);
        let fixed = null;
        if (input.autofix !== false && stat.findings.some((f) => f.status === "open" && f.fix && f.severity !== "info")) {
          const r = autofix(spec);
          if (r.applied.length) {
            const saved = st.saveSpec(r.spec, { operation: "autofix", parents: [spec.meta?.revisionId ?? spec.id] });
            spec = saved.spec;
            fixed = { revisionId: saved.revisionId, applied: r.applied.length, rejected: r.rejected.length, before: r.before.score, after: r.after.score };
          }
        }
        const after = fixed ? critique(spec) : stat;
        const runtime = await preview({ project: st.project, spec: spec.meta?.revisionId ?? spec, engine: input.engine, viewports: input.viewports, actions: input.actions });
        rounds.push({ round, revisionId: spec.meta?.revisionId, critique: { score: after.score, passed: after.passed, counts: after.counts }, autofix: fixed, preview: { passed: runtime.passed, score: runtime.score, findings: runtime.findings, evidenceDir: runtime.evidenceDir, contactSheets: runtime.viewports.map((v) => v.contactSheet) } });
        if (after.passed && runtime.passed) break;
        if (!fixed) break; // nothing more the machine can change; hand findings to the agent
      }
      const last = rounds[rounds.length - 1];
      return { passed: last.critique.passed && last.preview.passed, revisionId: last.revisionId, rounds };
    },
  },
  {
    name: "motion_lineage",
    cli: "lineage",
    description: "Revision history of all specs in the project (OpenMotion lineage engine, persisted): operations, parents, generations and an optional focus report for one revision.",
    inputSchema: { type: "object", properties: { project, spec: { type: "string", description: "Optional revision id (id@version) to focus on." } }, additionalProperties: false },
    handler: async (input) => store(input).lineageReport(input.spec),
  },
];

export const TOOL_BY_NAME = new Map(TOOLS.map((t) => [t.name, t]));
export const TOOL_BY_CLI = new Map(TOOLS.map((t) => [t.cli, t]));

/** Minimal JSON-schema check of the top-level shape (types, required, enums, unknown keys). */
export function checkInput(tool, input) {
  const schema = tool.inputSchema;
  const problems = [];
  if (!input || typeof input !== "object" || Array.isArray(input)) return ["input must be an object"];
  for (const key of schema.required ?? []) if (input[key] === undefined) problems.push(`missing required "${key}"`);
  for (const [key, value] of Object.entries(input)) {
    const prop = schema.properties[key];
    if (!prop) {
      if (schema.additionalProperties === false) problems.push(`unknown parameter "${key}"`);
      continue;
    }
    const types = prop.anyOf ? prop.anyOf.map((x) => x.type) : [prop.type];
    const actual = Array.isArray(value) ? "array" : Number.isInteger(value) ? "integer" : typeof value;
    const ok = types.some((t) => t === actual || (t === "number" && actual === "integer"));
    if (!ok) problems.push(`"${key}" must be ${types.join(" or ")}`);
    if (prop.enum && !prop.enum.includes(value)) problems.push(`"${key}" must be one of ${prop.enum.join(", ")}`);
    if (prop.type === "array" && prop.items?.enum && Array.isArray(value)) {
      for (const v of value) if (!prop.items.enum.includes(v)) problems.push(`"${key}" item "${v}" must be one of ${prop.items.enum.join(", ")}`);
    }
    if (typeof value === "number" && prop.minimum !== undefined && value < prop.minimum) problems.push(`"${key}" must be >= ${prop.minimum}`);
    if (typeof value === "number" && prop.maximum !== undefined && value > prop.maximum) problems.push(`"${key}" must be <= ${prop.maximum}`);
  }
  return problems;
}

export async function callTool(name, input = {}) {
  const tool = TOOL_BY_NAME.get(name);
  if (!tool) throw Object.assign(new Error(`Unknown tool "${name}".`), { code: "TOOL_UNKNOWN" });
  const problems = checkInput(tool, input);
  if (problems.length) throw Object.assign(new Error(`Invalid input for ${name}: ${problems.join("; ")}`), { code: "INPUT_INVALID", problems });
  return tool.handler(input);
}

export function toolSchemas() {
  return TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema }));
}
