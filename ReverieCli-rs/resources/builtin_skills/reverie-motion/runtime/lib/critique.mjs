// Static motion critique = vendored OpenMotion analysers (critique, accessibility,
// performance, genome) + native Reverie rules tuned for product UI motion.
// Findings are normalised to {code, source, severity, dimension, componentId, message, fix?, status}.
import * as OM from "../vendor/openmotion.mjs";
import {
  toOpenMotion, LAYOUT_PROPS, firstProperties, staggerOrder,
} from "./spec.mjs";
import { settleTimeMs, describeSpring } from "./spring.mjs";

const SEVERITY_PENALTY = { critical: 20, warning: 7, info: 1 };

const MOVEMENT = ["translateX", "translateY", "scale", "scaleX", "scaleY", "rotate", "rotateX", "rotateY", "rotateZ"];
const animatedProps = (c) => new Set(c.keyframes.flatMap((k) => Object.keys(k.properties)));
const num = (v) => (typeof v === "number" ? v : Number.parseFloat(String(v)));

function maxAbs(c, props) {
  let m = 0;
  for (const k of c.keyframes) for (const p of props) if (k.properties[p] !== undefined) {
    const v = num(k.properties[p]);
    if (Number.isFinite(v)) m = Math.max(m, p.startsWith("scale") ? Math.abs(1 - v) * 100 : Math.abs(v));
  }
  return m;
}

function easingName(e) {
  return e.type === "preset" ? e.name : e.type;
}

