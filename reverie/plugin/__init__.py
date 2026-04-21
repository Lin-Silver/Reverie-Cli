"""Plugin SDK depot and optional runtime-tool infrastructure for Reverie."""

from typing import TYPE_CHECKING

from .protocol import (
    RC_PROTOCOL_VERSION,
    RuntimePluginCommandSpec,
    RuntimePluginHandshake,
    build_runtime_tool_name,
    normalize_runtime_handshake,
)
from .runtime_manager import (
    DEFAULT_RUNTIME_PLUGIN_CATALOG,
    RuntimePluginManager,
    RuntimePluginRecord,
    RuntimePluginSnapshot,
    RuntimePluginSpec,
    RuntimePluginTemplateRecord,
)

if TYPE_CHECKING:
    from .dynamic_tool import RuntimePluginDynamicTool


def __getattr__(name: str):
    if name == "RuntimePluginDynamicTool":
        from .dynamic_tool import RuntimePluginDynamicTool

        return RuntimePluginDynamicTool
    raise AttributeError(name)


__all__ = [
    "RC_PROTOCOL_VERSION",
    "DEFAULT_RUNTIME_PLUGIN_CATALOG",
    "RuntimePluginCommandSpec",
    "RuntimePluginDynamicTool",
    "RuntimePluginHandshake",
    "RuntimePluginManager",
    "RuntimePluginRecord",
    "RuntimePluginSnapshot",
    "RuntimePluginSpec",
    "RuntimePluginTemplateRecord",
    "build_runtime_tool_name",
    "normalize_runtime_handshake",
]
