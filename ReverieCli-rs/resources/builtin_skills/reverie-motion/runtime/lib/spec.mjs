// Reverie MotionSpec v1 — structured, framework-neutral animation description.
//
// It is a compatible superset of OpenMotion's MotionSpec
// (open-motion/src/shared/motion/spec.ts): every component carries the same
// timing / easing / keyframe fields, so the vendored OpenMotion analysers run
// on `toOpenMotion(spec)` unchanged. Extensions: `kind` (flip, particles),
// `stagger`, `reducedMotion`, `transformOrigin`, `toggle`, spring easing in
// perceptual units, and a preview `stage`.
import { normalizeSpring, settleTimeMs } from "./spring.mjs";

export const SPEC_SCHEMA = "reverie-motion/spec@1";

export const PRESET_NAMES = [
  "linear", "ease", "ease-in", "ease-out", "ease-in-out",
  "ease-in-quad", "ease-out-quad", "ease-in-out-quad",
  "ease-in-cubic", "ease-out-cubic", "ease-in-out-cubic",
  "bounce", "back", "elastic", "snappy", "smooth", "soft",
  // Reverie additions (strong UI curves; see references/easing-and-springs.md)
  "ease-out-quart", "ease-out-expo", "ease-in-out-quart", "emphasized",
];

export const REVERIE_BEZIER = {
  "ease-out-quart": [0.25, 1, 0.5, 1],
  "ease-out-expo": [0.16, 1, 0.3, 1],
  "ease-in-out-quart": [0.76, 0, 0.24, 1],
  emphasized: [0.2, 0, 0, 1],
};

export const TRANSFORM_PROPS = [
  "translateX", "translateY", "translateZ", "scale", "scaleX", "scaleY",
  "rotate", "rotateX", "rotateY", "rotateZ", "skewX", "skewY",
];
export const FILTER_PROPS = ["blur", "brightness", "saturate", "contrast", "hueRotate"];
export const OTHER_PROPS = [
  "opacity", "backdropBlur", "clipPath", "borderRadius", "color", "backgroundColor",
  "width", "height", "boxShadow", "strokeDashoffset", "letterSpacing", "fontSize",
  "backgroundPosition", "top", "left", "right", "bottom", "margin", "padding",
];
export const ALL_PROPS = new Set([...TRANSFORM_PROPS, ...FILTER_PROPS, ...OTHER_PROPS]);
/** Properties a browser can animate on the compositor without layout or paint per frame. */
export const COMPOSITED_PROPS = new Set([...TRANSFORM_PROPS, "opacity"]);
/** Paint-only (no layout) but not composited. */
export const PAINT_PROPS = new Set([...FILTER_PROPS, "backdropBlur", "clipPath", "color", "backgroundColor", "boxShadow", "borderRadius", "strokeDashoffset", "backgroundPosition"]);
/** Trigger layout every frame. */
export const LAYOUT_PROPS = new Set(["width", "height", "top", "left", "right", "bottom", "margin", "padding", "fontSize", "letterSpacing"]);

const KINDS = ["keyframes", "flip", "particles"];
const TRIGGERS = ["onLoad", "onClick", "onHover", "onScroll", "manual", "onState"];
const DIRECTIONS = ["normal", "reverse", "alternate", "alternate-reverse"];
const FILLS = ["none", "forwards", "backwards", "both"];
const REDUCED = ["final-state", "first-frame", "fade", "keep"];
const PURPOSES = ["entrance", "exit", "feedback", "transition", "ambient", "attention", "storytelling", "loading"];
const ID = /^[a-z0-9][a-z0-9-_]{0,63}$/i;