/** Native Reverie rules (RM0xx). Each finding may carry a machine-applicable fix. */
export function nativeRules(spec) {
  const out = [];
  const purpose = spec.intent?.purpose ?? "entrance";
  const add = (code, severity, dimension, c, message, fix) =>
    out.push({ code, source: "native", severity, dimension, componentId: c?.id ?? null, message, ...(fix ? { fix } : {}), status: "open" });

  for (const c of spec.components) {
    if (c.kind === "particles") {
      if (c.particles.count > 150) add("RM013", "warning", "performance", c, `${c.particles.count} particles exceeds the 150-particle phone budget.`, { code: "particles.count", value: 120 });
      if (c.particles.maxDpr > 2) add("RM013", "info", "performance", c, `maxDpr ${c.particles.maxDpr} multiplies fill cost; 2 is enough.`, { code: "particles.maxDpr", value: 2 });
      continue;
    }
    const props = c.kind === "keyframes" ? animatedProps(c) : new Set(["transform"]);
    const infinite = c.iterationCount === "infinite";
    const interactive = ["onClick", "onHover", "manual", "onState"].includes(c.trigger);
    const role = c.trigger === "onHover" || (interactive && !c.toggle && c.kind === "keyframes" && purpose === "feedback") ? "feedback" : infinite ? "ambient" : purpose;

    // RM001 layout-triggering properties
    for (const p of props) if (LAYOUT_PROPS.has(p)) {
      const swap = { width: "scaleX", height: "scaleY", top: "translateY", bottom: "translateY", left: "translateX", right: "translateX" }[p];
      add("RM001", "warning", "performance", c, `"${p}" triggers layout on every frame.`, swap ? { code: "swap-property", from: p, to: swap } : undefined);
    }
    // RM002 expensive paint
    if (props.has("backdropBlur")) add("RM002", "warning", "performance", c, "Animating backdrop-filter re-blurs everything behind the element every frame; keep the blur static and animate opacity/transform.", { code: "drop-property", property: "backdropBlur" });
    if (props.has("blur") && maxAbs(c, ["blur"]) > 12) add("RM002", "warning", "performance", c, `blur up to ${maxAbs(c, ["blur"])}px is costly to paint; ≤ 10px reads the same in motion.`, { code: "clamp-property", property: "blur", max: 10 });
    for (const p of ["boxShadow", "backgroundColor", "borderRadius", "color"]) {
      if (props.has(p) && !infinite) add("RM002", "info", "performance", c, `"${p}" repaints each frame; fine for small elements, avoid on large surfaces.`);
    }
    if (props.has("borderRadius") && infinite) add("RM002", "info", "performance", c, "Infinite border-radius morph repaints continuously; keep the element small.");

    // RM004 spring truncation / dead tail
    if (c.easing.type === "spring") {
      const settle = settleTimeMs(c.easing);
      if (c.durationMs < settle * 0.9) add("RM004", "warning", "aesthetic", c, `Spring needs ${settle}ms to settle but duration is ${c.durationMs}ms — it will jump at the end.`, { code: "set-duration", value: settle });
      else if (c.durationMs > settle * 1.6) add("RM004", "info", "aesthetic", c, `Spring settles at ${settle}ms; the remaining ${c.durationMs - settle}ms is dead time.`, { code: "set-duration", value: settle });
      const d = describeSpring(c.easing);
      if (role === "feedback" && d.settleMs > 600) add("RM003", "warning", "aesthetic", c, `Feedback spring settles in ${d.settleMs}ms; raise stiffness (response ≤ 0.3s) so input feels instant.`, { code: "spring-response", response: 0.3 });
      if ((c.kind === "flip" || props.has("width") || maxAbs(c, ["translateX", "translateY"]) > 120) && d.dampingRatio < 0.7) add("RM003", "info", "aesthetic", c, `Large surfaces with damping ratio ${d.dampingRatio} wobble visibly; ≥ 0.8 keeps big moves calm.`);
    } else {
      // RM003 duration vs role
      const d = c.durationMs;
      if (role === "feedback" && d > 300) add("RM003", "warning", "aesthetic", c, `${d}ms is sluggish for direct feedback (aim 100–250ms).`, { code: "set-duration", value: 200 });
      if ((role === "entrance" || role === "storytelling") && d > 1000 && !infinite) add("RM003", "warning", "aesthetic", c, `${d}ms entrance delays content; aim 250–700ms.`, { code: "set-duration", value: 600 });
      if (role === "entrance" && d < 120) add("RM003", "info", "aesthetic", c, `${d}ms entrance may read as a flicker.`);
      if (role === "exit" && d > 300) add("RM003", "warning", "aesthetic", c, `Exits should be quicker than entrances (aim 150–250ms); got ${d}ms.`, { code: "set-duration", value: 200 });
      if (role === "transition" && d > 700) add("RM003", "warning", "aesthetic", c, `${d}ms transition holds the user up; aim 300–600ms.`, { code: "set-duration", value: 500 });
      if (infinite && d < 1000 && maxAbs(c, ["translateX", "translateY"]) > 20) add("RM014", "warning", "accessibility", c, `Fast infinite loop (${d}ms) with ${maxAbs(c, ["translateX", "translateY"])}px travel is distracting and vestibular-unfriendly.`, { code: "set-duration", value: 4000 });
    }

    // RM005 ease-in on things that must respond / arrive
    const name = easingName(c.easing);
    if (/^ease-in(-quad|-cubic)?$/.test(name) && role !== "exit" && role !== "ambient") {
      add("RM005", "warning", "aesthetic", c, `${name} starts slowly, which reads as lag for ${role} motion; use an ease-out curve.`, { code: "set-easing", value: role === "feedback" ? "ease-out" : "ease-out-quart" });
    }
    // RM006 linear movement
    if (name === "linear" && !infinite && [...props].some((p) => MOVEMENT.includes(p))) {
      add("RM006", "warning", "aesthetic", c, "Linear easing on movement looks mechanical; use ease-out-quart or a spring.", { code: "set-easing", value: "ease-out-quart" });
    }
    // RM007 stagger cascade length
    if (c.stagger && c.stagger.eachMs > 0) {
      const total = (Math.max(...staggerOrder(c.stagger.count, c.stagger.from))) * c.stagger.eachMs;
      if (total > 600) add("RM007", "warning", "aesthetic", c, `Stagger cascade takes ${total}ms before the last item starts; keep it under ~500ms.`, { code: "stagger-each", value: Math.max(20, Math.floor(500 / Math.max(1, Math.max(...staggerOrder(c.stagger.count, c.stagger.from))))) });
      else if (c.stagger.eachMs > 100) add("RM007", "info", "aesthetic", c, `${c.stagger.eachMs}ms per item feels slow for lists (30–60ms typical).`);
    }
    // RM009 scale from (near) zero
    if (c.kind === "keyframes" && !infinite) {
      const s = num(firstProperties(c).scale);
      if (Number.isFinite(s) && s < 0.3) add("RM009", "warning", "aesthetic", c, `Scaling from ${s} looks like a pop from nowhere; start at 0.8–0.95 with opacity.`, { code: "set-first-scale", value: 0.85 });
      else if (Number.isFinite(s) && s < 0.6 && role === "entrance") add("RM009", "info", "aesthetic", c, `Start scale ${s} is dramatic for UI; 0.85–0.95 is calmer.`);
    }
    // RM010 flash of content before a delayed entrance
    if (c.kind === "keyframes" && (c.delayMs > 0 || c.stagger) && ["none", "forwards"].includes(c.fillMode)) {
      const first = firstProperties(c);
      if (num(first.opacity) === 0 || first.clipPath || first.strokeDashoffset !== undefined) {
        add("RM010", "critical", "aesthetic", c, `Delayed entrance with fillMode "${c.fillMode}" shows the final state during the delay, then jumps to the first frame.`, { code: "set-fill", value: "both" });
      }
    }
    // RM012 keeping big motion under reduced-motion
    if (c.reducedMotion === "keep" && (maxAbs(c, ["translateX", "translateY"]) > 40 || maxAbs(c, ["rotate", "rotateX", "rotateY", "rotateZ"]) > 45 || c.kind === "flip")) {
      add("RM012", "warning", "accessibility", c, "Large movement is kept under prefers-reduced-motion; use \"fade\" or \"final-state\".", { code: "set-reduced", value: "fade" });
    }
    // RM015 interruptibility of toggles
    if (c.toggle && c.easing.type !== "spring" && c.durationMs > 500) add("RM015", "info", "aesthetic", c, "Long eased toggles feel stuck when interrupted; a spring keeps reversals continuous.");
    // RM016 origin-aware scale from a trigger
    if (c.triggerSelector && (props.has("scale") || props.has("scaleX") || props.has("scaleY")) && !c.transformOrigin) {
      add("RM016", "info", "aesthetic", c, "Scale from where the trigger is: set transformOrigin toward the trigger.");
    }
  }
  return out;
}

