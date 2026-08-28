"""Token-efficient progressive discovery for executable-local RATS tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .base import BaseTool, ToolResult


_BASE_DESCRIPTION = (
    "Search the compact catalogs of enabled RATS provider services. "
    "Search reports matching native tools without spending their schemas; "
    "load discloses the full schemas, and those tools become directly callable on the next agent step."
)

# What the schema advertises when no service has answered yet. Each connected
# service publishes its own request limits and those win; see
# ``reverie.rats_contract`` for why the fallback is the shipped value rather
# than an absence.
_FALLBACK_DESCRIBE_LIMIT = 16
_FALLBACK_SEARCH_LIMIT = 16


class RatsCatalogTool(BaseTool):
    """Search compact catalogs and progressively load native provider schemas."""

    name = "rats_catalog"
    aliases = ("rats_tools", "reverie_engine_tools", "rtp_catalog")
    search_hint = "discover load inspect and call native RATS provider tools through RTP"
    tool_category = "orchestration"
    tool_tags = ("rats", "rtp", "discover", "tool")
    read_only = True
    concurrency_safe = False
    always_load = True

    # `description` and `parameters` are both properties below: the introduction
    # has to name whichever services are connected right now, and the request
    # bounds are whatever those services publish, neither of which is knowable
    # at class scope.

    def _limits(self) -> Dict[str, int]:
        """The request bounds every connected service can satisfy."""
        try:
            published = self._runtime().request_limits()
        except Exception:
            published = {}
        if not isinstance(published, dict):
            published = {}

        def bound(key: str, fallback: int) -> int:
            value = published.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return fallback
            return value

        return {
            "describe_tools": bound("describe_tools", _FALLBACK_DESCRIBE_LIMIT),
            "search_results": bound("search_results", _FALLBACK_SEARCH_LIMIT),
        }

    @property  # type: ignore[override]
    def parameters(self) -> Dict[str, Any]:  # noqa: D401 - dynamic per connected services
        """Bound the request the model may make by what the services accept."""
        limits = self._limits()
        describe_limit = limits["describe_tools"]
        search_limit = limits["search_results"]
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "search", "load"],
                    "description": "List compact entries, search for relevant tools, or load exact names.",
                },
                "query": {"type": "string", "description": "Task keywords for search."},
                "service_id": {"type": "string", "description": "Optional exact connected RATS service id."},
                "provider_id": {"type": "string", "description": "Optional exact allowlisted RATS provider id."},
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": describe_limit,
                    "description": "Exact native provider tool names for load.",
                },
                "load": {
                    "type": "boolean",
                    "default": False,
                    "description": "Search only: also disclose the full schema of every match that has one. Matches without a schema are returned under not_loaded and stay uncallable. Leave off and load the names you actually need.",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": search_limit,
                    "default": min(5, search_limit),
                },
            },
            "required": ["operation"],
        }

    def _runtime(self):
        runtime = self.context.get("rats_runtime")
        if runtime is None:
            raise RuntimeError("The RATS runtime is not available.")
        return runtime

    @staticmethod
    def _output(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _render_capability_card(cards: List[Dict[str, Any]]) -> str:
        """Render the always-visible introduction to what each service offers."""
        lines: List[str] = []
        for card in cards:
            categories = " ".join(
                f"{entry.get('name')}({entry.get('count')})"
                for entry in card.get("categories", [])
                if isinstance(entry, dict)
            )
            product = str(card.get("product") or card.get("providerId") or "RATS service")
            lines.append(
                f"- {product} ({card.get('providerId')}, {card.get('toolCount')} native tools, "
                f"{card.get('loadedCount')} loaded of {card.get('loadedLimit')} max): {categories}"
            )
        if not lines:
            return ""
        return "Connected now:\n" + "\n".join(lines)

    @property  # type: ignore[override]
    def description(self) -> str:  # noqa: D401 - dynamic per connected services
        """Introduce the connected native surface without disclosing its schemas."""
        try:
            cards = self._runtime().capability_card()
        except Exception:
            return _BASE_DESCRIPTION
        card_text = self._render_capability_card(cards)
        if not card_text:
            return _BASE_DESCRIPTION
        return f"{_BASE_DESCRIPTION}\n{card_text}"

    def _loaded_names(self, runtime) -> Dict[str, List[str]]:
        try:
            snapshot = runtime.loaded_definition_names()
        except Exception:
            return {}
        return snapshot if isinstance(snapshot, dict) else {}

    @staticmethod
    def _evicted_between(
        before: Dict[str, List[str]],
        after: Dict[str, List[str]],
    ) -> List[str]:
        """Report definitions the bounded working set dropped during this call."""
        evicted: List[str] = []
        for service_key, names in before.items():
            remaining = set(after.get(service_key, []))
            evicted.extend(name for name in names if name not in remaining)
        return sorted(dict.fromkeys(evicted))

    def execute(self, **kwargs) -> ToolResult:
        runtime = self._runtime()
        operation = str(kwargs.get("operation") or "").strip().lower()
        service_id = str(kwargs.get("service_id") or "").strip()
        provider_id = str(kwargs.get("provider_id") or "").strip()
        limits = self._limits()
        result_ceiling = limits["search_results"]
        before = self._loaded_names(runtime)
        try:
            if operation == "list":
                rows = runtime.compact_catalog()
                limit = min(result_ceiling, max(1, int(kwargs.get("max_results", 5) or 5)))
                payload = {"count": len(rows), "tools": rows[:limit], "truncated": len(rows) > limit}
            elif operation == "search":
                load = bool(kwargs.get("load", False))
                matches = runtime.search(
                    str(kwargs.get("query") or ""),
                    limit=min(result_ceiling, max(1, int(kwargs.get("max_results", 5) or 5))),
                    service_id=service_id,
                    provider_id=provider_id,
                    load=load,
                )
                payload = {"matches": matches}
                if load:
                    # Only echo what the runtime actually loaded. A match whose
                    # provider publishes no schema stays undisclosed, so naming it
                    # here would promise a call that cannot be made.
                    loaded = [str(item.get("name") or "") for item in matches if item.get("loaded")]
                    unloaded = [str(item.get("name") or "") for item in matches if not item.get("loaded")]
                    payload["loaded_for_next_step"] = loaded
                    if unloaded:
                        payload["not_loaded"] = unloaded
                        payload["next_step"] = (
                            "Those names did not become callable — this service disclosed no schema "
                            "for them. Only loaded_for_next_step is callable on the next step."
                            if loaded
                            else "This service disclosed no schema for any match, so nothing became "
                            "callable. Refine the query, or use operation='list' to see what it does publish."
                        )
                else:
                    payload["next_step"] = (
                        "Call rats_catalog with operation='load' and the names you need "
                        "to make them directly callable."
                    )
            elif operation == "load":
                names = kwargs.get("names") if isinstance(kwargs.get("names"), list) else []
                definitions = runtime.describe(service_id, names, provider_id=provider_id)
                loaded = [str(item.get("name") or "") for item in definitions]
                payload = {"loaded_for_next_step": loaded, "definitions": definitions}
                # A requested name can be missing from the answer two ways: the
                # provider publishes it without a schema, or it fell past the
                # request cap the service published. Either way, saying nothing
                # would leave the model believing it asked and received.
                requested = [str(name or "").strip() for name in names if str(name or "").strip()]
                loaded_set = set(loaded)
                unloaded = [name for name in dict.fromkeys(requested) if name not in loaded_set]
                if unloaded:
                    payload["not_loaded"] = unloaded
            else:
                return ToolResult.fail("RATS operation must be list, search, or load.")
        except Exception as exc:
            return ToolResult.fail(str(exc))
        evicted = self._evicted_between(before, self._loaded_names(runtime))
        if evicted:
            payload["evicted"] = evicted
        return ToolResult.ok(self._output(payload), data=payload if isinstance(payload, dict) else {"value": payload})


__all__ = ["RatsCatalogTool"]
