# Blender Skill and browser/OBS avatar verification

Validated on Windows x64 on 2026-11-06. The accepted output is a browser/OBS 2D
portrait avatar with an editable Blender scene. Further 3D reconstruction testing
was stopped at the user's request.

The Blender plugin automatically registers the pinned RuiC Skill when enabled
and trusted. Persistent scripts, templates and references stay under
`.reverie/plugins/blender/skills/ruic-card-skill/`. Blender 5.1.1 keeps the existing
`.reverie/plugins/blender/runtime/` deployment location.

The maintained 2D workflow copies the original transparent portrait unchanged,
builds a 48 by 72 deform grid and packed expression images in `avatar.blend`, and
delivers an offline browser viewer. Its eight controls cover head directions,
breathing, hair sway, each eyelid, mouth opening and smile. A loopback pose relay
lets normal browser controls and local microphone amplitude drive an OBS browser
source. Only numeric pose values reach the server; audio stays in the browser.

## Verification evidence

- Focused integration suite: **11 passed**, with the 3D and card build cases
  explicitly deselected. This includes a real Blender 2D build, packed-image
  reopening, driven deformation, microphone cancellation and synchronization
  lifecycle regressions.
- Skill resources and runtime plugin regressions: **69 passed, 1 skipped**.
- Real Chromium verification of a supplied 1086 by 1448 transparent portrait:
  **45 checks passed**. Controls changed actual image pixels; neutral rendering
  had a maximum interior RGB error of 1 and maximum alpha error of 1. Tests also
  exercised reset, PNG export, mobile layout, reduced motion, genuine Canvas2D
  fallback and browser-to-output microphone synchronization with generated tone
  audio.
- Native portable OBS 33.0.1 verification: **19 checks passed**. Its official
  screenshot API captured real browser-source frames. All eight controls,
  synchronized synthetic-audio lips, reset, transparent edges and compositing
  over a colored background were verified. OBS was neither recording nor
  streaming, and the isolated collection had no audio-capture inputs. Source
  snapshots were compared in the same premultiplied color representation;
  actual opaque scene compositing was checked separately.
- The actual frozen Reverie SDK discovered all four official EXEs with a fresh
  application root, protocol cache and temporary directory. All four reported
  ready/supported. All **37** bundled Skill text resources matched the source
  after the one-file extraction process ended. The Skill ZIP contained no
  raster artwork, models, credentials or dependencies.

The reference portrait, generated avatar, screenshots, synthetic audio and
portable test applications remain local. Public tests use generated fixtures.

## Reproduction

Run the focused suites from the repository root with the Python source on
`PYTHONPATH`:

```powershell
python -m pytest ReverieCli-py/tests/test_blender_skill_integration.py -k 'not rigged_avatar and not card_skill_builds' -q
python -m pytest ReverieCli-py/tests/test_skill_resources.py ReverieCli-py/tests/test_skill_packaging.py ReverieCli-py/tests/test_skill_modes.py ReverieCli-py/tests/test_skill_pinning.py ReverieCli-py/tests/test_skill_shadowing.py ReverieCli-py/tests/test_runtime_plugins.py -q
```

For a real portrait, inspect the eyes and mouth, write `avatar-config.json`, run
`scripts/run_avatar_pipeline.py` with the plugin's detected Blender executable,
and start the generated `web/server.mjs`. Add its `?obs=1` URL as an OBS browser
source with the dimensions from `avatar.json`. In the regular browser enable
**同步到 OBS**, then use its controls or microphone permission.

This single-image workflow uses modest 2D deformation and newly authored local
expression masks. It has limited head-angle coverage and does not reconstruct
hidden anatomy. Keep the controlling browser visible for live use: background
throttling and system sleep can reduce update frequency. After three seconds
without pose updates, the output restores independent movement.

## Official plugin packages

The release workflow builds Blender **0.6.0**, Game Models **0.2.1**, Ren'Py
**0.2.1**, and Live2D **0.2.1**. It preserves upstream application runtime
versions, verifies the Blender archive SHA-256, handshakes each executable and
publishes four EXEs plus their version/hash/size manifest. Executables are
uploaded before the manifest; unrelated existing assets are retained.