/** Parse an easing shorthand or object into an OpenMotion-compatible Easing. */
export function normalizeEasing(input, path = "easing", errors = []) {
  if (input == null) return { type: "preset", name: "ease-out" };
  if (typeof input === "string") {
    const s = input.trim();
    if (PRESET_NAMES.includes(s)) return { type: "preset", name: s };
    const m = s.match(/^cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)$/);
    if (m) {
      const [x1, y1, x2, y2] = m.slice(1).map(Number);
      return checkBezier({ type: "bezier", p1: [x1, y1], p2: [x2, y2] }, path, errors);
    }
    errors.push({ path, message: `Unknown easing "${s}". Use a preset (${PRESET_NAMES.join(", ")}), cubic-bezier(...), or a spring object.` });
    return { type: "preset", name: "ease-out" };
  }
  if (typeof input === "object") {
    if (input.type === "preset") {
      if (!PRESET_NAMES.includes(input.name)) errors.push({ path: `${path}.name`, message: `Unknown preset "${input.name}".` });
      return { type: "preset", name: PRESET_NAMES.includes(input.name) ? input.name : "ease-out" };
    }
    if (input.type === "bezier") return checkBezier({ type: "bezier", p1: [...input.p1], p2: [...input.p2] }, path, errors);
    if (input.type === "spring") {
      try {
        const n = normalizeSpring(input);
        const out = { type: "spring", stiffness: n.stiffness, damping: n.damping, mass: n.mass };
        if (n.velocity) out.velocity = n.velocity;
        return out;
      } catch (error) {
        errors.push({ path, message: error.message });
        return { type: "preset", name: "ease-out" };
      }
    }
  }
  errors.push({ path, message: "Easing must be a preset name, cubic-bezier(...) string, or {type: preset|bezier|spring}." });
  return { type: "preset", name: "ease-out" };
}

function checkBezier(e, path, errors) {
  const ok = [...e.p1, ...e.p2].every(Number.isFinite) && e.p1[0] >= 0 && e.p1[0] <= 1 && e.p2[0] >= 0 && e.p2[0] <= 1;
  if (!ok) errors.push({ path, message: "cubic-bezier x values must be within [0, 1]." });
  return e;
}

/**
 * Validate and normalise a spec. Never throws for content problems; returns
 * {ok, spec, errors, warnings}. `errors` block compile/preview, `warnings` don't.
 */
export function normalizeSpec(input) {
  const errors = [];
  const warnings = [];
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return { ok: false, spec: null, errors: [{ path: "", message: "Spec must be a JSON object." }], warnings };
  }
  if (input.schema && input.schema !== SPEC_SCHEMA) {
    errors.push({ path: "schema", message: `Unsupported schema "${input.schema}"; expected ${SPEC_SCHEMA}.` });
  }
  const id = String(input.id ?? "");
  if (!ID.test(id)) errors.push({ path: "id", message: "id must be 1-64 chars of letters, digits, - or _ and start with a letter or digit." });
  const purpose = input.intent?.purpose ?? "entrance";
  if (!PURPOSES.includes(purpose)) errors.push({ path: "intent.purpose", message: `purpose must be one of ${PURPOSES.join(", ")}.` });

  const spec = {
    schema: SPEC_SCHEMA,
    id,
    name: String(input.name ?? id),
    description: String(input.description ?? ""),
    intent: { purpose, ...(input.intent ?? {}), purpose },
    tokens: { ...(input.tokens ?? {}) },
    stage: normalizeStage(input.stage),
    components: [],
    meta: { version: 1, ...(input.meta ?? {}) },
  };

  if (!Array.isArray(input.components) || input.components.length === 0) {
    errors.push({ path: "components", message: "components must be a non-empty array." });
  } else {
    const seen = new Set();
    input.components.forEach((raw, index) => {
      const c = normalizeComponent(raw, `components[${index}]`, errors, warnings, index);
      if (seen.has(c.id)) errors.push({ path: `components[${index}].id`, message: `Duplicate component id "${c.id}".` });
      seen.add(c.id);
      spec.components.push(c);
    });
  }
  return { ok: errors.length === 0, spec, errors, warnings };
}

function normalizeStage(stage = {}) {
  return {
    width: Number.isFinite(stage.width) ? stage.width : 960,
    height: Number.isFinite(stage.height) ? stage.height : 600,
    background: typeof stage.background === "string" ? stage.background : "#0b0d12",
    colorScheme: stage.colorScheme === "light" ? "light" : "dark",
    html: typeof stage.html === "string" ? stage.html : "",
    css: typeof stage.css === "string" ? stage.css : "",
    script: typeof stage.script === "string" ? stage.script : "",
  };
}