const SOURCE_DIMENSION = { vestibular: "accessibility", seizure: "accessibility", "reduced-motion": "accessibility", cognitive: "consistency" };

/**
 * Full static critique. Upstream findings that the Reverie compiler already
 * mitigates (reduced-motion alternatives are always generated) are kept for
 * transparency with status "mitigated" and excluded from the score.
 */
export function critique(spec) {
  const om = toOpenMotion(spec);
  const findings = nativeRules(spec);
  const strengths = [];
  const upstream = { critique: null, accessibility: null, performance: null, genome: null };
  if (om.components.length) {
    const cr = OM.critiqueMotion(om);
    upstream.critique = { overallScore: cr.overallScore, dimensions: Object.fromEntries(Object.entries(cr.dimensions).map(([k, v]) => [k, v.score])) };
    for (const f of cr.findings) {
      if (f.severity === "strength") { strengths.push(f.message); continue; }
      findings.push({ code: "OM-CRITIQUE", source: "openmotion:critique", severity: f.severity, dimension: f.dimension, componentId: baseId(f.componentId), message: f.message, status: mitigated(spec, f) ? "mitigated" : "open" });
    }
    const a11y = OM.checkAccessibility(om.components);
    upstream.accessibility = { score: a11y.score, stats: a11y.stats };
    for (const i of a11y.issues) {
      findings.push({ code: `OM-A11Y-${i.category}`, source: "openmotion:accessibility", severity: i.severity, dimension: SOURCE_DIMENSION[i.category] ?? "accessibility", componentId: baseId(i.componentId), message: i.message, remediation: i.remediation, status: mitigated(spec, i) ? "mitigated" : "open" });
    }
    const perf = OM.checkPerformance(om.components);
    upstream.performance = { estimatedFrameMs: perf.stats.estimatedFrameMs, withinBudget: perf.stats.withinBudget, layoutTriggerCount: perf.stats.layoutTriggerCount };
    for (const i of perf.issues) {
      findings.push({ code: `OM-PERF-${i.category}`, source: "openmotion:performance", severity: i.severity, dimension: "performance", componentId: baseId(i.componentId), message: i.message, remediation: i.suggestion, status: "open" });
    }
    if (om.components.length >= 2) {
      const g = OM.analyzeGenome(om);
      upstream.genome = { diversityScore: g.diversityScore, familyCount: g.familyCount, isMonoculture: g.isMonoculture, monocultureAxes: g.monocultureAxes };
    }
  }
  const deduped = dedupe(findings);
  const open = deduped.filter((f) => f.status === "open");
  const score = Math.max(0, 100 - open.reduce((s, f) => s + (SEVERITY_PENALTY[f.severity] ?? 0), 0));
  return {
    schema: "reverie-motion.critique.v1",
    specId: spec.id,
    score,
    passed: !open.some((f) => f.severity === "critical") && score >= 70,
    counts: count(open),
    findings: deduped,
    fixable: open.filter((f) => f.fix).length,
    strengths,
    upstream,
    springs: spec.components.filter((c) => c.easing?.type === "spring").map((c) => ({ componentId: c.id, ...describeSpring(c.easing) })),
  };
}

// Stagger expansion ids look like "items__3"; report against the authoring component.
function baseId(id) {
  return id ? String(id).replace(/__\d+$/, "") : null;
}

function mitigated(spec, issue) {
  const id = baseId(issue.componentId);
  const c = spec.components.find((x) => x.id === id);
  const msg = issue.message ?? "";
  if (/loops infinitely|cannot opt out|starts hidden|inaccessible when motion is disabled/i.test(msg)) return !c || c.reducedMotion !== "keep";
  if (/prefers-reduced-motion|reduced[- ]motion/i.test(msg) && /no |missing|without/i.test(msg)) return true;
  // A stagger group is the remedy for simultaneity, not an instance of it.
  if (/play simultaneously/i.test(msg)) {
    // Count each stagger group once; OpenMotion counts every expanded item.
    return spec.components.filter((x) => x.kind !== "particles").length <= 5;
  }
  // Direct-manipulation feedback is meant to be short (100–200ms); small travel is not vestibular.
  if (/animates in \d+ms/i.test(msg) && c && ["onClick", "onHover", "manual", "onState"].includes(c.trigger) && maxAbs(c, ["translateX", "translateY"]) <= 24 && maxAbs(c, ["scale"]) <= 10) return true;
  return false;
}

function dedupe(list) {
  const seen = new Set();
  return list.filter((f) => {
    const key = `${f.componentId}|${f.code}|${f.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function count(list) {
  return list.reduce((acc, f) => ({ ...acc, [f.severity]: (acc[f.severity] ?? 0) + 1 }), { critical: 0, warning: 0, info: 0 });
}

