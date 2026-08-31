# Attribution

This skill adapts the methodology of **img2threejs** — https://github.com/img2threejs/img2threejs — which is distributed under the Apache License 2.0.

What is taken: the "reconstruction by code, not photogrammetry" premise, the locked pass order (blockout → structural → form → material → surface → lighting → interaction → optimization), the fail-closed render-and-review gate between passes, and the character track's shape (landmarks → camera-pose solve → de-lighting → texture projection → skeleton and geodesic skinning → five-stage hair → chirality gates).

What is not taken: no upstream source code is bundled. img2threejs drives its passes through roughly ninety standard-library Python modules under `forge/`, invoked as `python3 forge/<stage>/<script>.py` against a `.img2threejs/state.json` file. Reverie ships as a frozen single-file build with no guaranteed external `python3` interpreter, so that script farm would work in a source checkout and silently fail in a packaged install. This skill therefore expresses the same pipeline as instructions executed with Reverie's own tools — `create_file` and `str_replace_editor` for the factory and the state file, `browser_controler` DevTools for rendering and screenshots, the model's own vision for the review — and keeps an equivalent `.reverie/photo-to-3d/<subject>/state.json` as the pass ledger.

Apache-2.0 requires attribution for derivative works, which this file provides; it does not require that this skill be Apache-2.0, since no upstream code is copied here. If upstream source is ever vendored into Reverie, add the upstream `LICENSE` and `NOTICE` alongside it.
