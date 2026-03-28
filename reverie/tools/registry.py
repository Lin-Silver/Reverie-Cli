"""Declarative tool registry for Reverie's built-in tool surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Type

from ..modes import normalize_mode
from .base import BaseTool
from .codebase_retrieval import CodebaseRetrievalTool
from .git_commit_retrieval import GitCommitRetrievalTool
from .str_replace_editor import StrReplaceEditorTool
from .file_ops import FileOpsTool
from .delete_file import DeleteFileTool
from .command_exec import CommandExecTool
from .web_search import WebSearchTool
from .task_manager import TaskManagerTool
from .context_management import ContextManagementTool
from .create_file import CreateFileTool
from .user_input import UserInputTool
from .clarification import ClarificationTool
from .text_to_image import TextToImageTool
from .ant_tools import TaskBoundaryTool, NotifyUserTool
from .novel_context_manager import NovelContextManagerTool
from .consistency_checker_tool import ConsistencyCheckerTool
from .plot_analyzer_tool import PlotAnalyzerTool
from .game_asset_manager import GameAssetManagerTool
from .game_balance_analyzer import GameBalanceAnalyzerTool
from .level_design_tool import LevelDesignTool
from .game_config_editor import GameConfigEditorTool
from .game_asset_packer import GameAssetPackerTool
from .game_gdd_manager import GameGDDManagerTool
from .story_design_tool import StoryDesignTool
from .game_math_simulator import GameMathSimulatorTool
from .game_stats_analyzer import GameStatsAnalyzerTool
from .game_design_orchestrator import GameDesignOrchestratorTool
from .game_project_scaffolder import GameProjectScaffolderTool
from .game_playtest_lab import GamePlaytestLabTool
from .game_modeling_workbench import GameModelingWorkbenchTool
from .atlas_delivery_orchestrator import AtlasDeliveryOrchestratorTool
from .reverie_engine import ReverieEngineTool
from .reverie_engine_lite import ReverieEngineLiteTool
from .vision_upload import VisionUploadTool
from .token_counter import TokenCounterTool
from .mode_switch import ModeSwitchTool
from .computer_control import ComputerControlTool


ToolClass = Type[BaseTool]
ModePredicate = Callable[[str], bool]


@dataclass(frozen=True)
class ToolRegistration:
    """One declarative tool registration entry."""

    tool_class: ToolClass
    include_modes: frozenset[str] = frozenset()
    exclude_modes: frozenset[str] = frozenset()
    expose_schema: bool = True
    predicate: Optional[ModePredicate] = None

    @property
    def name(self) -> str:
        """Return the tool's public name."""
        return str(getattr(self.tool_class, "name", self.tool_class.__name__))

    def enabled_in_mode(self, mode: object) -> bool:
        """Return whether the tool should be exposed for the supplied mode."""
        normalized_mode = normalize_mode(mode)
        if self.include_modes and normalized_mode not in self.include_modes:
            return False
        if normalized_mode in self.exclude_modes:
            return False
        if self.predicate is not None:
            return bool(self.predicate(normalized_mode))
        return True


_TOOL_REGISTRY: List[ToolRegistration] = []


def register_tool_class(
    tool_class: ToolClass,
    *,
    include_modes: Optional[Sequence[str]] = None,
    exclude_modes: Optional[Sequence[str]] = None,
    expose_schema: bool = True,
    predicate: Optional[ModePredicate] = None,
) -> None:
    """Register a built-in or extension tool class."""
    registration = ToolRegistration(
        tool_class=tool_class,
        include_modes=frozenset(normalize_mode(mode) for mode in (include_modes or ()) if str(mode or "").strip()),
        exclude_modes=frozenset(normalize_mode(mode) for mode in (exclude_modes or ()) if str(mode or "").strip()),
        expose_schema=bool(expose_schema),
        predicate=predicate,
    )

    for index, existing in enumerate(_TOOL_REGISTRY):
        if existing.name == registration.name:
            _TOOL_REGISTRY[index] = registration
            return

    _TOOL_REGISTRY.append(registration)


def get_tool_registrations(*, include_hidden: bool = True) -> List[ToolRegistration]:
    """Return registered tool metadata."""
    if include_hidden:
        return list(_TOOL_REGISTRY)
    return [registration for registration in _TOOL_REGISTRY if registration.expose_schema]


