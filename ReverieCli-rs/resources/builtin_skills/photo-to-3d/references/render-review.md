# Render and review

Nothing is locked on inspection of the source. Every pass is judged from a render.

## Harness

Create it once, at `.reverie/photo-to-3d/<subject>/`:

- `index.html` — an importmap or bundled page that imports the factory, adds it to a scene, and exposes `window.__reviewCamera(name)` to jump between the review cameras.
- `review.ts` (or inline module) — scene, renderer, the pass-6 rig once it exists, and a placeholder rig before that: one `HemisphereLight` plus one `DirectionalLight`, so early passes are readable without prejudging pass 6.
- Serve it however the project already serves static files (`npm run dev`, `python -m http.server`, an existing Vite server). Do not invent a new build system for the harness.

## Capture loop

```
browser_session_start(url=<harness url>, background=true, minimized=true, activate=false)
devtools_eval(expression="window.__reviewCamera('front')")
devtools_screenshot(full_page=true)
devtools_console()
```

Repeat the eval/screenshot pair per camera. Close the session with `browser_session_close` when the pass is done so stale profiles do not pile up.

A blank, black, or single-flat-colour render is a failure, not a subtle mismatch. Check `devtools_console` first: a shader compile error, a missing import, or a NaN transform is the usual cause.

## Review cameras

Fixed for the whole job so renders are comparable across passes:

| name | position | purpose |
| --- | --- | --- |
| `front` | on the reference's own axis | direct comparison with the photo |
| `three-quarter` | 35° off front, slightly above | the shape-reading view |
| `side` | 90° off front | depth and profile |
| `top` | above, looking down | footprint and layout |

Add `detail` cameras for a specific area when a pass needs them, but never replace the four.

## Scoring

Score each criterion of the current pass 0–5 and require ≥4 on every one to lock:

- 5 — indistinguishable from the reference for this pass's concern.
- 4 — a difference exists but would not be noticed side by side.
- 3 — noticeable side by side. **Blocks the lock.**
- 2 or below — wrong, not merely imprecise. **Blocks the lock.**

Never average away a 2. One failing criterion fails the pass.

## `state.json`

The whole record of the job. Write it with `create_file`/`str_replace_editor`; it needs no bespoke tooling.

```json
{
  "schema": "reverie.photo-to-3d/1",
  "subject": "espresso-grinder",
  "kind": "object",
  "references": ["assets/refs/grinder-front.jpg"],
  "real_size_m": { "x": 0.14, "y": 0.36, "z": 0.18 },
  "factory": "src/models/espresso-grinder/index.ts",
  "harness": ".reverie/photo-to-3d/espresso-grinder/index.html",
  "budget": { "draw_calls": 24, "triangles": 120000 },
  "cameras": ["front", "three-quarter", "side", "top"],
  "passes": [
    {
      "id": 1,
      "name": "blockout",
      "status": "locked",
      "scores": { "silhouette": 5, "proportion": 4, "scale": 5 },
      "renders": [".reverie/photo-to-3d/espresso-grinder/renders/p1-front.png"],
      "notes": "Hopper taper deferred to pass 3.",
      "locked_at": "2026-08-30T11:04:00Z"
    }
  ],
  "materials": { "body": "#2b2b2e", "hopper": "#d8d5cf" },
  "open_issues": []
}
```

Rules: `status` is one of `pending`, `in_progress`, `review`, `locked`. A pass with `locked` and no `renders` entry is invalid — that combination means a lock was claimed without evidence. `open_issues` must be empty before the job is reported complete, or the remaining entries must be handed to the user explicitly.

## Reporting

When the run finishes, tell the user: the factory path, the locked pass list, the final scores, the triangle and draw-call counts, and every open issue. Attach or reference the final renders. Do not describe a resemblance the screenshots do not show.
