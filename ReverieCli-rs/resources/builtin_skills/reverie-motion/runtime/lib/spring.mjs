// Analytic damped-harmonic-oscillator spring — native Reverie Motion code.
//
// OpenMotion approximates every spring with one of two fixed cubic-beziers
// (shared/motion/easing.ts → easingToCss). This module solves the actual
// ODE  m·x'' + c·x' + k·(x − 1) = 0,  x(0) = 0,  x'(0) = v0
// and turns the solution into a CSS `linear()` timing function, a settle
// duration, and sampled keyframes.

const TWO_PI = Math.PI * 2;

/**
 * Normalise any supported spring description to {stiffness, damping, mass, velocity}.
 * Accepted forms:
 *   {stiffness, damping, mass?, velocity?}     physical (OpenMotion compatible)
 *   {response, dampingFraction, velocity?}     Apple / SwiftUI perceptual
 *   {duration, bounce, velocity?}              SwiftUI `.spring(duration:bounce:)`, duration in seconds
 */
export function normalizeSpring(input = {}) {
  const velocity = Number.isFinite(input.velocity) ? input.velocity : 0;
  if (Number.isFinite(input.stiffness) && Number.isFinite(input.damping)) {
    const mass = Number.isFinite(input.mass) && input.mass > 0 ? input.mass : 1;
    if (input.stiffness <= 0) throw new RangeError("spring stiffness must be > 0");
    if (input.damping < 0) throw new RangeError("spring damping must be >= 0");
    return { stiffness: input.stiffness, damping: input.damping, mass, velocity };
  }
  let response;
  let fraction;
  if (Number.isFinite(input.response)) {
    response = input.response;
    fraction = Number.isFinite(input.dampingFraction) ? input.dampingFraction : 0.825;
  } else if (Number.isFinite(input.duration)) {
    response = input.duration;
    const bounce = Number.isFinite(input.bounce) ? input.bounce : 0;
    // SwiftUI: bounce in (-1, 1); positive = underdamped, negative = overdamped.
    fraction = bounce >= 0 ? 1 - bounce : 1 / (1 + bounce);
  } else {
    throw new TypeError("spring needs {stiffness, damping} or {response, dampingFraction} or {duration, bounce}");
  }
  if (!(response > 0)) throw new RangeError("spring response/duration must be > 0 seconds");
  if (!(fraction >= 0)) throw new RangeError("spring dampingFraction must be >= 0");
  const mass = 1;
  const stiffness = (TWO_PI / response) ** 2 * mass;
  const damping = (4 * Math.PI * fraction * mass) / response;
  return { stiffness: round(stiffness, 4), damping: round(damping, 4), mass, velocity };
}

/** Damping ratio ζ (1 = critical, < 1 bouncy, > 1 sluggish). */
export function dampingRatio(spring) {
  const { stiffness, damping, mass } = normalizeSpring(spring);
  return damping / (2 * Math.sqrt(stiffness * mass));
}

/**
 * Closed-form solver. Returns {position(t), velocity(t)} with t in seconds,
 * position normalised so 0 = start and 1 = target.
 */
export function solveSpring(spring) {
  const { stiffness: k, damping: c, mass: m, velocity: v0 } = normalizeSpring(spring);
  const w0 = Math.sqrt(k / m);
  const zeta = c / (2 * Math.sqrt(k * m));
  // y(t) = x(t) − 1, y(0) = −1, y'(0) = v0
  if (zeta < 1 - 1e-9) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    const A = -1;
    const B = (v0 + zeta * w0 * A) / wd;
    return {
      zeta,
      position(t) {
        const e = Math.exp(-zeta * w0 * t);
        return 1 + e * (A * Math.cos(wd * t) + B * Math.sin(wd * t));
      },
      velocity(t) {
        const e = Math.exp(-zeta * w0 * t);
        const cos = Math.cos(wd * t);
        const sin = Math.sin(wd * t);
        return e * ((B * wd - zeta * w0 * A) * cos - (A * wd + zeta * w0 * B) * sin);
      },
    };
  }
  if (zeta <= 1 + 1e-9) {
    // y = e^{-w0 t}(A + B t);  y'(0) = B − w0·A = v0  ⇒  B = v0 + w0·A
    const A = -1;
    const Bc = v0 + w0 * A;
    return {
      zeta,
      position(t) {
        return 1 + Math.exp(-w0 * t) * (A + Bc * t);
      },
      velocity(t) {
        return Math.exp(-w0 * t) * (Bc - w0 * (A + Bc * t));
      },
    };
  }
  const s = Math.sqrt(zeta * zeta - 1);
  const r1 = -w0 * (zeta - s);
  const r2 = -w0 * (zeta + s);
  const C2 = (v0 + r1) / (r2 - r1); // from C1 + C2 = −1, r1·C1 + r2·C2 = v0
  const C1 = -1 - C2;
  return {
    zeta,
    position(t) {
      return 1 + C1 * Math.exp(r1 * t) + C2 * Math.exp(r2 * t);
    },
    velocity(t) {
      return C1 * r1 * Math.exp(r1 * t) + C2 * r2 * Math.exp(r2 * t);
    },
  };
}

