# Illustration to virtual avatar in Reverie

Inspect the user's actual illustration before choosing geometry, proportions,
face, hair, clothing, accessories, palette or expressions. Preserve identity
and silhouette. Keep the original input and author changes in the output
project. If no illustration is supplied, ask for it through the available
`userInput` tool before claiming a reference-faithful conversion.

## Shared Blender environment

Use `rc_blender_runtime_status` and, when needed, `rc_blender_ensure_runtime`.
Read the detected executable path and pass it as `blender_path` to
`blender_modeling_workbench`, or as `--blender` to this Skill's pipeline.
Blender stays in `.reverie/plugins/blender/runtime/`; its configuration,
add-ons and MCP checkout remain in the same plugin depot. Output `.blend`,
textures, `.glb`, renders and verification reports belong to the user's project.

## 2D virtual avatar for browser and OBS

For a Live2D-like browser/OBS avatar, use the maintained 2D pipeline. It keeps
the original portrait bytes, uses a deformable 2D mesh for head/body/hair motion,
and builds aligned eye/mouth masks for blinking, smile and speaking. The viewer
also accepts local microphone amplitude for mouth opening. A card's tilt or foil
controls do not demonstrate these character features.

1. Copy the actual transparent portrait to `<project>/assets/source.png`. Inspect
   its pixel dimensions and face at full resolution. Locate each eye center,
   ellipse radii, eye angle, mouth center and skin samples on the visible face.
   The coordinates are pixels from the top-left. Do not copy example coordinates
   without checking the supplied image.
2. Write `<project>/avatar-config.json` using `avatar-config.example.json` as the
   schema example. Set head/neck, body, feet and side-hair deformation bands for
   this portrait. Keep changes modest so the source silhouette and face remain
   recognizable. Expression masks are newly authored local face pixels and need
   visual checking against the original.
3. Run `scripts/run_avatar_pipeline.py --project <project> --blender <detected
   plugin executable>`. Blender's bundled Python and NumPy author the scene and
   masks; the host launcher uses Python's standard library. No npm installation
   is needed. Verify `avatar-build-verification.json`, open `avatar.blend` and
   confirm packed images, eight neutral controls and actual driven deformation.
4. Start `node <project>/web/server.mjs`, then open its printed local URL. Test
   each eye, mouth, smile, head directions, breathing, hair sway, the talking
   demo and microphone stop/reset. Compare actual rendered frames and view the
   face close-up. With 原画静态 selected, export at native dimensions and compare
   the PNG to the original, allowing normal browser color/alpha quantization.
   Also verify mobile controls, reduced motion and the Canvas2D fallback.
5. Use the same local URL with `?obs=1` in an OBS browser source. Set the browser
   source dimensions from `web/avatar.json`. The document and canvas are
   transparent and controls are hidden. Test the actual OBS preview against a
   colored background where OBS is available; a PNG alpha check alone does not
   verify OBS. In the normal browser window enable 同步到 OBS, then operate the
   controls or enable microphone mouth movement there. The local server relays
   only eight numeric pose parameters to transparent output windows; it never
   receives audio. Verify actual OBS expression changes and synchronized lips.
   Stopping synchronization or closing the controller restores independent
   output motion. Without synchronization, the OBS Interact window supports B
   to blink, S to smile, T for the talking demo, R to reset and Space to pause.
   Use a normal browser for microphone permission rather than depending on the
   embedded OBS browser's media-device support.
   Keep the controlling browser open and visible during live use. Browser
   background throttling or system sleep can reduce pose-update frequency;
   after three seconds without updates, OBS resumes independent motion.
6. Deliver `avatar.blend`, the complete `web/` folder, source/configuration,
   expression masks and a ZIP of the output project. The original artwork and
   generated avatar remain in that project, never in the text-only Skill bundle.

This route produces a browser/OBS 2D avatar package. If the user requests a
Cubism/VTube Studio model, use the Live2D plugin and an actual Cubism editor/export
workflow to produce and validate `.model3.json` with `.moc3`; this viewer's manifest
is `reverie.2d-avatar.v1` and is not a Cubism binary.

