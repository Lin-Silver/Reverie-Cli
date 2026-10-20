"""Pinned MCP Apps 2026-01-26 / ext-apps 2.0.3, offline host profile."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict
from urllib.parse import unquote, urlsplit

MCP_APP_SDK_VERSION = "2.0.3"
MCP_APP_PROTOCOL_VERSION = "2026-01-26"
MCP_APP_MIME = "text/html;profile=mcp-app"


def normalize_tool_ui(tool: Dict[str, Any]) -> Dict[str, Any]:
    meta = tool.get("_meta") if isinstance(tool.get("_meta"), dict) else {}
    ui = meta.get("ui", {})
    if not isinstance(ui, dict):
        return {"visibility": []}
    visibility = ui.get("visibility", ["model", "app"])
    if not isinstance(visibility, list) or any(x not in ("model", "app") for x in visibility):
        visibility = []
    uri = ui.get("resourceUri", meta.get("openai/outputTemplate"))
    return {**ui, "resourceUri": uri if isinstance(uri, str) else None, "visibility": list(visibility)}


def _without_meta(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_meta(item) for key, item in value.items() if key != "_meta"}
    if isinstance(value, list):
        return [_without_meta(item) for item in value]
    return value


def public_mcp_result(result: Dict[str, Any]) -> Dict[str, Any]:
    # structuredContent is explicitly model-visible business data. Its keys are
    # not transport metadata; preserve the object exactly as the server returned.
    public = {key: result[key] for key in ("content", "structuredContent", "isError") if key in result}
    if "content" in public:
        public["content"] = _without_meta(public["content"])
    return public


def validate_ui_resource(result: Dict[str, Any], uri: str, binding: Dict[str, Any]) -> Dict[str, Any]:
    parsed = urlsplit(uri)
    if parsed.scheme != "ui" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MCP App resources require an exact ui:// URI.")
    decoded = unquote(parsed.path)
    if "\\" in decoded or ".." in decoded.split("/") or any(ord(c) < 32 for c in uri):
        raise ValueError("Invalid MCP App resource URI.")
    contents = result.get("contents", [])
    if not isinstance(contents, list) or len(contents) != 1 or not isinstance(contents[0], dict):
        raise ValueError("This profile requires one self-contained HTML resource.")
    entry = contents[0]
    mime = ";".join(part.strip().lower() for part in str(entry.get("mimeType", "")).split(";"))
    if entry.get("uri") != uri or mime != MCP_APP_MIME:
        raise ValueError("MCP App resource URI or MIME does not match the declared template.")
    html = entry.get("text")
    if not isinstance(html, str) or not html or len(html.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("MCP App HTML is missing or exceeds 2 MiB.")
    meta = entry.get("_meta", {})
    if not isinstance(meta, dict) or not isinstance(meta.get("ui", {}), dict):
        raise ValueError("Invalid UI resource metadata.")
    ui = meta.get("ui", {})
    csp = ui.get("csp", {})
    permissions = ui.get("permissions", {})
    if not isinstance(csp, dict) or not isinstance(permissions, dict):
        raise ValueError("Invalid UI CSP or permissions.")
    for key, domains in csp.items():
        if key not in {"connectDomains", "resourceDomains", "frameDomains", "baseUriDomains"} or not isinstance(domains, list) or domains:
            raise ValueError("Offline MCP Apps profile does not grant requested CSP origins.")
    if permissions or meta.get("openai/widgetCSP"):
        raise ValueError("Offline MCP Apps profile does not grant requested resource permissions or legacy CSP.")
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    source = {"kind": "mcp", **binding, "resource_uri": uri, "content_hash": content_hash,
              "requested_ui": ui, "granted_csp": {}, "granted_permissions": {}}
    source["cache_key"] = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"html": html, "source": source}


def publish_mcp_app(context: Dict[str, Any], metadata: Dict[str, Any], arguments: Dict[str, Any], response: Dict[str, Any], summary: str) -> Dict[str, Any]:
    """Persist private hydration before publishing only a model-safe reference."""
    from .tools.render_view import RenderViewTool
    runtime = context["mcp_runtime"]
    server = metadata["server_name"]
    identity = runtime.app_identity(server)
    resource = runtime.read_ui_resource(server, metadata["ui"]["resourceUri"], identity)
    allowed = {item["tool_name"]: item["name"] for item in runtime.get_app_tool_definitions() if item["server_name"] == server}
    resource["source"]["tool_bindings"] = dict(list(allowed.items())[:32])
    helper = RenderViewTool(context)
    owner = helper._identity()
    title = metadata.get("tool_name", "MCP App")[:120]
    # Summaries are public text, bounded independently from private hydration.
    while len(summary.encode("utf-8")) > 4096:
        summary = summary[:len(summary) // 2]
    store = helper._store()
    manifest = store.register_mcp_app(resource=resource, identity=owner, title=title, summary=summary,
                                      arguments=arguments, result=response.get("result", {}), callable_tools=allowed.values())
    reference = manifest.model_reference()
    helper._emit("view_ready", session_id=owner.session_id, turn_id=owner.turn_id, **reference)
    return {"session_id": owner.session_id, "turn_id": owner.turn_id, **reference}