function normalizeComponent(raw, path, errors, warnings, index) {
  const c = raw && typeof raw === "object" ? raw : {};
  const kind = c.kind ?? "keyframes";
  if (!KINDS.includes(kind)) errors.push({ path: `${path}.kind`, message: `kind must be one of ${KINDS.join(", ")}.` });
  const id = String(c.id ?? `c${index + 1}`);
  if (!ID.test(id)) errors.push({ path: `${path}.id`, message: "Invalid component id." });
  const selector = typeof c.selector === "string" && c.selector.trim() ? c.selector.trim() : null;
  if (kind !== "flip" && !selector) errors.push({ path: `${path}.selector`, message: "selector is required (a CSS selector in the target markup)." });

  const easing = normalizeEasing(c.easing, `${path}.easing`, errors);
  let durationMs = c.durationMs;
  if (durationMs === "auto" || durationMs == null) {
    durationMs = easing.type === "spring" ? settleTimeMs(easing) : 400;
  }
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    errors.push({ path: `${path}.durationMs`, message: "durationMs must be a positive number or \"auto\"." });
    durationMs = 400;
  }
  const iterationCount = c.iterationCount ?? 1;
  if (!(iterationCount === "infinite" || (Number.isInteger(iterationCount) && iterationCount > 0))) {
    errors.push({ path: `${path}.iterationCount`, message: "iterationCount must be a positive integer or \"infinite\"." });
  }
  const trigger = c.trigger ?? "onLoad";
  if (!TRIGGERS.includes(trigger)) errors.push({ path: `${path}.trigger`, message: `trigger must be one of ${TRIGGERS.join(", ")}.` });
  const direction = c.direction ?? "normal";
  if (!DIRECTIONS.includes(direction)) errors.push({ path: `${path}.direction`, message: "invalid direction" });
  const fillMode = c.fillMode ?? "both";
  if (!FILLS.includes(fillMode)) errors.push({ path: `${path}.fillMode`, message: "invalid fillMode" });
  const reducedMotion = c.reducedMotion ?? (iterationCount === "infinite" ? "first-frame" : "final-state");
  if (!REDUCED.includes(reducedMotion)) errors.push({ path: `${path}.reducedMotion`, message: `reducedMotion must be one of ${REDUCED.join(", ")}.` });

  const keyframes = [];
  if (kind === "keyframes") {
    if (!Array.isArray(c.keyframes) || c.keyframes.length < 2) {
      errors.push({ path: `${path}.keyframes`, message: "keyframes needs at least two frames (offset 0 and 1)." });
    } else {
      let last = -1;
      c.keyframes.forEach((kf, i) => {
        const kpath = `${path}.keyframes[${i}]`;
        const offset = kf?.offset;
        if (!Number.isFinite(offset) || offset < 0 || offset > 1) errors.push({ path: `${kpath}.offset`, message: "offset must be within [0, 1]." });
        else if (offset < last) errors.push({ path: `${kpath}.offset`, message: "offsets must be ascending." });
        last = Number.isFinite(offset) ? offset : last;
        const properties = {};
        for (const [prop, value] of Object.entries(kf?.properties ?? {})) {
          if (!ALL_PROPS.has(prop)) {
            errors.push({ path: `${kpath}.properties.${prop}`, message: `Unsupported property "${prop}".` });
            continue;
          }
          if (!(typeof value === "number" && Number.isFinite(value)) && typeof value !== "string") {
            errors.push({ path: `${kpath}.properties.${prop}`, message: "value must be a finite number or a CSS string." });
            continue;
          }
          properties[prop] = value;
        }
        const frame = { offset, properties };
        if (kf?.easing != null) frame.easing = normalizeEasing(kf.easing, `${kpath}.easing`, errors);
        keyframes.push(frame);
      });
      if (keyframes.length && keyframes[0].offset !== 0) errors.push({ path: `${path}.keyframes[0].offset`, message: "first keyframe offset must be 0." });
      if (keyframes.length && keyframes[keyframes.length - 1].offset !== 1) errors.push({ path: `${path}.keyframes[-1].offset`, message: "last keyframe offset must be 1." });
    }
  }

  const out = {
    id,
    name: String(c.name ?? id),
    kind,
    selector,
    durationMs: Math.round(durationMs),
    delayMs: Number.isFinite(c.delayMs) && c.delayMs >= 0 ? Math.round(c.delayMs) : 0,
    iterationCount,
    direction,
    fillMode,
    trigger,
    easing,
    keyframes,
    style: c.style && typeof c.style === "object" ? { ...c.style } : {},
    reducedMotion,
  };
  if (c.durationMs === "auto" || (c.durationMs == null && easing.type === "spring")) out.durationAuto = true;
  if (typeof c.transformOrigin === "string") out.transformOrigin = c.transformOrigin;
  if (c.triggerSelector) out.triggerSelector = String(c.triggerSelector);
  if (c.toggle === true) out.toggle = true;
  if (c.stagger) {
    const s = c.stagger;
    // Negative steps are allowed only for infinite loops (start loops out of phase).
    if (!Number.isFinite(s.eachMs) || (s.eachMs < 0 && iterationCount !== "infinite")) errors.push({ path: `${path}.stagger.eachMs`, message: "stagger.eachMs must be >= 0 (negative only for infinite loops)." });
    out.stagger = {
      eachMs: Number.isFinite(s.eachMs) ? s.eachMs : 40,
      from: ["start", "end", "center"].includes(s.from) ? s.from : "start",
      count: Number.isInteger(s.count) && s.count > 0 ? s.count : 5,
    };
  }
  if (kind === "flip") {
    const f = c.flip ?? {};
    if (!f.from || !f.to) errors.push({ path: `${path}.flip`, message: "flip needs {from, to} selectors." });
    out.flip = { from: String(f.from ?? ""), to: String(f.to ?? ""), crossfade: f.crossfade !== false };
  }
  if (kind === "particles") {
    const p = c.particles ?? {};
    out.particles = {
      count: clampInt(p.count, 1, 2000, 80),
      colors: Array.isArray(p.colors) && p.colors.length ? p.colors.map(String) : ["#ffffff"],
      sizeMin: num(p.sizeMin, 1),
      sizeMax: num(p.sizeMax, 3),
      speed: num(p.speed, 24),
      seed: clampInt(p.seed, 1, 2 ** 31 - 1, 7),
      drift: num(p.drift, 0.6),
      twinkle: p.twinkle !== false,
      maxDpr: num(p.maxDpr, 2),
    };
    if (out.particles.count > 400) warnings.push({ path: `${path}.particles.count`, message: "More than 400 particles costs real CPU on low-end phones; see critique RM013." });
  }
  return out;
}