def get_registered_tool_classes(*, include_hidden: bool = True) -> List[ToolClass]:
    """Return registered tool classes in declaration order."""
    return [registration.tool_class for registration in get_tool_registrations(include_hidden=include_hidden)]


def get_tool_classes_for_mode(mode: object, *, include_hidden: bool = False) -> List[ToolClass]:
    """Return tool classes visible in the supplied mode."""
    normalized_mode = normalize_mode(mode)
    registrations = get_tool_registrations(include_hidden=include_hidden)
    return [
        registration.tool_class
        for registration in registrations
        if registration.enabled_in_mode(normalized_mode)
    ]


def is_tool_visible_in_mode(tool_name: str, mode: object) -> bool:
    """Return whether a tool should be advertised for a mode."""
    normalized_name = str(tool_name or "").strip()
    if not normalized_name:
        return False
    if normalized_name.startswith("mcp_"):
        return True

    normalized_mode = normalize_mode(mode)
    for registration in _TOOL_REGISTRY:
        if registration.name != normalized_name:
            continue
        return registration.expose_schema and registration.enabled_in_mode(normalized_mode)
    return True


def _register_builtin_tools() -> None:
    register_tool_class(CodebaseRetrievalTool)
    register_tool_class(GitCommitRetrievalTool)
    register_tool_class(StrReplaceEditorTool)
    register_tool_class(FileOpsTool)
    register_tool_class(DeleteFileTool)
    register_tool_class(CommandExecTool)
    register_tool_class(WebSearchTool)
    register_tool_class(TaskManagerTool, include_modes=("reverie", "reverie-gamer"))
    register_tool_class(ContextManagementTool, expose_schema=False)
    register_tool_class(CreateFileTool)
    register_tool_class(UserInputTool)
    register_tool_class(ClarificationTool, include_modes=("writer",))
    register_tool_class(TextToImageTool)
    register_tool_class(TaskBoundaryTool, include_modes=("reverie-ant",))
    register_tool_class(NotifyUserTool, include_modes=("reverie-ant",))
    register_tool_class(NovelContextManagerTool, include_modes=("writer",))
    register_tool_class(ConsistencyCheckerTool, include_modes=("writer",))
    register_tool_class(PlotAnalyzerTool, include_modes=("writer",))
    register_tool_class(GameAssetManagerTool, include_modes=("reverie-gamer",))
    register_tool_class(GameBalanceAnalyzerTool, include_modes=("reverie-gamer",))
    register_tool_class(LevelDesignTool, include_modes=("reverie-gamer",))
    register_tool_class(GameConfigEditorTool, include_modes=("reverie-gamer",))
    register_tool_class(GameAssetPackerTool, include_modes=("reverie-gamer",))
    register_tool_class(GameGDDManagerTool, include_modes=("reverie-gamer",))
    register_tool_class(StoryDesignTool, include_modes=("reverie-gamer",))
    register_tool_class(GameMathSimulatorTool, include_modes=("reverie-gamer",))
    register_tool_class(GameStatsAnalyzerTool, include_modes=("reverie-gamer",))
    register_tool_class(GameDesignOrchestratorTool, include_modes=("reverie-gamer",))
    register_tool_class(GameProjectScaffolderTool, include_modes=("reverie-gamer",))
    register_tool_class(GamePlaytestLabTool, include_modes=("reverie-gamer",))
    register_tool_class(GameModelingWorkbenchTool, include_modes=("reverie-gamer",))
    register_tool_class(AtlasDeliveryOrchestratorTool, include_modes=("reverie-atlas",))
    register_tool_class(ReverieEngineTool, include_modes=("reverie-gamer",))
    register_tool_class(ReverieEngineLiteTool, include_modes=("reverie-gamer",))
    register_tool_class(VisionUploadTool)
    register_tool_class(TokenCounterTool)
    register_tool_class(ModeSwitchTool, exclude_modes=("computer-controller",))
    register_tool_class(ComputerControlTool, include_modes=("computer-controller",))


_register_builtin_tools()


__all__ = [
    "ToolRegistration",
    "get_registered_tool_classes",
    "get_tool_classes_for_mode",
    "get_tool_registrations",
    "is_tool_visible_in_mode",
    "register_tool_class",
]
