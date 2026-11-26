// Project-local workspace (.reverie-motion/) for specs, previews, evidence and
// lineage. All writes are confined to the project directory; nothing is deleted.
import fs from "node:fs";
import path from "node:path";
import * as OM from "../vendor/openmotion.mjs";
import { normalizeSpec } from "./spec.mjs";

export const WORKDIR = ".reverie-motion";

export class Store {
  constructor(project) {
    this.project = path.resolve(project ?? ".");
    if (!fs.existsSync(this.project) || !fs.statSync(this.project).isDirectory()) {
      throw Object.assign(new Error(`Project directory not found: ${this.project}`), { code: "PROJECT_NOT_FOUND" });
    }
    this.root = path.join(this.project, WORKDIR);
  }

  /** Resolve a user path and refuse anything outside the project. */
  inside(p) {
    const full = path.resolve(this.project, p);
    const rel = path.relative(this.project, full);
    if (rel.startsWith("..") || path.isAbsolute(rel)) {
      throw Object.assign(new Error(`Path escapes the project directory: ${p}`), { code: "PATH_OUTSIDE_PROJECT" });
    }
    return full;
  }

  ensure() {
    for (const dir of ["specs", "previews", "evidence"]) fs.mkdirSync(path.join(this.root, dir), { recursive: true });
    const ignore = path.join(this.root, ".gitignore");
    if (!fs.existsSync(ignore)) fs.writeFileSync(ignore, "# reverie-motion working data\nbrowser-profile/\nevidence/\npreviews/\n");
    return this;
  }

  rel(p) {
    return path.relative(this.project, p).replace(/\\/g, "/");
  }

  /** Persist a normalized spec as a new revision and as the latest copy. */
  saveSpec(spec, { operation = "original", parents = [], params = {} } = {}) {
    this.ensure();
    const existing = this.revisions(spec.id);
    const version = existing.length ? Math.max(...existing) + 1 : 1;
    const revisionId = `${spec.id}@${version}`;
    const saved = { ...spec, meta: { ...spec.meta, version, revisionId } };
    const file = path.join(this.root, "specs", `${spec.id}@${version}.json`);
    fs.writeFileSync(file, JSON.stringify(saved, null, 2) + "\n");
    fs.writeFileSync(path.join(this.root, "specs", `${spec.id}.json`), JSON.stringify(saved, null, 2) + "\n");
    const record = this.recordLineage(revisionId, saved.name, operation, parents, params);
    return { spec: saved, file: this.rel(file), latest: this.rel(path.join(this.root, "specs", `${spec.id}.json`)), revisionId, lineage: record };
  }

  revisions(id) {
    const dir = path.join(this.root, "specs");
    if (!fs.existsSync(dir)) return [];
    const re = new RegExp(`^${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}@(\\d+)\\.json$`);
    return fs.readdirSync(dir).map((f) => f.match(re)).filter(Boolean).map((m) => Number(m[1]));
  }

  /**
   * Load a spec by file path (inside the project), by id (latest), or by "id@version".
   * Always re-validated; invalid specs raise SPEC_INVALID with the error list.
   */
  loadSpec(ref) {
    if (!ref) throw Object.assign(new Error("A spec reference (path, id or id@version) is required."), { code: "SPEC_REQUIRED" });
    if (typeof ref === "object") return this.validate(ref, "<inline>");
    let file;
    if (/\.json$/i.test(ref)) file = this.inside(ref);
    else file = path.join(this.root, "specs", `${ref}.json`);
    if (!fs.existsSync(file)) throw Object.assign(new Error(`Spec not found: ${ref}`), { code: "SPEC_NOT_FOUND" });
    let data;
    try {
      data = JSON.parse(fs.readFileSync(file, "utf8").replace(/^﻿/, ""));
    } catch (error) {
      throw Object.assign(new Error(`Spec is not valid JSON (${ref}): ${error.message}`), { code: "SPEC_JSON" });
    }
    return this.validate(data, ref);
  }

  validate(data, label) {
    const { ok, spec, errors, warnings } = normalizeSpec(data);
    if (!ok) throw Object.assign(new Error(`Spec ${label} is invalid: ${errors.map((e) => `${e.path}: ${e.message}`).join("; ")}`), { code: "SPEC_INVALID", errors, warnings });
    spec.__warnings = warnings;
    return spec;
  }

  // ---- lineage (OpenMotion motionLineage engine, persisted as JSON) ----
  lineageFile() {
    return path.join(this.root, "lineage.json");
  }

  readLineage() {
    try {
      return JSON.parse(fs.readFileSync(this.lineageFile(), "utf8"));
    } catch {
      return { schema: "reverie-motion.lineage.v1", records: [] };
    }
  }

  /** Replay stored records into the in-memory upstream store so its tree/ancestor logic applies. */
  hydrate() {
    const data = this.readLineage();
    OM.clearProjectLineage(this.project);
    for (const r of data.records) OM.recordLineage(this.project, r.componentId, r.componentName, r.operation, r.parentIds, r.params, r.label);
    return data;
  }

  recordLineage(revisionId, name, operation, parentIds = [], params = {}) {
    const data = this.hydrate();
    const allowed = ["original", "variation", "style-transfer", "story-beat", "template", "duplicate", "import"];
    // OpenMotion's lineage enum has no autofix/synthesis; those are stored as
    // "import" with the real operation kept in the label.
    const op = allowed.includes(operation) ? operation : "import";
    const label = operation;
    const rec = OM.recordLineage(this.project, revisionId, name, op, parentIds, params, label);
    const stored = { componentId: revisionId, componentName: name, operation: op, label, parentIds, params, generation: rec.generation, createdAt: new Date().toISOString() };
    data.records.push(stored);
    fs.writeFileSync(this.lineageFile(), JSON.stringify(data, null, 2) + "\n");
    return stored;
  }

  lineageReport(revisionId) {
    const data = this.hydrate();
    const summary = OM.getProjectLineageSummary(this.project);
    const tree = OM.getLineageTree(this.project);
    const simplify = (n) => ({ id: n.record.componentId, operation: n.record.operation, label: n.record.label, generation: n.record.generation, children: n.children.map(simplify) });
    return {
      records: data.records.length,
      summary: { totalOperations: summary.totalOperations, maxGeneration: summary.maxGeneration, operationBreakdown: summary.operationBreakdown, rootCount: summary.rootCount },
      tree: tree.map(simplify),
      focus: revisionId ? OM.generateLineageReport(this.project, revisionId) : null,
    };
  }
}
