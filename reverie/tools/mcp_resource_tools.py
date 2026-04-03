"""MCP resource discovery and reading tools."""

from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import base64
import mimetypes
import re
import time
from urllib.parse import urlparse

from .base import BaseTool, ToolResult


def _clip(value: Any, limit: int = 240) -> str:
    """Clip text to a predictable preview length."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 3)].rstrip()}..."


def _sanitize_filename(value: str) -> str:
    """Convert arbitrary names into a filesystem-safe stem."""
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return text or "resource"


class ListMcpResourcesTool(BaseTool):
    """Expose MCP resource discovery to the agent."""

    name = "list_mcp_resources"
    aliases = ("mcp_resources",)
    search_hint = "discover read-only mcp resources"
    tool_category = "mcp-resource"
    tool_tags = ("mcp", "resource", "discover", "dataset", "document")
    read_only = True
    concurrency_safe = True

    description = """List resources exposed by currently enabled MCP servers.

Use this tool when an MCP server may expose documents, datasets, prompts, or
other read-only resources that should be inspected before calling tools.
"""

    parameters = {
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "description": "Optional MCP server name to filter resources by",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum resources to include in the textual output (default: 20, max: 100)",
                "default": 20,
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Force rediscovery of MCP resources before returning results",
                "default": False,
            },
        },
        "required": [],
    }

    def _runtime(self):
        runtime = self.context.get("mcp_runtime")
        if runtime is None:
            raise RuntimeError("MCP runtime is not available in the current context.")
        return runtime

    def execute(self, **kwargs) -> ToolResult:
        max_results = kwargs.get("max_results", 20)
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            return ToolResult.fail("max_results must be an integer")
        max_results = max(1, min(max_results, 100))

        server = str(kwargs.get("server", "") or "").strip()
        force_refresh = bool(kwargs.get("force_refresh", False))

        try:
            resources = list(self._runtime().list_resources(server_name=server, force_refresh=force_refresh))
        except Exception as exc:
            return ToolResult.fail(str(exc))

        visible = resources[:max_results]
        heading = (
            f"MCP resources for server '{server}': {len(resources)} found"
            if server
            else f"MCP resources across enabled servers: {len(resources)} found"
        )
        lines = [heading]
        if not visible:
            lines.append("- No MCP resources were discovered.")
        else:
            lines.append("")
            for item in visible:
                description = _clip(item.get("description", ""), 160)
                mime_type = str(item.get("mimeType", "") or "").strip() or "(unspecified)"
                lines.append(
                    f"- {item.get('server')} :: {item.get('name')}\n"
                    f"  uri: {item.get('uri')}\n"
                    f"  mime: {mime_type}\n"
                    f"  description: {description or '(no description)'}"
                )
            if len(resources) > len(visible):
                lines.append("")
                lines.append(f"... {len(resources) - len(visible)} additional resources omitted.")

        return ToolResult.ok(
            "\n".join(lines),
            data={
                "server": server or None,
                "count": len(resources),
                "items": visible,
            },
        )


class ReadMcpResourceTool(BaseTool):
    """Read one MCP resource by server name and URI."""

    name = "read_mcp_resource"
    aliases = ("open_mcp_resource",)
    search_hint = "read one mcp resource by uri"
    tool_category = "mcp-resource"
    tool_tags = ("mcp", "resource", "read", "document", "dataset")
    read_only = True
    concurrency_safe = True

    description = """Read a specific MCP resource by server name and URI.