const num = (v, d) => (Number.isFinite(v) ? v : d);
const clampInt = (v, lo, hi, d) => (Number.isInteger(v) ? Math.min(hi, Math.max(lo, v)) : d);

/** Final-state property map (last keyframe) — used for reduced-motion and checks. */
export function finalProperties(component) {
  const out = {};
  for (const kf of component.keyframes) Object.assign(out, kf.properties);
  return out;
}
export function firstProperties(component) {
  return { ...(component.keyframes[0]?.properties ?? {}) };
}

/** Indices order for stagger groups. */
export function staggerOrder(count, from) {
  const idx = [...Array(count).keys()];
  if (from === "end") return idx.map((i) => count - 1 - i);
  if (from === "center") {
    const mid = (count - 1) / 2;
    return idx.map((i) => Math.round(Math.abs(i - mid)));
  }
  return idx;
}

/**
 * Convert to an OpenMotion MotionSpec so the vendored upstream analysers can
 * run. Stagger groups expand into `count` components with stepped delays;
 * flip components are approximated as translate+scale keyframes; particle
 * fields are excluded (they are covered by native rules).
 */
export function toOpenMotion(spec) {
  const now = new Date(0).toISOString();
  const components = [];
  let order = 0;
  for (const c of spec.components) {
    if (c.kind === "particles") continue;
    const base = {
      projectId: spec.id,
      sceneId: null,
      name: c.name,
      selector: c.selector,
      templateId: spec.meta?.template ?? null,
      durationMs: c.durationMs,
      delayMs: c.delayMs,
      iterationCount: c.iterationCount,
      direction: c.direction,
      fillMode: c.fillMode,
      playState: "running",
      trigger: ["manual", "onState"].includes(c.trigger) ? "onClick" : c.trigger,
      easing: toUpstreamEasing(c.easing),
      keyframes:
        c.kind === "flip"
          ? [
              { offset: 0, properties: { translateX: 120, translateY: 80, scale: 0.6 } },
              { offset: 1, properties: { translateX: 0, translateY: 0, scale: 1 } },
            ]
          : c.keyframes.map((k) => ({ offset: k.offset, properties: { ...k.properties }, ...(k.easing ? { easing: toUpstreamEasing(k.easing) } : {}) })),
      style: { ...c.style },
      parentId: null,
      createdAt: now,
      updatedAt: now,
    };
    if (c.stagger) {
      const order2 = staggerOrder(c.stagger.count, c.stagger.from);
      for (let i = 0; i < c.stagger.count; i += 1) {
        components.push({ ...base, id: `${c.id}__${i}`, name: `${c.name} #${i + 1}`, delayMs: Math.max(0, c.delayMs + order2[i] * c.stagger.eachMs), orderIndex: order++ });
      }
    } else {
      components.push({ ...base, id: c.id, orderIndex: order++ });
    }
  }
  return {
    project: {
      id: spec.id,
      name: spec.name,
      description: spec.description,
      scenes: [],
      tokens: spec.tokens,
      globalTiming: {},
      status: "draft",
      sourceTemplateId: spec.meta?.template ?? null,
      createdAt: now,
      updatedAt: now,
    },
    components,
  };
}

