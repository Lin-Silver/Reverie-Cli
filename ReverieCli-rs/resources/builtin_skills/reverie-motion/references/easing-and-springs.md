# Easing and springs

## Presets

| Name | CSS | Use |
|---|---|---|
| `ease-out` | native | small feedback |
| `ease-out-quart` | `cubic-bezier(0.25, 1, 0.5, 1)` | default for entrances and reveals |
| `ease-out-expo` | `cubic-bezier(0.16, 1, 0.3, 1)` | large reveals, masks |
| `ease-out-cubic` | `cubic-bezier(0.33, 1, 0.68, 1)` | general UI |
| `emphasized` | `cubic-bezier(0.2, 0, 0, 1)` | expressive transitions |
| `ease-in-out`, `ease-in-out-cubic`, `ease-in-out-quart` | | elements moving on screen from A to B, loops |
| `ease-in`, `ease-in-quad`, `ease-in-cubic` | | exits only (RM005 otherwise) |
| `linear` | native | constant loops (spinners, marquees); never movement that starts/stops (RM006) |
| `back`, `bounce`, `elastic`, `snappy`, `smooth`, `soft` | OpenMotion approximations | prefer a spring for overshoot |

Any `cubic-bezier(x1, y1, x2, y2)` string is accepted (x within 0–1).

## Springs

```json
{ "type": "spring", "response": 0.42, "dampingFraction": 0.86 }
```

Accepted forms (all normalised to `{stiffness, damping, mass, velocity}`):

- `response` (s) + `dampingFraction` — Apple/SwiftUI perceptual parameters. `response` ≈ the period of the undamped oscillation; `dampingFraction` 1 = no overshoot, < 1 = bounce.
- `duration` (s) + `bounce` (−1…1) — SwiftUI `.spring(duration:bounce:)`.
- `stiffness`, `damping`, `mass` — physical (OpenMotion compatible). `velocity` (normalised units/s) optional.

The runtime solves the damped harmonic oscillator analytically (under-, critically and over-damped cases), finds the settle time (within 0.1 % and at rest), and emits an exact CSS `linear()` curve (simplified with ≤ 0.15 % error) plus a cubic-bezier fallback under `@supports not (animation-timing-function: linear(0, 1))`. With `durationMs: "auto"` the duration is the settle time; a shorter duration truncates the spring (RM004).

`critique` returns a `springs` array per component: `dampingRatio`, `character` (bouncy/lively/smooth/sluggish), `settleMs`, `overshoot`.

| Feel | response | dampingFraction | Typical |
|---|---|---|---|
| snappy | 0.30 | 0.86 | toggles, press, direct manipulation |
| surface | 0.42 | 0.86 | sheets, shared-element, panels |
| smooth | 0.50 | 1.00 | large moves without overshoot |
| lively | 0.45 | 0.62 | small pops, badges |
| playful | 0.45 | 0.50 | celebrations only |

Large surfaces wobbling (damping ratio < 0.7) read as unstable (RM003 info). Feedback springs must settle quickly (RM003 when > 600ms).

## Why `linear()` instead of a bezier

A cubic-bezier cannot represent oscillation; OpenMotion maps every spring to one of two fixed beziers. `linear()` reproduces the solved curve, including overshoot (verified in a real browser: a 0.6→1 scale with response 0.5 / dampingFraction 0.55 peaks at the analytic 1.050). Support: Chrome/Edge 113+, Firefox 112+, Safari 17.2+; older engines get the fallback bezier.
