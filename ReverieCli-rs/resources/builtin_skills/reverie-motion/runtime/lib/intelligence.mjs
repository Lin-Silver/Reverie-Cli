// Variation, style transfer, storytelling, synthesis and Motion DNA.
// Engines are the vendored OpenMotion modules; this layer adapts them to
// product-UI constraints (keep brand colours, no accidental loops, spring-aware).
import * as OM from "../vendor/openmotion.mjs";
import { normalizeSpec, toOpenMotion, mergeFromOpenMotion, normalizeEasing } from "./spec.mjs";
import { critique } from "./critique.mjs";

const DEFAULT_STRATEGIES = ["easing", "timing", "choreography", "intensity", "direction"];

/** Spring "feel" per archetype — used when the target already uses physics. */
export const ARCHETYPE_SPRINGS = {
  minimalist: { response: 0.35, dampingFraction: 1 },
  energetic: { response: 0.32, dampingFraction: 0.6 },
  cinematic: { response: 0.7, dampingFraction: 0.95 },
  playful: { response: 0.45, dampingFraction: 0.5 },
  corporate: { response: 0.4, dampingFraction: 1 },
  organic: { response: 0.6, dampingFraction: 0.75 },
  mechanical: null, // switches to crisp bezier timing
  elegant: { response: 0.55, dampingFraction: 0.9 },
};

const SPRING_FEELS = [
  { id: "snappy", response: 0.3, dampingFraction: 0.86, note: "Fast, no visible bounce — direct manipulation, toggles." },
  { id: "smooth", response: 0.5, dampingFraction: 1, note: "Critically damped glide — large surfaces, sheets." },
  { id: "bouncy", response: 0.5, dampingFraction: 0.6, note: "Playful overshoot — celebratory or small elements only." },
];

function renormalize(spec) {
  const out = normalizeSpec({ ...spec, components: spec.components.map((c) => (c.durationAuto && c.easing.type === "spring" ? { ...c, durationMs: "auto" } : c)) });
  if (!out.ok) throw new Error(`Generated spec is invalid: ${JSON.stringify(out.errors.slice(0, 3))}`);
  return out.spec;
}

function summary(spec) {
  const report = critique(spec);
  return { score: report.score, passed: report.passed, counts: report.counts };
}

/** Motion DNA: spec-level style fingerprint + per-component DNA (OpenMotion). */
export function motionDna(spec) {
  const om = toOpenMotion(spec);
  if (!om.components.length) return { style: null, components: [] };
  const style = OM.extractStyleDNA(om);
  return {
    style,
    description: OM.describeStyle(style),
    components: om.components.filter((c) => !c.id.includes("__") || c.id.endsWith("__0")).map((c) => ({ componentId: c.id.replace(/__0$/, ""), ...OM.extractDNA(c) })),
  };
}

export function compareDna(a, b) {
  return OM.compareStyles(OM.extractStyleDNA(toOpenMotion(a)), OM.extractStyleDNA(toOpenMotion(b)));
}

/**
 * Generate alternatives: OpenMotion variant strategies (palette excluded by
 * default so brand colours are untouched) + native spring-feel variants for
 * spring components. Each variant is a complete, valid spec with its critique.
 */
export function generateVariants(spec, { count = 4, strategies = DEFAULT_STRATEGIES, seed = 1, springFeels = true } = {}) {
  const om = toOpenMotion(spec);
  const out = [];
  if (om.components.length) {
    const variants = OM.generateVariants(om, { count, strategies, seed });
    variants.forEach((v, i) => {
      let next = mergeFromOpenMotion(spec, v.spec);
      next.id = `${spec.id}-v${i + 1}`.slice(0, 64);
      next.name = `${spec.name} · ${v.name}`;
      next.meta = { ...spec.meta, version: 1, operation: "variation", parent: spec.meta?.revisionId ?? spec.id, strategy: v.strategy };
      next = renormalize(next);
      out.push({ id: next.id, strategy: v.strategy, source: "openmotion:motionVariantGenerator", description: v.description, divergence: v.divergence, changes: v.changes.slice(0, 12), critique: summary(next), spec: next });
    });
  }
  if (springFeels && spec.components.some((c) => c.easing.type === "spring")) {
    for (const feel of SPRING_FEELS) {
      let next = structuredClone(spec);
      for (const c of next.components) {
        if (c.easing.type !== "spring") continue;
        c.easing = normalizeEasing({ type: "spring", response: feel.response, dampingFraction: feel.dampingFraction });
        c.durationAuto = true;
      }
      next.id = `${spec.id}-${feel.id}`.slice(0, 64);
      next.name = `${spec.name} · spring ${feel.id}`;
      next.meta = { ...spec.meta, version: 1, operation: "variation", parent: spec.meta?.revisionId ?? spec.id, strategy: `spring:${feel.id}` };
      next = renormalize(next);
      out.push({ id: next.id, strategy: `spring-${feel.id}`, source: "native:spring", description: feel.note, critique: summary(next), spec: next });
    }
  }
  return out;
}

