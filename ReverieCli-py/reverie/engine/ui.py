"""Control-style UI layout and gameplay binding for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .components import (
    ButtonComponent,
    ChoiceListComponent,
    DialogueBoxComponent,
    ProgressBarComponent,
    ResourceBarComponent,
    TowerBuildPanelComponent,
    UIControlComponent,
)
from .math3d import Vector2
from .scene import Node, SceneTree


@dataclass
class UIRect:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": round(float(self.x), 3),
            "y": round(float(self.y), 3),
            "width": round(float(self.width), 3),
            "height": round(float(self.height), 3),
        }


class UISystem:
    """Resolves layout and binds UI controls to gameplay state."""

    def __init__(self, scene_tree: SceneTree, *, gameplay: Any = None) -> None:
        self.scene_tree = scene_tree
        self.gameplay = gameplay
        self._rects: Dict[str, UIRect] = {}

    def update(self, viewport_size: Any, *, frame_index: int = 0) -> None:
        self._rects.clear()
        self._apply_gameplay_bindings(frame_index=frame_index)
        viewport = Vector2.from_any(viewport_size)
        root_rect = UIRect(0.0, 0.0, max(1.0, viewport.x), max(1.0, viewport.y))
        self._resolve_tree(self.scene_tree.root, root_rect)

    def get_rect(self, node: Node) -> Optional[UIRect]:
        return self._rects.get(node.node_path)

    def summary(self) -> Dict[str, Any]:
        return {
            "control_count": len(self._rects),
            "controls": sorted(self._rects.keys()),
        }

    def _localize(self, value: str, *, default: str = "", params: Optional[Dict[str, Any]] = None) -> str:
        manager = getattr(self.scene_tree, "localization_manager", None)
        if manager is None:
            return str(value or default)
        return manager.resolve_text(str(value or default), default=default, params=params)

    def _resolve_tree(self, node: Node, parent_rect: UIRect) -> None:
        control = node.get_component("UIControl")
        if isinstance(control, UIControlComponent):
            rect = self._resolve_control_rect(control, parent_rect)
            self._rects[node.node_path] = rect
            node.metadata["_ui_rect"] = rect.to_dict()
            node.metadata["_ui_visible"] = bool(control.visible)
            parent_for_children = rect
        else:
            parent_for_children = parent_rect
        for child in node.children:
            self._resolve_tree(child, parent_for_children)

    def _resolve_control_rect(self, control: UIControlComponent, parent_rect: UIRect) -> UIRect:
        min_size = Vector2.from_any(control.min_size)
        custom_size = Vector2.from_any(control.custom_size)
        left = parent_rect.x + parent_rect.width * float(control.anchor_left) + float(control.margin_left)
        top = parent_rect.y + parent_rect.height * float(control.anchor_top) + float(control.margin_top)

        if abs(float(control.anchor_right) - float(control.anchor_left)) > 0.00001:
            right = parent_rect.x + parent_rect.width * float(control.anchor_right) + float(control.margin_right)
            width = max(min_size.x, right - left)
        else:
            width = max(min_size.x, custom_size.x if custom_size.x > 0.0 else min_size.x)

        if abs(float(control.anchor_bottom) - float(control.anchor_top)) > 0.00001:
            bottom = parent_rect.y + parent_rect.height * float(control.anchor_bottom) + float(control.margin_bottom)
            height = max(min_size.y, bottom - top)
        else:
            height = max(min_size.y, custom_size.y if custom_size.y > 0.0 else min_size.y)

        return UIRect(left, top, width, height)

    def _apply_gameplay_bindings(self, *, frame_index: int) -> None:
        for node in self.scene_tree.iter_nodes():
            control = node.get_component("UIControl")
            if not isinstance(control, UIControlComponent):
                continue
            self._bind_dialogue_box(node, control)
            self._bind_choice_list(node, control)
            self._bind_resource_bar(node, control)
            self._bind_build_panel(node, control)
            self._bind_button(node)
            node.metadata["_ui_frame"] = frame_index

    def _bind_dialogue_box(self, node: Node, control: UIControlComponent) -> None:
        component = node.get_component("DialogueBox")
        if not isinstance(component, DialogueBoxComponent) or self.gameplay is None:
            return
        view = self.gameplay.get_active_dialogue_view() if hasattr(self.gameplay, "get_active_dialogue_view") else {}
        if not view or not view.get("conversation_id"):
            control.visible = False
            node.metadata["ui_dialogue"] = {
                "conversation_id": "",
                "speaker": "",
                "text": component.empty_text,
            }
            return
        control.visible = True
        node.metadata["ui_dialogue"] = {
            "conversation_id": str(view.get("conversation_id") or ""),
            "speaker": f"{component.speaker_prefix}{str(view.get('speaker') or '')}",
            "text": str(view.get("text") or component.empty_text),
            "node_id": str(view.get("node_id") or ""),
        }

    def _bind_choice_list(self, node: Node, control: UIControlComponent) -> None:
        component = node.get_component("ChoiceList")
        if not isinstance(component, ChoiceListComponent) or self.gameplay is None:
            return
        view = self.gameplay.get_active_dialogue_view() if hasattr(self.gameplay, "get_active_dialogue_view") else {}
        if not view or not view.get("conversation_id"):
            control.visible = False
            node.metadata["ui_choices"] = []
            return
        rendered = [
            {
                "index": int(choice.get("index", index)),
                "text": f"{component.choice_prefix}{str(choice.get('text') or '')}",
            }
            for index, choice in enumerate(list(view.get("choices") or [])[: max(1, int(component.max_visible_choices))])
        ]
        control.visible = len(rendered) > 0
        node.metadata["ui_choices"] = rendered

    def _bind_resource_bar(self, node: Node, control: UIControlComponent) -> None:
        component = node.get_component("ResourceBar")
        progress = node.get_component("ProgressBar")
        if not isinstance(component, ResourceBarComponent) or self.gameplay is None:
            return
        current_value = float(self.gameplay.state.resources.get(component.resource_id, 0))
        max_value = max(1.0, float(component.max_value))
        if isinstance(progress, ProgressBarComponent):
            progress.min_value = 0.0
            progress.max_value = max_value
            progress.value = current_value
            progress.label = self._localize(component.label or component.resource_id.title())
        node.metadata["ui_resource"] = {
            "resource_id": component.resource_id,
            "label": self._localize(component.label or component.resource_id.title()),
            "value": current_value,
            "max_value": max_value,
            "ratio": max(0.0, min(1.0, current_value / max_value)),
            "display_mode": component.display_mode,
        }
        control.visible = True

    def _bind_build_panel(self, node: Node, control: UIControlComponent) -> None:
        component = node.get_component("TowerBuildPanel")
        if not isinstance(component, TowerBuildPanelComponent) or self.gameplay is None:
            return
        blueprint_ids = list(component.blueprint_ids)
        if component.auto_populate or not blueprint_ids:
            blueprint_ids = sorted(self.gameplay.tower_blueprints.keys())
        options = []
        for tower_id in blueprint_ids:
            blueprint = dict(self.gameplay.tower_blueprints.get(tower_id) or {})
            if not blueprint:
                continue
            options.append(
                {
                    "tower_id": tower_id,
                    "cost": int(blueprint.get("cost", 0)),
                    "range": float(blueprint.get("range", 0.0)),
                    "damage": float(blueprint.get("damage", 0.0)),
                    "label": self._localize(str(blueprint.get("label") or tower_id.replace("_", " ").title())),
                }
            )
        node.metadata["ui_build_panel"] = {
            "title": self._localize(component.title),
            "options": options,
            "gold": int(self.gameplay.state.resources.get("gold", 0)),
        }
        control.visible = len(options) > 0

    def _bind_button(self, node: Node) -> None:
        button = node.get_component("Button")
        if not isinstance(button, ButtonComponent):
            return
        node.metadata["ui_button"] = {
            "text": self._localize(button.text),
            "action": button.action,
            "pressed": button.pressed,
            "disabled": button.disabled,
            "variant": button.variant,
        }
