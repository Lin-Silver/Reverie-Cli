---
name: photo-to-3d
description: Rebuild a photographed subject as procedural Three.js code from one or more reference images. Use for photo to 3D, image to 3D model, picture to mesh, "make a 3D model of this photo", or turning a product shot, character, prop, vehicle, building, or room photo into a THREE.Group factory, a WebGL/react-three-fiber scene, or a Three.js asset assembled from primitives and shaders rather than photogrammetry, a point cloud, or a downloaded mesh.
---

# Photo to 3D

Reconstruct the subject **as code**, not as a scan. A reference image becomes a deterministic TypeScript factory that returns a `THREE.Group` assembled from Three.js primitives, lathe/extrude/tube geometry, and procedural shader materials. There is no photogrammetry step, no point cloud, and no imported mesh: every millimetre of the output exists because a pass decided it should.

Adapted from the img2threejs project (Apache-2.0; see [attribution.md](references/attribution.md)). Reverie keeps the same locked pass order and fail-closed review gates but drives them with Reverie's own tools instead of an external `python3 forge/` script farm, so the workflow behaves identically in a source checkout and in a packaged build.

## Before the first pass

1. Confirm the reference image path(s) and actually look at them through your vision input. With no image there is no ground truth — call `ask_clarification` rather than inventing a subject.
2. Classify the subject as **object** (product, prop, vehicle, furniture, building, terrain) or **character** (human, humanoid, creature, anything with a face or a skeleton). A character inserts the extra track in [character-track.md](references/character-track.md) after pass 3.
3. Fix the workspace layout and write it down. Default: the factory under `src/models/<subject>/`, the review harness and pass state under `.reverie/photo-to-3d/<subject>/`.
4. Create `state.json` before any geometry. Its contract is in [render-review.md](references/render-review.md); it is the only record of which passes are locked, so a later pass must never quietly rewrite an earlier pass's numbers.
5. Stand up the render harness once. A pass that cannot be rendered cannot be reviewed, and a pass that cannot be reviewed cannot be locked.

## Locked pass order

Run the passes in order and never skip forward. Each has an entry gate, a deliverable, and an exit gate; a pass that fails its exit gate is re-run, not waived. Per-pass gates are in [pass-pipeline.md](references/pass-pipeline.md).

1. **Blockout** — proportions and bounding volumes only. Grey boxes and cylinders, correct silhouette, correct world scale in metres.
2. **Structural** — the load-bearing parts: frame, chassis, trunk, walls, limb hierarchy. The group tree and every node name are settled here; later passes only fill it in.
3. **Form** — each part's real profile via `LatheGeometry`, `ExtrudeGeometry`, `TubeGeometry`, bevels, and displacement helpers. The silhouette must now match the reference at the review cameras.
4. **Material** — one `MeshPhysicalMaterial`/`MeshStandardMaterial` per part with measured base colour, roughness, metalness, clearcoat, and transmission. Colours are sampled from the reference, never recalled from memory. See [materials.md](references/materials.md).
5. **Surface** — procedural detail: shader-driven grain, weave, wear, panel lines, decals, normal and roughness variation. No bitmap textures unless the user supplied them.
6. **Lighting** — the rig the model is judged under: key/fill/rim or an environment, plus tone mapping and exposure. Lock the rig; later reviews must not be rescued by relighting.
7. **Interaction** — only when asked: animation clips, hover/click states, exposed parameters, react-three-fiber wiring.
8. **Optimization** — merge geometry, dispose duplicates, cap segment counts, and report draw calls and triangle count against the stated budget.

## Review every pass

A pass is finished only once a render exists and has been compared against the reference:

1. Serve the harness, then capture it with `browser_controler` — `browser_session_start(background=true, minimized=true, activate=false)` followed by `devtools_screenshot(full_page=true)` — and read `devtools_console` for shader and runtime errors.
2. Put the screenshot beside the reference and score this pass's criteria only. Do not grade pass 3 on its materials.
3. Record the verdict, the numeric scores, and the outstanding fixes in `state.json`.
4. **Fail closed.** Any unmet criterion, any console error, any blank or black render blocks the lock. Fix, re-render, re-review.
5. Only then mark the pass `locked` and move on.

The camera set and the scoring rubric are in [render-review.md](references/render-review.md).

## Hard rules

- Do not download, generate, or import a mesh, `.glb`, `.obj`, photogrammetry output, or an AI-generated 3D asset and present it as the result. The deliverable is readable code.
- Do not use `text_to_image` to fabricate a "reference". The user's photo is the only ground truth.
- Do not claim a visual match you have not screenshotted. Report what the render actually showed, including what is still wrong.
- Keep the model unit-correct: state the subject's real-world size in metres during pass 1 and honour it in every later pass.
- Never reopen a locked pass to paper over a later failure. If pass 1's proportions were wrong, say so, unlock it explicitly in `state.json`, and re-run every pass below it.
- Prefer parameters over buried literals so the factory stays re-tunable: `createSubject({ scale, colorway, detail })`.
- One subject per factory file. Build scenes by composing factories.

## Related surfaces

- `blender_modeling_workbench` when the user wants a Blender-authored mesh export instead of Three.js code.
- `reverie_engine` and `game_modeling_workbench` when the target is a Reverie-Gamer runtime asset rather than a web scene.
- `browser_controler` for every render, screenshot, and console check this skill performs.
