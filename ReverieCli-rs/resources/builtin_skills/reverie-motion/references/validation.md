# Validation: critique codes, preview evidence, thresholds

## Static critique (`RM critique`)

Score = 100 − Σ(open findings: critical 20, warning 7, info 1). `passed` = no open critical and score ≥ 70. Findings carry `code`, `source`, `severity`, `dimension`, `componentId`, `message`, optional machine `fix`, and `status` (`open` or `mitigated` — an upstream finding the compiler already handles, e.g. "no reduced-motion alternative", kept for transparency and excluded from the score).

### Native rules (source `native`)

| Code | Trigger | Auto-fix |
|---|---|---|
| RM001 | layout property animated (width, height, top/left/…, margin, padding, font-size) | numeric width/height → scaleX/Y, top/left → translate |
| RM002 | animated backdrop blur (warning), blur > 12px (warning), paint properties (info) | drop backdrop animation; clamp blur to 10px |
| RM003 | duration outside the role's range (feedback > 300ms, entrance > 1000ms, exit > 300ms, transition > 700ms); feedback spring settling > 600ms; wobbly large surface (info) | set duration / snappier spring |
| RM004 | spring truncated (duration < 0.9 × settle) or dead tail (> 1.6 × settle, info) | duration = settle time |
| RM005 | `ease-in` family on response/arrival | ease-out / ease-out-quart |
| RM006 | `linear` on non-looping movement | ease-out-quart |
| RM007 | stagger cascade > 600ms (warning) or > 100ms per item (info) | shorter step |
| RM009 | scale from < 0.3 (warning) / < 0.6 on entrance (info) | start at 0.85 |
| RM010 | delayed/staggered entrance with fill `none`/`forwards` whose first frame hides content — flash of final state | fill `both` |
| RM012 | large movement kept under reduced motion | `fade` |
| RM013 | > 150 particles, DPR > 2 | 120 particles, DPR 2 |
| RM014 | fast infinite loop with large travel | 4s period |
| RM015 | long eased toggle (info) — prefer a spring | — |
| RM016 | scale with a trigger but no `transformOrigin` (info) | — |

### OpenMotion analysers (vendored, unmodified)

`openmotion:critique` (accessibility/performance/aesthetic/consistency), `openmotion:accessibility` (vestibular, seizure/flash, reduced-motion, cognitive), `openmotion:performance` (paint/layout/composite cost model), plus a genome/diversity summary in `upstream.genome`. Auto-fix also runs OpenMotion's `autoFixAccessibility`, but every upstream change passes a policy; rejected changes are listed in `rejected` with the reason (e.g. capping an ambient loop to 3 iterations, snapping spring durations to fixed tiers, shortening micro-interactions).

## Preview (`RM preview`)

Three phases per viewport (default desktop 1280×800@1 and mobile 390×844@2 with touch):

1. **Live run** — real time, with a frame probe: `perf.fps`, `meanMs`, `p95FrameMs`, `droppedFrames` (> 25ms), `layoutCount` / `layoutsPerFrame`, `recalcStyleCount`, layout/style/script durations, `cls` (layout-shift sum), `longTasks`, runtime `errors` (exceptions, console errors, failed loads).
2. **Deterministic sampling** — every `Animation` (CSS animations, transitions, WAAPI) is paused and seeked to each sample time; reverie previews also seek canvas particle fields. Each sample saves `frame-<viewport>-<t>.png` and the computed state of tracked elements (rect, opacity, transform matrix → `scaleX/scaleY/translateX/translateY`, filter, clip-path, stroke-dashoffset, whether an ancestor clips it). Pages with only rAF/canvas motion and no seek hook fall back to real-time sampling (`sampling.mode: "realtime"`).
3. **Reduced motion** — `prefers-reduced-motion: reduce` emulated: long-running animations still active, tracked elements' visibility, screenshot `reduced-<viewport>.png`, particle canvases.

Visual analysis runs in a separate blank tab with `<canvas>`: per-frame `coverage` (pixels differing from the corner background), `diffPrev`/`changedPrev` (change from previous sample), `motionEnergy` (sum of diffs), `firstToLast`, and a labelled `contact-<viewport>.png` grid.

Headless Chromium is not vsync-locked, so `fps` can exceed 60; use `p95FrameMs`, dropped frames, long tasks and `layoutsPerFrame` as the signals, not absolute fps.

### Runtime findings (RV)

| Code | Severity | Meaning |
|---|---|---|
| RV001 | critical | runtime errors (normal or reduced-motion run) |
| RV002 | warning | `layoutsPerFrame` > 0.5 over > 10 frames — a layout property is animating |
| RV003 | warning / critical | CLS > 0.02 / > 0.1 |
| RV004 | warning | p95 frame > 25ms or long tasks during motion |
| RV005 | warning / critical | motion still running under reduced motion / content hidden under reduced motion but visible otherwise |
| RV006 | warning | horizontal overflow (document wider than viewport, or an unclipped tracked element leaves the viewport) |
| RV007 | critical | sampled frames visually identical — nothing visibly moves |
| RV008 | warning | final opacity differs from the spec's last keyframe |
| RV009 | warning | blank frame between visible frames |
| RV010 | critical | no Animation objects after load/actions although onLoad motion is expected |

Preview score = 100 − Σ(critical 30, warning 10, info 2); `passed` = no critical and score ≥ 70.

## Reading the evidence

1. Open `contact-desktop.png` / `contact-mobile.png` (if you can view images): check the first frame is the intended start (not a flash of the end state), motion reads in the intended direction, the last frame is the designed end state, nothing clips or overflows on mobile.
2. From `preview-report.json` → `viewports[].samples[].elements`, confirm numerically: e.g. opacity rises monotonically, `scaleX` overshoots then settles for springs, stagger items start in order, `strokeDashoffset` goes 1 → 0.
3. Compare `reduced-*.png` with the final frame: the content must be present.
4. For interactions, preview with actions and sample after them; for toggles also sample a reversal (`toggle:ID`, `wait:MS`, `toggle:ID`).
