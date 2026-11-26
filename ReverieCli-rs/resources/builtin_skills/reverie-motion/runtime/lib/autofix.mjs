// Auto-fix: native fixers for RM findings + the vendored OpenMotion
// autoFixAccessibility pass, filtered through a Reverie policy so upstream
// remediations that break product UI motion are rejected (and reported).
import * as OM from "../vendor/openmotion.mjs";
import { normalizeSpec, toOpenMotion, normalizeEasing } from "./spec.mjs";
import { critique } from "./critique.mjs";
import { settleTimeMs } from "./spring.mjs";

/** UI-tuned thresholds handed to OpenMotion (its defaults target showreels). */
export const UPSTREAM_OPTIONS = { maxDisplacementPx: 300, maxRotationDeg: 180, minDurationMs: 120, maxLoopIterations: 3, staggerStepMs: 50 };

function applyNativeFix(spec, f, log) {
  const c = spec.components.find((x) => x.id === f.componentId);
  if (!c || !f.fix) return false;
  const fix = f.fix;
  const record = (field, before, after) => log.push({ source: "native", code: f.code, componentId: c.id, field, before, after, reason: f.message });
  switch (fix.code) {
    case "set-duration":
      if (c.durationMs === fix.value) return false;
      record("durationMs", c.durationMs, fix.value);
      c.durationMs = fix.value;
      if (c.easing.type === "spring") c.durationAuto = true;
      return true;
    case "set-easing": {
      const e = normalizeEasing(fix.value);
      record("easing", JSON.stringify(c.easing), JSON.stringify(e));
      c.easing = e;
      return true;
    }
    case "spring-response": {
      const e = normalizeEasing({ type: "spring", response: fix.response, dampingFraction: 0.8 });
      record("easing", JSON.stringify(c.easing), JSON.stringify(e));
      c.easing = e;
      c.durationMs = settleTimeMs(e);
      c.durationAuto = true;
      return true;
    }
    case "set-fill":
      record("fillMode", c.fillMode, fix.value);
      c.fillMode = fix.value;
      return true;
    case "set-reduced":
      record("reducedMotion", c.reducedMotion, fix.value);
      c.reducedMotion = fix.value;
      return true;
    case "stagger-each":
      record("stagger.eachMs", c.stagger.eachMs, fix.value);
      c.stagger.eachMs = fix.value;
      return true;
    case "set-first-scale":
      record("keyframes[0].scale", c.keyframes[0].properties.scale, fix.value);
      c.keyframes[0].properties.scale = fix.value;
      return true;
    case "clamp-property": {
      let changed = false;
      for (const k of c.keyframes) {
        const v = k.properties[fix.property];
        if (typeof v === "number" && v > fix.max) {
          k.properties[fix.property] = fix.max;
          changed = true;
        }
      }
      if (changed) record(fix.property, `>${fix.max}`, fix.max);
      return changed;
    }
    case "drop-property": {
      for (const k of c.keyframes) delete k.properties[fix.property];
      record(fix.property, "animated", "removed (keep it static in CSS)");
      return true;
    }
    case "swap-property": {
      // Only numeric px → transform swaps are safe to automate.
      const values = c.keyframes.map((k) => k.properties[fix.from]);
      if (!values.every((v) => v === undefined || typeof v === "number")) return false;
      const defined = values.filter((v) => v !== undefined);
      if (!defined.length) return false;
      const ref = Math.max(...defined);
      for (const k of c.keyframes) {
        const v = k.properties[fix.from];
        if (v === undefined) continue;
        delete k.properties[fix.from];
        k.properties[fix.to] = fix.to.startsWith("scale") ? (ref ? Number((v / ref).toFixed(4)) : 1) : (["bottom", "right"].includes(fix.from) ? -v : v);
      }
      if (fix.to.startsWith("scale") && !c.transformOrigin) c.transformOrigin = fix.from === "width" ? "left center" : "center top";
      record("keyframes", fix.from, fix.to);
      return true;
    }
    case "particles.count":
      record("particles.count", c.particles.count, fix.value);
      c.particles.count = fix.value;
      return true;
    case "particles.maxDpr":
      record("particles.maxDpr", c.particles.maxDpr, fix.value);
      c.particles.maxDpr = fix.value;
      return true;
    default:
      return false;
  }
}

