"""Live2D integration helpers for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, Optional

import yaml

from .config import discover_live2d_sdk


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _looks_like_asset_path(value: str) -> bool:
    text = str(value or "").strip()
    return "/" in text or "\\" in text or "." in Path(text).name


@dataclass
class Live2DModelDefinition:
    model_id: str
    model_json: str = ""
    motions: Dict[str, list[str]] = field(default_factory=dict)
    expressions: Dict[str, str] = field(default_factory=dict)
    textures: list[str] = field(default_factory=list)
    physics: str = ""
    pose: str = ""
    layout: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    idle_motion: str = "idle"
    motion_aliases: Dict[str, str] = field(default_factory=dict)
    default_expression: str = ""
    placeholder: bool = False

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Live2DModelDefinition":
        data = dict(payload or {})
        motions = data.get("motions") or {}
        aliases = data.get("motion_aliases") or data.get("aliases") or {}
        return cls(
            model_id=str(data.get("model_id") or data.get("id") or "model"),
            model_json=str(data.get("model_json") or data.get("model3_json") or ""),
            motions={
                str(key): [str(item) for item in (value or []) if str(item).strip()]
                for key, value in dict(motions).items()
            },
            expressions={str(key): str(value) for key, value in dict(data.get("expressions") or {}).items()},
            textures=[str(item) for item in (data.get("textures") or []) if str(item).strip()],
            physics=str(data.get("physics") or ""),
            pose=str(data.get("pose") or ""),
            layout=dict(data.get("layout") or {}),
            metadata=dict(data.get("metadata") or {}),
            idle_motion=str(data.get("idle_motion") or "idle"),
            motion_aliases={str(key): str(value) for key, value in dict(aliases).items() if str(key).strip()},
            default_expression=str(data.get("default_expression") or ""),
            placeholder=bool(data.get("placeholder", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_json": self.model_json,
            "motions": dict(self.motions),
            "expressions": dict(self.expressions),
            "textures": list(self.textures),
            "physics": self.physics,
            "pose": self.pose,
            "layout": dict(self.layout),
            "metadata": dict(self.metadata),
            "idle_motion": self.idle_motion,
            "motion_aliases": dict(self.motion_aliases),
            "default_expression": self.default_expression,
            "placeholder": self.placeholder,
        }


@dataclass
class Live2DManifest:
    enabled: bool = False
    renderer: str = "web"
    sdk_candidates: list[str] = field(default_factory=list)
    models: Dict[str, Live2DModelDefinition] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Live2DManifest":
        data = dict(payload or {})
        models: Dict[str, Live2DModelDefinition] = {}
        raw_models = data.get("models") or {}
        if isinstance(raw_models, list):
            for item in raw_models:
                if not isinstance(item, dict):
                    continue
                definition = Live2DModelDefinition.from_dict(item)
                models[definition.model_id] = definition
        elif isinstance(raw_models, dict):
            for model_id, item in raw_models.items():
                if not isinstance(item, dict):
                    continue
                definition = Live2DModelDefinition.from_dict({"model_id": model_id, **item})
                models[definition.model_id] = definition

        return cls(
            enabled=bool(data.get("enabled", False)),
            renderer=str(data.get("renderer") or "web"),
            sdk_candidates=[str(item) for item in (data.get("sdk_candidates") or []) if str(item).strip()],
            models=models,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "renderer": self.renderer,
            "sdk_candidates": list(self.sdk_candidates),
            "models": {key: value.to_dict() for key, value in self.models.items()},
        }


class Live2DManager:
    """Loads, validates, routes motions, and builds the Live2D browser bridge."""

    def __init__(self, project_root: str | Path, manifest_path: str | Path = "data/live2d/models.yaml") -> None:
        self.project_root = Path(project_root).resolve()
        self.manifest_path = self.project_root / manifest_path
        self._manifest: Optional[Live2DManifest] = None

    def load_manifest(self) -> Live2DManifest:
        if self._manifest is not None:
            return self._manifest
        if not self.manifest_path.exists():
            self._manifest = Live2DManifest()
            return self._manifest
        payload = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        self._manifest = Live2DManifest.from_dict(payload)
        return self._manifest

    def save_manifest(self) -> Path:
        manifest = self.load_manifest()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            yaml.safe_dump(manifest.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return self.manifest_path

    def _bundled_sdk_path(self) -> Optional[Path]:
        candidate = Path(__file__).resolve().parent / "vendor/live2d/live2dcubismcore.min.js"
        return candidate if candidate.exists() else None

    def discover_sdk(self, sdk_candidates: Optional[Iterable[str]] = None) -> Optional[Path]:
        manifest = self.load_manifest()
        candidates = list(sdk_candidates or manifest.sdk_candidates)
        discovered = discover_live2d_sdk(self.project_root, candidates)
        if discovered is not None:
            return discovered
        return self._bundled_sdk_path()

    def register_model(self, definition: Live2DModelDefinition | Dict[str, Any]) -> Live2DModelDefinition:
        model = definition if isinstance(definition, Live2DModelDefinition) else Live2DModelDefinition.from_dict(definition)
        manifest = self.load_manifest()
        manifest.models[model.model_id] = model
        manifest.enabled = True
        self.save_manifest()
        return model

    def resolve_model(self, model_id: str) -> Optional[Live2DModelDefinition]:
        return self.load_manifest().models.get(str(model_id).strip())

    def _resolve_asset_path(self, definition: Live2DModelDefinition, relative_path: str) -> Optional[Path]:
        text = str(relative_path or "").strip()
        if not text:
            return None
        path = Path(text)
        if path.is_absolute():
            return path

        candidates: list[Path] = []
        if definition.model_json:
            model_json = self.project_root / definition.model_json
            candidates.append((model_json.parent / path).resolve())
        candidates.append((self.project_root / path).resolve())

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else None

    def _load_model_json_payload(self, definition: Live2DModelDefinition) -> Dict[str, Any]:
        model_json_path = self._resolve_asset_path(definition, definition.model_json)
        if model_json_path is None or not model_json_path.exists():
            return {}
        try:
            return json.loads(model_json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def validate(self) -> list[str]:
        manifest = self.load_manifest()
        errors: list[str] = []
        placeholder_only = bool(manifest.models) and all(model.placeholder for model in manifest.models.values())
        if manifest.enabled and not placeholder_only and not self.discover_sdk():
            errors.append("Live2D enabled but live2dcubismcore.min.js was not found from configured sdk_candidates")

        for model_id, definition in manifest.models.items():
            if definition.placeholder:
                continue
            if not definition.model_json:
                errors.append(f"Live2D model '{model_id}' is missing model_json")
                continue

            model_json_path = self._resolve_asset_path(definition, definition.model_json)
            if model_json_path is None or not model_json_path.exists():
                errors.append(f"Live2D model '{model_id}' references missing model_json: {definition.model_json}")
                continue

            payload = self._load_model_json_payload(definition)
            if not payload:
                errors.append(f"Live2D model '{model_id}' contains unreadable model_json: {definition.model_json}")
                continue

            file_references = dict(payload.get("FileReferences") or {})
            moc_path = str(file_references.get("Moc") or "")
            if moc_path:
                resolved = self._resolve_asset_path(definition, moc_path)
                if resolved is None or not resolved.exists():
                    errors.append(f"Live2D model '{model_id}' references missing moc file: {moc_path}")

            declared_textures = list(definition.textures) or [str(item) for item in (file_references.get("Textures") or []) if str(item).strip()]
            if not declared_textures:
                errors.append(f"Live2D model '{model_id}' does not declare any textures")
            for texture_path in declared_textures:
                resolved = self._resolve_asset_path(definition, texture_path)
                if resolved is None or not resolved.exists():
                    errors.append(f"Live2D model '{model_id}' references missing texture: {texture_path}")

            physics_path = definition.physics or str(file_references.get("Physics") or "")
            if physics_path:
                resolved = self._resolve_asset_path(definition, physics_path)
                if resolved is None or not resolved.exists():
                    errors.append(f"Live2D model '{model_id}' references missing physics file: {physics_path}")

            pose_path = definition.pose or str(file_references.get("Pose") or "")
            if pose_path:
                resolved = self._resolve_asset_path(definition, pose_path)
                if resolved is None or not resolved.exists():
                    errors.append(f"Live2D model '{model_id}' references missing pose file: {pose_path}")

            file_motion_groups = dict(file_references.get("Motions") or {})
            for motion_name, clips in definition.motions.items():
                if not clips:
                    errors.append(f"Live2D model '{model_id}' motion '{motion_name}' does not declare any clips")
                    continue
                for clip in clips:
                    if _looks_like_asset_path(clip):
                        resolved = self._resolve_asset_path(definition, clip)
                        if resolved is None or not resolved.exists():
                            errors.append(f"Live2D model '{model_id}' motion '{motion_name}' references missing clip: {clip}")

            if definition.idle_motion and definition.idle_motion not in definition.motions:
                errors.append(f"Live2D model '{model_id}' idle_motion '{definition.idle_motion}' is not defined in motions")

            file_expressions = dict(file_references.get("Expressions") or {})
            for expression_name, expression_path in definition.expressions.items():
                if not expression_path:
                    errors.append(f"Live2D model '{model_id}' expression '{expression_name}' is empty")
                    continue
                if _looks_like_asset_path(expression_path):
                    resolved = self._resolve_asset_path(definition, expression_path)
                    if resolved is None or not resolved.exists():
                        errors.append(f"Live2D model '{model_id}' expression '{expression_name}' references missing file: {expression_path}")

        return errors

    def route_motion(self, model_id: str, motion: str, *, expression: str = "") -> Dict[str, Any]:
        requested_motion = str(motion or "").strip() or "idle"
        requested_expression = str(expression or "").strip()
        model = self.resolve_model(model_id)
        if model is None:
            return {
                "model_id": str(model_id),
                "model_present": False,
                "requested_motion": requested_motion,
                "resolved_motion": requested_motion,
                "motion_clips": [],
                "expression": requested_expression,
                "expression_path": requested_expression,
                "fallback_used": False,
                "available_motions": [],
            }

        available_motions = list(model.motions.keys())
        alias_map = {_normalize_key(key): value for key, value in model.motion_aliases.items()}
        canonical_lookup = {_normalize_key(key): key for key in available_motions}
        normalized_requested = _normalize_key(requested_motion)

        resolved_motion = canonical_lookup.get(normalized_requested) or canonical_lookup.get(_normalize_key(alias_map.get(normalized_requested, "")))
        fallback_used = False
        if resolved_motion is None:
            if model.idle_motion and model.idle_motion in model.motions:
                resolved_motion = model.idle_motion
                fallback_used = True
            elif "idle" in model.motions:
                resolved_motion = "idle"
                fallback_used = True
            elif available_motions:
                resolved_motion = available_motions[0]
                fallback_used = True
            else:
                resolved_motion = requested_motion

        motion_clips = list(model.motions.get(resolved_motion) or [])
        resolved_expression = requested_expression or model.default_expression
        expression_path = ""
        if resolved_expression:
            expression_key = model.expressions.get(resolved_expression)
            if expression_key:
                expression_path = expression_key
            elif _looks_like_asset_path(resolved_expression):
                expression_path = resolved_expression

        return {
            "model_id": str(model_id),
            "model_present": True,
            "requested_motion": requested_motion,
            "resolved_motion": resolved_motion,
            "motion_clips": motion_clips,
            "expression": resolved_expression,
            "expression_path": expression_path,
            "fallback_used": fallback_used,
            "available_motions": available_motions,
        }

    def compose_motion_event(
        self,
        model_id: str,
        motion: str,
        *,
        expression: str = "",
        source: str = "",
    ) -> Dict[str, Any]:
        routed = self.route_motion(model_id, motion, expression=expression)
        return {
            **routed,
            "motion": routed["resolved_motion"],
            "source": str(source or ""),
            "renderer": self.load_manifest().renderer,
        }

    def summary(self) -> Dict[str, Any]:
        manifest = self.load_manifest()
        sdk_path = self.discover_sdk()
        return {
            "enabled": manifest.enabled,
            "renderer": manifest.renderer,
            "model_count": len(manifest.models),
            "models": sorted(manifest.models.keys()),
            "sdk_found": sdk_path is not None,
            "sdk_path": str(sdk_path) if sdk_path else "",
            "validation_errors": self.validate(),
        }

    def build_runtime_bundle(self, output_path: str | Path, *, sdk_path: Optional[Path] = None) -> Path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest = self.load_manifest()
        sdk = sdk_path or self.discover_sdk()
        sdk_relative = "vendor/live2d/live2dcubismcore.min.js"
        models: Dict[str, Any] = {}

        for model_id, definition in manifest.models.items():
            model_json = self._resolve_asset_path(definition, definition.model_json) if definition.model_json else None
            textures = [
                str(self._relative_from(target.parent, self._resolve_asset_path(definition, texture_path)))
                for texture_path in definition.textures
                if self._resolve_asset_path(definition, texture_path) is not None
            ]
            models[model_id] = {
                "model_id": definition.model_id,
                "placeholder": definition.placeholder,
                "idle_motion": definition.idle_motion,
                "default_expression": definition.default_expression,
                "motion_aliases": dict(definition.motion_aliases),
                "motions": dict(definition.motions),
                "expressions": dict(definition.expressions),
                "layout": dict(definition.layout),
                "metadata": dict(definition.metadata),
                "model_json": str(self._relative_from(target.parent, model_json)) if model_json else "",
                "textures": textures,
            }

        payload = {
            "enabled": manifest.enabled,
            "renderer": manifest.renderer,
            "sdk_script": sdk_relative if sdk else "",
            "manifest_path": str(self._relative_from(target.parent, self.manifest_path)),
            "models": models,
            "validation_errors": self.validate(),
        }
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def _relative_from(self, base_dir: Path, path: Optional[Path]) -> str:
        if path is None:
            return ""
        return Path(os.path.relpath(path.resolve(), start=base_dir.resolve())).as_posix()

    def _copy_sdk_for_bridge(self, bridge_dir: Path, sdk_path: Optional[Path]) -> str:
        if sdk_path is None or not sdk_path.exists():
            return ""
        vendor_path = bridge_dir / "vendor/live2d/live2dcubismcore.min.js"
        vendor_path.parent.mkdir(parents=True, exist_ok=True)
        if vendor_path.resolve() != sdk_path.resolve():
            shutil.copyfile(sdk_path, vendor_path)
        return vendor_path.relative_to(bridge_dir).as_posix()

    def build_web_bridge(self, output_path: str | Path) -> Path:
        """Create a browser bridge that loads Cubism Core and exposes motion commands."""
        manifest = self.load_manifest()
        sdk_path = self.discover_sdk()
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        sdk_reference = self._copy_sdk_for_bridge(target.parent, sdk_path)
        runtime_bundle = self.build_runtime_bundle(target.with_suffix(".runtime.json"), sdk_path=sdk_path)
        runtime_reference = runtime_bundle.relative_to(target.parent).as_posix()
        sdk_script_tag = f'<script src="{sdk_reference}"></script>' if sdk_reference else ""

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Reverie Engine Live2D Bridge</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0d1420;
      --panel: rgba(16, 27, 42, 0.94);
      --border: #35506e;
      --accent: #72d7ff;
      --text: #dde9f6;
      --muted: #98adc2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(85, 154, 214, 0.18), transparent 40%),
        linear-gradient(180deg, #09111a, var(--bg));
      color: var(--text);
      min-height: 100vh;
    }}
    .shell {{
      width: min(1100px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 18px;
      grid-template-columns: 1.2fr 0.8fr;
    }}
    .panel {{
      border: 1px solid var(--border);
      border-radius: 18px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
      overflow: hidden;
    }}
    .panel header {{
      padding: 16px 20px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .panel header strong {{
      display: block;
      font-size: 17px;
    }}
    .panel header span {{
      color: var(--muted);
      font-size: 13px;
    }}
    #stage {{
      min-height: 440px;
      display: grid;
      place-items: center;
      background:
        linear-gradient(180deg, rgba(34, 58, 83, 0.4), rgba(7, 12, 19, 0.9)),
        radial-gradient(circle at center, rgba(114, 215, 255, 0.08), transparent 60%);
      position: relative;
    }}
    #stage canvas {{
      width: min(100%, 720px);
      aspect-ratio: 16 / 9;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      background: rgba(7, 12, 19, 0.6);
    }}
    #placeholder {{
      position: absolute;
      inset: auto 24px 24px 24px;
      padding: 14px 16px;
      border-radius: 14px;
      background: rgba(5, 12, 20, 0.82);
      color: var(--muted);
      font-size: 13px;
    }}
    .stack {{
      display: grid;
      gap: 18px;
    }}
    .status-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      padding: 18px 20px;
    }}
    .stat {{
      padding: 14px;
      border-radius: 14px;
      background: rgba(5, 12, 20, 0.72);
      border: 1px solid rgba(255, 255, 255, 0.06);
    }}
    .stat small {{
      display: block;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .stat strong {{
      color: var(--accent);
      word-break: break-word;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0 20px 18px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      color: #04131c;
      background: linear-gradient(135deg, #72d7ff, #9bf1cf);
      font-weight: 700;
    }}
    pre {{
      margin: 0;
      padding: 18px 20px 20px;
      white-space: pre-wrap;
      background: rgba(3, 11, 18, 0.65);
      color: #bed0e2;
      font-size: 12px;
      max-height: 320px;
      overflow: auto;
    }}
    @media (max-width: 900px) {{
      .shell {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <header>
        <strong>Reverie Engine Live2D Bridge</strong>
        <span>Renderer: {manifest.renderer}</span>
      </header>
      <div id="stage">
        <canvas id="live2d-canvas" width="1280" height="720"></canvas>
        <div id="placeholder">Bridge ready. Use <code>window.ReverieLive2DBridge.playMotion(...)</code> or post a <code>reverie-live2d-command</code> event.</div>
      </div>
    </section>
    <section class="stack">
      <section class="panel">
        <header>
          <strong>Runtime</strong>
          <span>SDK and manifest bootstrap state</span>
        </header>
        <div class="status-grid">
          <div class="stat"><small>Cubism Core</small><strong id="sdk-state">loading</strong></div>
          <div class="stat"><small>Selected Model</small><strong id="model-state">none</strong></div>
          <div class="stat"><small>Requested Motion</small><strong id="motion-state">idle</strong></div>
          <div class="stat"><small>Runtime Bundle</small><strong id="bundle-state">{runtime_reference}</strong></div>
        </div>
        <div class="toolbar">
          <button id="bootstrap-button" type="button">Bootstrap</button>
          <button id="idle-button" type="button">Play Idle</button>
        </div>
      </section>
      <section class="panel">
        <header>
          <strong>Status Log</strong>
          <span>Command routing and bridge telemetry</span>
        </header>
        <pre id="status">Preparing runtime bundle...</pre>
      </section>
    </section>
  </main>
  {sdk_script_tag}
  <script>
    const status = document.getElementById('status');
    const sdkState = document.getElementById('sdk-state');
    const modelState = document.getElementById('model-state');
    const motionState = document.getElementById('motion-state');
    const placeholder = document.getElementById('placeholder');
    const runtimeBundleUrl = {json.dumps(runtime_reference)};
    let runtimeBundle = null;
    let selectedModel = '';
    let selectedMotion = 'idle';

    function writeStatus(message, payload) {{
      const suffix = payload ? "\\n\\n" + JSON.stringify(payload, null, 2) : '';
      status.textContent = message + suffix;
    }}

    function updateHud() {{
      sdkState.textContent = window.Live2DCubismCore ? 'loaded' : 'missing';
      modelState.textContent = selectedModel || 'none';
      motionState.textContent = selectedMotion || 'idle';
    }}

    async function ensureRuntime() {{
      if (runtimeBundle) {{
        updateHud();
        return runtimeBundle;
      }}
      const response = await fetch(runtimeBundleUrl);
      runtimeBundle = await response.json();
      const modelIds = Object.keys(runtimeBundle.models || {{}});
      selectedModel = selectedModel || modelIds[0] || '';
      updateHud();
      writeStatus('Runtime bundle loaded.', runtimeBundle);
      return runtimeBundle;
    }}

    function resolveMotion(modelId, requestedMotion) {{
      const runtime = runtimeBundle || {{ models: {{}} }};
      const model = (runtime.models || {{}})[modelId] || null;
      if (!model) {{
        return {{ modelId, resolvedMotion: requestedMotion || 'idle', fallbackUsed: false, motionClips: [] }};
      }}
      const motions = model.motions || {{}};
      const aliases = model.motion_aliases || {{}};
      const normalize = (value) => String(value || '').trim().toLowerCase().replace(/[- ]/g, '_');
      const wanted = normalize(requestedMotion || 'idle');
      const available = Object.keys(motions);
      let resolved = available.find((entry) => normalize(entry) === wanted);
      if (!resolved && aliases[wanted]) {{
        resolved = available.find((entry) => normalize(entry) === normalize(aliases[wanted]));
      }}
      let fallbackUsed = false;
      if (!resolved) {{
        resolved = model.idle_motion || available[0] || requestedMotion || 'idle';
        fallbackUsed = normalize(resolved) !== wanted;
      }}
      return {{
        modelId,
        resolvedMotion: resolved,
        fallbackUsed,
        motionClips: motions[resolved] || [],
      }};
    }}

    async function bootstrap() {{
      await ensureRuntime();
      placeholder.textContent = window.Live2DCubismCore
        ? 'Cubism Core is loaded. ReverieLive2DBridge is ready to accept routed motion commands.'
        : 'Cubism Core script is missing. Bridge still works in dry-run mode for motion routing and validation.';
      updateHud();
      return window.ReverieLive2DBridge.status();
    }}

    window.ReverieLive2DBridge = {{
      async bootstrap() {{
        return bootstrap();
      }},
      async setModel(modelId) {{
        await ensureRuntime();
        selectedModel = String(modelId || '');
        updateHud();
        return this.status();
      }},
      async playMotion(modelId, motion, options = {{}}) {{
        await ensureRuntime();
        const targetModel = String(modelId || selectedModel || '');
        const route = resolveMotion(targetModel, motion);
        selectedModel = targetModel;
        selectedMotion = route.resolvedMotion || String(motion || 'idle');
        updateHud();
        const payload = {{
          type: 'motion',
          model_id: targetModel,
          requested_motion: String(motion || 'idle'),
          resolved_motion: route.resolvedMotion,
          expression: String(options.expression || ''),
          source: String(options.source || 'bridge'),
          fallback_used: Boolean(route.fallbackUsed),
          motion_clips: route.motionClips,
        }};
        placeholder.textContent = 'Motion routed for ' + (targetModel || 'unknown model') + ': ' + payload.resolved_motion;
        writeStatus('Motion command routed.', payload);
        window.dispatchEvent(new CustomEvent('reverie-live2d-motion', {{ detail: payload }}));
        return payload;
      }},
      async applyCommand(command) {{
        const payload = command || {{}};
        if (payload.type === 'set_model') {{
          return this.setModel(payload.model_id || '');
        }}
        return this.playMotion(payload.model_id || selectedModel || '', payload.motion || 'idle', payload);
      }},
      status() {{
        return {{
          renderer: runtimeBundle ? runtimeBundle.renderer : {json.dumps(manifest.renderer)},
          sdk_loaded: Boolean(window.Live2DCubismCore),
          selected_model: selectedModel,
          selected_motion: selectedMotion,
          validation_errors: runtimeBundle ? runtimeBundle.validation_errors : [],
        }};
      }},
    }};

    window.addEventListener('reverie-live2d-command', (event) => {{
      window.ReverieLive2DBridge.applyCommand(event.detail || {{}}).catch((error) => {{
        writeStatus('Failed to apply command.', {{ error: String(error) }});
      }});
    }});

    document.getElementById('bootstrap-button').addEventListener('click', () => {{
      bootstrap().catch((error) => writeStatus('Bootstrap failed.', {{ error: String(error) }}));
    }});
    document.getElementById('idle-button').addEventListener('click', () => {{
      window.ReverieLive2DBridge.playMotion(selectedModel, 'idle').catch((error) => {{
        writeStatus('Idle motion failed.', {{ error: String(error) }});
      }});
    }});

    bootstrap().catch((error) => writeStatus('Initial bootstrap failed.', {{ error: String(error) }}));
  </script>
</body>
</html>
"""
        target.write_text(html, encoding="utf-8")
        return target