/**
 * Style transfer onto `spec` from an archetype or another spec.
 * strength 0..1 scales every OpenMotion transfer dimension; colours and loop
 * behaviour are preserved unless explicitly allowed.
 */
export function transferStyle(spec, { archetype, from, strength = 0.8, keepColors = true, allowLoops = false } = {}) {
  const om = toOpenMotion(spec);
  if (!om.components.length) throw new Error("Style transfer needs at least one keyframe or flip component.");
  const fields = ["durationMs", "delayMs", "easing", "keyframes", ...(allowLoops ? ["iterationCount", "direction"] : [])];
  const options = {
    easingStrength: strength, tempoStrength: strength, energyStrength: strength, axisStrength: strength * 0.5,
    colorStrength: keepColors ? 0 : strength, complexityStrength: strength * 0.6,
    iterationStrength: allowLoops ? strength : 0, stagingStrength: strength, preserveTargetStructure: true,
  };
  let transferred;
  let sourceLabel;
  if (archetype) {
    if (!OM.getStyleArchetype(archetype)) {
      const error = new Error(`Unknown archetype "${archetype}". Available: ${OM.listStyleArchetypes().map((a) => a.id).join(", ")}`);
      error.code = "ARCHETYPE_NOT_FOUND";
      throw error;
    }
    // applyArchetype uses OpenMotion's fixed defaults; the field filter below enforces our policy.
    transferred = OM.applyArchetype(archetype, om);
    sourceLabel = `archetype:${archetype}`;
  } else if (from) {
    transferred = OM.transferSpecStyle(toOpenMotion(from), om, options);
    sourceLabel = `spec:${from.id}`;
  } else {
    throw new Error("transferStyle needs an archetype or a source spec.");
  }
  let next = mergeFromOpenMotion(spec, transferred, { fields });
  // Spring-aware: physics components keep physics, retuned to the target feel.
  for (const c of next.components) {
    const original = spec.components.find((x) => x.id === c.id);
    if (original?.easing.type !== "spring") {
      if (c.easing.type !== "spring") delete c.durationAuto;
      continue;
    }
    const feel = archetype ? ARCHETYPE_SPRINGS[archetype] : springFeelOf(from);
    if (feel) {
      c.easing = normalizeEasing({ type: "spring", ...feel });
      c.durationAuto = true;
    } else {
      delete c.durationAuto;
    }
  }
  next.id = `${spec.id}-${archetype ?? "styled"}`.slice(0, 64);
  next.name = `${spec.name} · ${archetype ?? `styled like ${from.name}`}`;
  next.meta = { ...spec.meta, version: 1, operation: "style-transfer", parent: spec.meta?.revisionId ?? spec.id, styleSource: sourceLabel, strength };
  next = renormalize(next);
  const beforeDna = OM.extractStyleDNA(om);
  const afterDna = OM.extractStyleDNA(toOpenMotion(next));
  const targetDna = archetype ? OM.getStyleArchetype(archetype).dna : OM.extractStyleDNA(toOpenMotion(from));
  return {
    spec: next,
    source: sourceLabel,
    fieldsTransferred: fields,
    similarityToSource: { before: OM.compareStyles(beforeDna, targetDna).overallSimilarity, after: OM.compareStyles(afterDna, targetDna).overallSimilarity },
    description: OM.describeStyle(afterDna),
    critique: summary(next),
  };
}