/**
 * Time (ms) after which the spring stays within `epsilon` of the target and
 * its speed stays below `velocityEpsilon` (per second, normalised units).
 */
export function settleTimeMs(spring, { epsilon = 0.001, velocityEpsilon = 0.01, maxMs = 10000 } = {}) {
  const solved = solveSpring(spring);
  let lastUnsettled = 0;
  for (let ms = 0; ms <= maxMs; ms += 1) {
    const t = ms / 1000;
    if (Math.abs(solved.position(t) - 1) > epsilon || Math.abs(solved.velocity(t)) > velocityEpsilon) {
      lastUnsettled = ms;
    }
  }
  return Math.min(maxMs, lastUnsettled + 1);
}

/** Peak overshoot beyond the target, as a fraction (0.08 = 8 %). */
export function overshoot(spring, durationMs = settleTimeMs(spring)) {
  const solved = solveSpring(spring);
  let peak = 0;
  for (let ms = 0; ms <= durationMs; ms += 1) peak = Math.max(peak, solved.position(ms / 1000) - 1);
  return round(Math.max(0, peak), 4);
}

/**
 * Sample the spring as a CSS `linear()` easing over `durationMs`
 * (defaults to the settle time). Points are reduced with Ramer–Douglas–Peucker
 * so the string stays small while the curve error stays under `tolerance`.
 */
export function springToLinear(spring, { durationMs, tolerance = 0.0015, maxPoints = 120 } = {}) {
  const duration = durationMs ?? settleTimeMs(spring);
  const solved = solveSpring(spring);
  const steps = Math.min(600, Math.max(60, Math.round(duration / 4)));
  const raw = [];
  for (let i = 0; i <= steps; i += 1) {
    const x = i / steps;
    raw.push([x, solved.position((x * duration) / 1000)]);
  }
  raw[raw.length - 1][1] = 1; // land exactly on target at the end of the timeline
  let points = rdp(raw, tolerance);
  let tol = tolerance;
  while (points.length > maxPoints) {
    tol *= 1.5;
    points = rdp(raw, tol);
  }
  const body = points
    .map(([x, y], i) => {
      const value = fmt(y);
      if (i === 0 || i === points.length - 1) return value;
      return `${value} ${fmt(x * 100, 2)}%`;
    })
    .join(", ");
  return { css: `linear(${body})`, durationMs: duration, points: points.length, maxError: tol };
}

/** Evaluate a parsed `linear()` point list at progress x (used by tests). */
export function evaluateLinearPoints(points, x) {
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    if (x <= x1) return x1 === x0 ? y1 : y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
  }
  return points[points.length - 1][1];
}

/** Parse a CSS linear() string produced by springToLinear back to points. */
export function parseLinear(css) {
  const inner = css.trim().replace(/^linear\(/, "").replace(/\)$/, "");
  const parts = inner.split(",").map((p) => p.trim().split(/\s+/));
  return parts.map((p, i) => {
    const y = Number(p[0]);
    const x = p[1] ? Number(p[1].replace("%", "")) / 100 : i === 0 ? 0 : 1;
    return [x, y];
  });
}

/** Interpolate numeric keyframe values along the spring for WAAPI baking. */
export function springSamples(spring, { durationMs, fps = 60 } = {}) {
  const duration = durationMs ?? settleTimeMs(spring);
  const solved = solveSpring(spring);
  const frames = Math.max(2, Math.round((duration / 1000) * fps));
  const out = [];
  for (let i = 0; i <= frames; i += 1) {
    const x = i / frames;
    out.push({ offset: round(x, 5), progress: i === frames ? 1 : solved.position((x * duration) / 1000) });
  }
  return out;
}

/** Summary used by critique, docs and the CLI. */
export function describeSpring(spring) {
  const n = normalizeSpring(spring);
  const settle = settleTimeMs(n);
  const zeta = dampingRatio(n);
  return {
    ...n,
    dampingRatio: round(zeta, 4),
    character: zeta < 0.5 ? "bouncy" : zeta < 0.85 ? "lively" : zeta <= 1.0001 ? "smooth" : "sluggish",
    settleMs: settle,
    overshoot: overshoot(n, settle),
    response: round(TWO_PI / Math.sqrt(n.stiffness / n.mass), 4),
  };
}

function rdp(points, epsilon) {
  if (points.length < 3) return points.slice();
  const [x1, y1] = points[0];
  const [x2, y2] = points[points.length - 1];
  let index = 0;
  let max = 0;
  for (let i = 1; i < points.length - 1; i += 1) {
    const [x, y] = points[i];
    // vertical distance to the chord — the error a linear() segment introduces
    const yi = y1 + ((y2 - y1) * (x - x1)) / (x2 - x1 || 1);
    const d = Math.abs(y - yi);
    if (d > max) {
      max = d;
      index = i;
    }
  }
  if (max <= epsilon) return [points[0], points[points.length - 1]];
  const left = rdp(points.slice(0, index + 1), epsilon);
  const right = rdp(points.slice(index), epsilon);
  return left.slice(0, -1).concat(right);
}

function fmt(n, digits = 4) {
  const v = Number(n.toFixed(digits));
  return Object.is(v, -0) ? "0" : String(v);
}

function round(n, digits) {
  return Number(n.toFixed(digits));
}