/** Decide whether an upstream OpenMotion auto-fix action is acceptable for product UI. */
export function upstreamPolicy(action, component) {
  if (!component) return { accept: false, why: "component not in spec" };
  if (action.fix?.startsWith("Capped iterations") && component.reducedMotion !== "keep") {
    return { accept: false, why: "reduced-motion users already get a static alternative from the compiler; the loop stays for everyone else" };
  }
  if (action.field === "durationMs" && /^Raised duration/.test(action.fix ?? "") && Number(action.after) < Number(action.before)) {
    return { accept: false, why: "a duration floor must never shorten an animation" };
  }
  if (action.category === "vestibular" && action.field === "durationMs" && ["onClick", "onHover", "manual", "onState"].includes(component.trigger)) {
    return { accept: false, why: "short direct-manipulation feedback is intentional (100–200ms)" };
  }
  if (action.field === "fillMode") return { accept: false, why: "Reverie uses fillMode \"both\" (handled by RM010)" };
  if (action.componentId.includes("__")) return { accept: false, why: "stagger copies are timed by the stagger group, not individually" };
  if (component.easing.type === "spring" && (action.field === "easing" || action.field === "durationMs")) {
    return { accept: false, why: "spring timing comes from the physics (settle time), not from duration tiers or bezier families" };
  }
  if (component.iterationCount === "infinite" && action.field === "durationMs") {
    return { accept: false, why: "ambient loop periods are intentionally long" };
  }
  if (action.category === "cognitive" && action.field === "delayMs" && component.trigger !== "onLoad") {
    return { accept: false, why: "interactive motion is not simultaneous with load-time motion" };
  }
  return { accept: true };
}

function upstreamPass(spec, log, rejected) {
  const om = toOpenMotion(spec);
  if (!om.components.length) return false;
  const { fixedComponents, result } = OM.autoFixAccessibility(om.components, UPSTREAM_OPTIONS);
  const fixedById = new Map(fixedComponents.map((c) => [c.id, c]));
  let changed = false;
  for (const action of result.fixes) {
    const c = spec.components.find((x) => x.id === action.componentId);
    const verdict = upstreamPolicy(action, c ?? null);
    if (!verdict.accept) {
      rejected.push({ source: "openmotion:autofix", componentId: action.componentId, field: action.field, fix: action.fix, why: verdict.why });
      continue;
    }
    const fixed = fixedById.get(action.componentId);
    // OpenMotion reports keyframe edits as "keyframe.<prop>"; the whole track is copied.
    const field = action.field.startsWith("keyframe.") ? "keyframes" : action.field;
    if (!fixed || !(field in fixed) || (field === "keyframes" && c.kind !== "keyframes")) continue;
    c[field] = structuredClone(fixed[field]);
    log.push({ source: "openmotion:autofix", code: action.category, componentId: c.id, field: action.field, before: action.before, after: action.after, reason: action.issue });
    changed = true;
  }
  return changed;
}

/**
 * Iteratively fix until no fixable open findings remain (max `passes`).
 * Returns the new normalized spec plus a full before/after record.
 */
export function autofix(inputSpec, { passes = 3, upstream = true } = {}) {
  let spec = structuredClone(inputSpec);
  const before = critique(spec);
  const applied = [];
  const rejected = [];
  for (let pass = 0; pass < passes; pass += 1) {
    const report = critique(spec);
    let changed = false;
    for (const f of report.findings) {
      if (f.status === "open" && f.fix && f.severity !== "info") changed = applyNativeFix(spec, f, applied) || changed;
    }
    if (upstream && pass === 0) changed = upstreamPass(spec, applied, rejected) || changed;
    const renormalized = normalizeSpec({ ...spec, components: spec.components.map((c) => (c.durationAuto ? { ...c, durationMs: "auto" } : c)) });
    if (!renormalized.ok) throw new Error(`Auto-fix produced an invalid spec: ${JSON.stringify(renormalized.errors)}`);
    spec = renormalized.spec;
    if (!changed) break;
  }
  const after = critique(spec);
  spec.meta = { ...spec.meta, version: (inputSpec.meta?.version ?? 1) + 1, parent: inputSpec.meta?.revisionId ?? inputSpec.id, operation: "autofix" };
  return {
    schema: "reverie-motion.autofix.v1",
    spec,
    applied,
    rejected,
    before: { score: before.score, counts: before.counts },
    after: { score: after.score, counts: after.counts, passed: after.passed },
    remaining: after.findings.filter((f) => f.status === "open"),
  };
}