function springFeelOf(spec) {
  const s = spec?.components.find((c) => c.easing.type === "spring")?.easing;
  if (!s) return null;
  const zeta = s.damping / (2 * Math.sqrt(s.stiffness * (s.mass ?? 1)));
  const response = (2 * Math.PI) / Math.sqrt(s.stiffness / (s.mass ?? 1));
  return { response: Number(response.toFixed(3)), dampingFraction: Number(zeta.toFixed(3)) };
}

export function listArchetypes() {
  return OM.listStyleArchetypes().map((a) => ({ id: a.id, name: a.name, description: a.description, signatures: a.signatures, spring: ARCHETYPE_SPRINGS[a.id] ?? null }));
}

/**
 * Motion storytelling: OpenMotion's five-act narrative planner produces beats
 * (timing, easing, intensity); each beat is bound to one target selector and
 * realised as transform/opacity keyframes scaled by intensity.
 */
export function storySpec({ id = "story", intent, selectors, totalDurationMs = 3200, stage } = {}) {
  if (!intent) throw new Error(`story intent required: ${OM.listNarrativeIntents().map((i) => i.intent ?? i.id ?? i.name).join(", ")}`);
  if (!Array.isArray(selectors) || !selectors.length) throw new Error("story needs one or more target selectors (one per beat, cycled).");
  const seq = OM.generateStorySequence(intent, { totalDurationMs });
  const components = seq.beats.map((b, i) => {
    const k = b.intensity;
    const rise = Math.round(10 + 36 * k);
    const climax = b.act === "climax";
    return {
      id: `beat-${i + 1}`,
      name: `${b.act}: ${b.label}`.slice(0, 80),
      selector: selectors[i % selectors.length],
      delayMs: Math.round(b.delayMs),
      durationMs: Math.max(160, Math.round(b.durationMs)),
      easing: b.easing,
      keyframes: climax
        ? [{ offset: 0, properties: { translateY: rise, scale: 0.92, opacity: 0 } }, { offset: 0.6, properties: { translateY: -4, scale: 1.03, opacity: 1 } }, { offset: 1, properties: { translateY: 0, scale: 1, opacity: 1 } }]
        : [{ offset: 0, properties: { translateY: rise, opacity: 0 } }, { offset: 1, properties: { translateY: 0, opacity: 1 } }],
    };
  });
  return {
    spec: { id, name: seq.title, description: seq.summary, intent: { purpose: "storytelling", narrative: intent }, components, stage: stage ?? {}, meta: { operation: "story-beat", story: { intent, themes: seq.themes, intensityCurve: seq.intensityCurve } } },
    sequence: { title: seq.title, summary: seq.summary, totalDurationMs: seq.totalDurationMs, beats: seq.beats.map((b) => ({ act: b.act, label: b.label, tone: b.emotionalTone, intensity: b.intensity, delayMs: b.delayMs, durationMs: b.durationMs, hint: b.transformHint })) },
  };
}

export function listNarratives() {
  return OM.listNarrativeIntents();
}

/**
 * Motion synthesis: blend the DNA of components from two or more specs and
 * apply it to `target` (a spec whose first animated component receives it).
 */
export function synthesize(sources, target, { strategy = "blend", seed = 1 } = {}) {
  const comps = sources.flatMap((s) => toOpenMotion(s).components.filter((c) => !c.id.includes("__") || c.id.endsWith("__0")));
  if (comps.length < 2) throw new Error("Synthesis needs at least two source components across the given specs.");
  const result = OM.synthesizeMotion(comps, { strategy, seed });
  const om = toOpenMotion(target);
  const host = om.components[0];
  if (!host) throw new Error("Synthesis target has no animatable component.");
  const hybrid = OM.applySynthesizedDNA(host, result);
  hybrid.id = host.id;
  let next = mergeFromOpenMotion(target, { ...om, components: [hybrid, ...om.components.slice(1)] }, { fields: ["durationMs", "delayMs", "easing", "keyframes", "iterationCount"] });
  for (const c of next.components) if (c.easing.type !== "spring") delete c.durationAuto;
  next.id = `${target.id}-synth`.slice(0, 64);
  next.name = `${target.name} · synthesized`;
  next.meta = { ...target.meta, version: 1, operation: "synthesis", parent: target.meta?.revisionId ?? target.id, sources: sources.map((s) => s.meta?.revisionId ?? s.id), strategy, seed };
  next = renormalize(next);
  return { spec: next, summary: result.summary, attributions: result.attributions, dna: result.dna, critique: summary(next) };
}
