"""Read-only runtime media generation capability discovery tool."""

from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult
from ..media_capabilities import build_media_capabilities, render_runtime_media_capabilities_digest


class MediaGenerationCapabilitiesTool(BaseTool):
    """Report current TTI/TTV model, provider, readiness, and parameter capabilities."""

    name = "media_generation_capabilities"
    aliases = ("media_capabilities",)
    search_hint = "inspect runtime image video generation capabilities models parameters"
    tool_category = "media-generation"
    tool_tags = ("media", "image", "video", "capabilities", "models")
    read_only = True
    concurrency_safe = True

    description = """Read current runtime media generation capabilities without generating files.

Returns active image/video sources, default models, configured model counts, API-key/local-model readiness,
provider model profiles, parameter constraints, and output capabilities. Use before selecting non-default
media models or provider-specific generation parameters."""

    parameters = {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "enum": ["summary", "full"],
                "description": "summary returns the short digest; full returns source/model/profile details.",
                "default": "full",
            },
            "modality": {
                "type": "string",
                "enum": ["all", "image", "video"],
                "description": "Optional modality filter.",
                "default": "all",
            },
        },
        "required": [],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        capabilities = build_media_capabilities(
            config_manager=self.context.get("config_manager"),
            config=self.context.get("config"),
            project_root=self.get_project_root(),
        )
        modality = str(kwargs.get("modality", "all") or "all").strip().lower()
        detail = str(kwargs.get("detail", "full") or "full").strip().lower()
        if modality in {"image", "video"}:
            data = {modality: capabilities.get(modality, {})}
        else:
            data = capabilities
        if detail == "summary":
            return ToolResult.ok(render_runtime_media_capabilities_digest(capabilities), data)

        lines = [render_runtime_media_capabilities_digest(capabilities), "", "Detailed runtime media capabilities:"]
        for key in ("image", "video"):
            if key not in data:
                continue
            item = data[key]
            lines.append(
                f"- {key}: active_source={item.get('active_source')}; default_model={item.get('default_model') or '(none)'}; "
                f"configured_count={item.get('configured_count', 0)}"
            )
            sources = item.get("sources", {}) if isinstance(item.get("sources"), dict) else {}
            for source_name, source_data in sources.items():
                model_count = len(source_data.get("models", []) or [])
                readiness = []
                if "api_key_available" in source_data:
                    readiness.append(f"api_key={'yes' if source_data.get('api_key_available') else 'no'}")
                if "local_models_exist" in source_data:
                    readiness.append(f"local_files={source_data.get('local_models_exist')}/{source_data.get('configured_count', 0)}")
                lines.append(
                    f"  - {source_name}: enabled={'yes' if source_data.get('enabled') else 'no'}; "
                    f"default={source_data.get('default_model') or '(none)'}; models={model_count}"
                    + (f"; {'; '.join(readiness)}" if readiness else "")
                )
        return ToolResult.ok("\n".join(lines), data)