/** OpenMotion only knows its own presets; map Reverie-only presets to bezier. */
export function toUpstreamEasing(e) {
  if (e.type === "preset" && REVERIE_BEZIER[e.name]) {
    const [a, b, c, d] = REVERIE_BEZIER[e.name];
    return { type: "bezier", p1: [a, b], p2: [c, d] };
  }
  if (e.type === "spring") return { type: "spring", stiffness: e.stiffness, damping: e.damping, mass: e.mass ?? 1 };
  return e;
}

/**
 * Merge timing/easing/keyframe changes from an upstream-transformed MotionSpec
 * back into a Reverie spec (structure, selectors, stage and extensions kept).
 * `fields` limits what is copied.
 */
export function mergeFromOpenMotion(spec, om, { fields = ["durationMs", "delayMs", "easing", "iterationCount", "direction", "keyframes"] } = {}) {
  const byId = new Map(om.components.map((c) => [c.id, c]));
  const next = structuredClone(spec);
  for (const c of next.components) {
    const first = byId.get(c.id) ?? byId.get(`${c.id}__0`);
    if (!first) continue;
    for (const field of fields) {
      if (field === "keyframes" && c.kind !== "keyframes") continue;
      if (first[field] === undefined) continue;
      c[field] = structuredClone(first[field]);
    }
    if (fields.includes("durationMs")) c.durationMs = Math.max(1, Math.round(c.durationMs));
    if (c.stagger && fields.includes("delayMs")) {
      const second = byId.get(`${c.id}__1`);
      if (second) {
        const order = staggerOrder(c.stagger.count, c.stagger.from);
        const step = order[1] - order[0] || 1;
        c.stagger.eachMs = Math.max(0, Math.round((second.delayMs - first.delayMs) / step));
      }
      c.delayMs = Math.max(0, first.delayMs - staggerOrder(c.stagger.count, c.stagger.from)[0] * c.stagger.eachMs);
    }
    if (c.easing?.type === "spring" && c.durationAuto) c.durationMs = settleTimeMs(c.easing);
  }
  return next;
}