Text resources are returned inline. Binary resources can be persisted into the
project cache so the agent receives a safe local path instead of raw base64.
"""

    parameters = {
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "description": "MCP server name that provides the resource",
            },
            "uri": {
                "type": "string",
                "description": "Exact resource URI to read",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum text characters to include per text content block (default: 12000)",
                "default": 12000,
            },
            "save_binary": {
                "type": "boolean",
                "description": "Persist binary resource blobs into the project cache instead of omitting them",
                "default": True,
            },
        },
        "required": ["server", "uri"],
    }

    def _runtime(self):
        runtime = self.context.get("mcp_runtime")
        if runtime is None:
            raise RuntimeError("MCP runtime is not available in the current context.")
        return runtime

    def _resource_cache_dir(self) -> Path:
        root = self.context.get("project_data_dir")
        base_dir = Path(root) if root else self.get_project_root() / ".reverie"
        cache_dir = base_dir / "mcp_resources"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _persist_binary_blob(self, uri: str, mime_type: str, blob_value: str) -> Path:
        parsed = urlparse(str(uri or "").strip())
        stem_source = Path(parsed.path).name or parsed.netloc or parsed.scheme or "resource"
        stem = _sanitize_filename(stem_source)
        extension = mimetypes.guess_extension(str(mime_type or "").split(";", 1)[0].strip().lower()) or ".bin"
        target = self._resource_cache_dir() / f"{stem}-{int(time.time() * 1000)}{extension}"
        target.write_bytes(base64.b64decode(blob_value))
        return target

    def execute(self, **kwargs) -> ToolResult:
        server = str(kwargs.get("server", "") or "").strip()
        uri = str(kwargs.get("uri", "") or "").strip()
        save_binary = bool(kwargs.get("save_binary", True))
        max_chars = kwargs.get("max_chars", 12000)

        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            return ToolResult.fail("max_chars must be an integer")
        max_chars = max(200, min(max_chars, 100_000))

        try:
            payload = self._runtime().read_resource(server_name=server, uri=uri)
        except Exception as exc:
            return ToolResult.fail(str(exc))

        contents = payload.get("contents", []) if isinstance(payload, dict) else []
        if not isinstance(contents, list):
            contents = []

        rendered: List[str] = [f"MCP resource '{uri}' from server '{server}'"]
        normalized_items: List[Dict[str, Any]] = []

        if not contents:
            rendered.append("- The server returned no content blocks for this resource.")
            return ToolResult.ok("\n".join(rendered), data={"server": server, "uri": uri, "contents": []})

        for index, item in enumerate(contents, start=1):
            entry = item if isinstance(item, dict) else {}
            entry_uri = str(entry.get("uri", uri) or uri).strip()
            mime_type = str(entry.get("mimeType", "") or "").strip()

            if isinstance(entry.get("text"), str):
                text_value = entry.get("text", "")
                truncated = False
                if len(text_value) > max_chars:
                    text_value = f"{text_value[: max_chars - 3].rstrip()}..."
                    truncated = True
                rendered.extend(
                    [
                        "",
                        f"[content {index}] text ({mime_type or 'text/plain'})",
                        text_value or "(empty text block)",
                    ]
                )
                if truncated:
                    rendered.append(f"[content {index} truncated to {max_chars} characters]")
                normalized_items.append(
                    {
                        "uri": entry_uri,
                        "mimeType": mime_type or None,
                        "text": text_value,
                        "truncated": truncated,
                    }
                )
                continue

            blob_value = str(entry.get("blob", "") or "").strip()
            if blob_value and save_binary:
                try:
                    saved_path = self._persist_binary_blob(entry_uri, mime_type, blob_value)
                except Exception as exc:
                    rendered.extend(
                        [
                            "",
                            f"[content {index}] binary ({mime_type or 'application/octet-stream'})",
                            f"Failed to persist binary content: {exc}",
                        ]
                    )
                    normalized_items.append(
                        {
                            "uri": entry_uri,
                            "mimeType": mime_type or None,
                            "error": str(exc),
                        }
                    )
                    continue

                rendered.extend(
                    [
                        "",
                        f"[content {index}] binary ({mime_type or 'application/octet-stream'})",
                        f"Saved to: {saved_path}",
                    ]
                )
                normalized_items.append(
                    {
                        "uri": entry_uri,
                        "mimeType": mime_type or None,
                        "saved_to": str(saved_path),
                    }
                )
                continue

            rendered.extend(
                [
                    "",
                    f"[content {index}] binary ({mime_type or 'application/octet-stream'})",
                    "Binary content omitted. Re-run with save_binary=true to persist it into the project cache.",
                ]
            )
            normalized_items.append(
                {
                    "uri": entry_uri,
                    "mimeType": mime_type or None,
                    "omitted": True,
                }
            )

        return ToolResult.ok(
            "\n".join(rendered),
            data={
                "server": server,
                "uri": uri,
                "contents": normalized_items,
            },
        )