## 2.5D illustration avatar

Follow the Skill's registered transparent subject, background, effects, lineart
and typography workflow. Use distinct depth planes and modest parallax. The
card viewer supplies drag, tilt, zoom, reset, flip, mobile controls and
reduced-motion behavior. Deliver the editable `.blend`, geometry and working
viewer with the source layers. A layered avatar has limited viewpoint coverage;
describe it as 2.5D and show both tilt directions.

If the requested avatar needs blinking, mouth movement or limb motion, author
aligned eye/mouth variants and articulated body layers from the same reference,
then implement actual shape changes or layer transforms in Blender/Three.js.
Test each expression and animation in the destination viewer. Do not label a
card's tilt controls as face tracking, lip sync or skeletal animation. Live2D
is a separate destination: use the enabled Live2D plugin to inspect/validate
an actual `.model3.json` and Cubism model; PNG planes cannot replace `.moc3`.

## Fully rigged 3D humanoid avatar

1. Record the reference-specific proportions, face features, hair silhouette,
   clothing construction, accessories and material assignments. A single front
   view does not determine the hidden back/side; state those design assumptions
   and request another view when the choice materially changes the character.
2. Use `blender_modeling_workbench` with `action="generate_script"`,
   `preset="production_character_pipeline"`, `brief=<reference-specific brief>`,
   `model_name=<stable name>`, `blender_path=<plugin executable>` and the project's
   `output_dir`. Inspect and edit the generated bpy script against the actual
   reference before executing it. The procedural preset is an editable scaffold;
   a brief alone does not reconstruct the illustration or prove identity fidelity.
3. Author the actual head/body, hair, clothing and accessories, then retopologize,
   unwrap UVs and tune textures/materials against the reference. If an enabled
   image-to-3D model tool is available, use its actual output as a starting mesh
   and inspect it. Game Models manages model packages; a downloaded snapshot by
   itself is not an inference tool or an accepted avatar.
4. Build and weight a humanoid armature. Verify pelvis/spine/chest/neck/head,
   paired arms/hands and legs/feet, rest pose and naming. Test joint deformation
   in the pose-stress action; fix shoulder, elbow, hip, knee and neck artifacts.
   Use named facial shape keys with real vertex deformation for eye closure,
   smiles and mouth opening. Add the destination's required visemes and gaze
   targets, then inspect each in the rendered character.
   Create targets with `shape_key_add(..., from_mix=False)` and explicitly set
   each target's `value=0.0` before saving, exporting and rendering the neutral
   pose. Verify that the exported default morph weights are zero, then exercise
   each expression separately: a model that starts with both eyes closed and
   its mouth open can still pass checks that only count shape keys.
5. Run the edited script with `rc_blender_run_script` or the workbench's
   `action="run_script"`, passing the plugin executable. Use
   `rc_blender_inspect_scene` to check meshes, armature, shape keys, actions,
   material/image references and missing files. Run `action="audit_model"`
   on workbench outputs and resolve failed structural gates.
6. Deliver editable `.blend`, textures and a `.glb` with skinning, morph targets
   and animation clips. Reimport the GLB and test expressions/poses in the
   destination runtime. Render front, side and back plus close-up face views,
   and compare identity to the original illustration. Structural QA is evidence
   about the rig/export only; it cannot establish artistic fidelity.
7. For a requested `.vrm`, first inspect an actually installed VRM exporter and
   the destination's VRM version requirements. Map humanoid bones, expressions,
   spring bones and metadata, export, then validate/import in the target app.
   Install an exporter inside the plugin's existing add-on depot only when
   required. Never rename a GLB to `.vrm` or promise VRM from this Skill alone.

Report separately what was built, executed, rendered, visually compared, and
tested in the target runtime. A 2.5D card and a procedural humanoid candidate
are distinct deliverables; neither is proof of a finished reference conversion.
