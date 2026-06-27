"""Gameplay runtime systems for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import re

from .components import (
    ColliderComponent,
    DialogueComponent,
    HealthComponent,
    ImageComponent,
    Live2DComponent,
    NavigationAgentComponent,
    ScriptBehaviourComponent,
    TowerDefenseComponent,
    UIControlComponent,
)
from .live2d import Live2DManager
from .localization import LocalizationManager
from .math3d import Vector3
from .navigation import NavigationServer
from .scene import Node, SceneTree


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _string_list(values: Any) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        return [str(item).strip() for item in values if str(item).strip()]
    if isinstance(values, str) and values.strip():
        return [values.strip()]
    return []


@dataclass
class DialogueSession:
    conversation_id: str
    current_node_id: str
    source: str = ""
    speaker: str = ""
    history: list[str] = field(default_factory=list)
    completed: bool = False


@dataclass
class ActiveWave:
    wave_id: str
    started_frame: int
    pending_entries: list[Dict[str, Any]] = field(default_factory=list)
    spawned_nodes: set[str] = field(default_factory=set)
    reward_resources: Dict[str, int] = field(default_factory=dict)
    next_wave_id: str = ""
    completed: bool = False


@dataclass
class EngineWorldState:
    flags: Dict[str, bool] = field(default_factory=dict)
    counters: Dict[str, float] = field(default_factory=dict)
    resources: Dict[str, int] = field(default_factory=dict)
    inventory: Dict[str, int] = field(default_factory=dict)
    quests: Dict[str, str] = field(default_factory=dict)
    active_dialogue: Optional[DialogueSession] = None
    active_waves: Dict[str, ActiveWave] = field(default_factory=dict)
    cooldowns: Dict[str, int] = field(default_factory=dict)
    live2d_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    notes: Dict[str, Any] = field(default_factory=dict)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.flags[str(name)] = bool(value)

    def has_flag(self, name: str) -> bool:
        return bool(self.flags.get(str(name), False))

    def add_counter(self, name: str, amount: float = 1.0) -> None:
        key = str(name)
        self.counters[key] = self.counters.get(key, 0.0) + float(amount)

    def add_resource(self, name: str, amount: int) -> None:
        key = str(name)
        self.resources[key] = self.resources.get(key, 0) + int(amount)

    def add_inventory(self, item_id: str, amount: int = 1) -> None:
        key = str(item_id)
        self.inventory[key] = self.inventory.get(key, 0) + int(amount)

    def summary(self) -> Dict[str, Any]:
        return {
            "flags": {key: value for key, value in self.flags.items() if value},
            "counters": dict(self.counters),
            "resources": dict(self.resources),
            "inventory": dict(self.inventory),
            "quests": dict(self.quests),
            "notes": dict(self.notes),
            "active_dialogue": self.active_dialogue.conversation_id if self.active_dialogue else "",
            "active_waves": sorted(self.active_waves.keys()),
            "live2d_models": sorted(self.live2d_state.keys()),
        }


class GameplayDirector:
    """Coordinates data-driven gameplay systems, dialogue, and TD logic."""

    def __init__(
        self,
        scene_tree: SceneTree,
        resource_manager: Any,
        telemetry: Any,
        *,
        config: Optional[Dict[str, Any]] = None,
        live2d: Optional[Live2DManager] = None,
        localization: Optional[LocalizationManager] = None,
        audio_manager: Any = None,
    ) -> None:
        self.scene_tree = scene_tree
        self.resource_manager = resource_manager
        self.telemetry = telemetry
        self.config = dict(config or {})
        self.live2d = live2d or Live2DManager(resource_manager.project_root)
        self.localization = localization
        self.audio_manager = audio_manager
        self.state = EngineWorldState()
        self.dialogues: Dict[str, Dict[str, Any]] = {}
        self.quests: Dict[str, Dict[str, Any]] = {}
        self.paths: Dict[str, list[list[float]]] = {}
        self.navigation = NavigationServer()
        self.tower_blueprints: Dict[str, Dict[str, Any]] = {}
        self.waves: Dict[str, Dict[str, Any]] = {}
        self.economy: Dict[str, Any] = {}
        self._consumed_triggers: set[str] = set()
        self._registered_live2d: set[str] = set()
        self._autostarted_waves: set[str] = set()
        self._content_loaded = False
        self._bootstrapped = False

    @property
    def genre(self) -> str:
        project = dict(self.config.get("project") or {})
        runtime = dict(self.config.get("runtime") or {})
        return str(project.get("genre") or runtime.get("genre") or self.scene_tree.root.metadata.get("genre") or "sandbox")

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self._ensure_content_loaded()
        autostart_conversation = str(self.scene_tree.root.metadata.get("autostart_conversation") or "").strip()
        if autostart_conversation:
            self.start_dialogue(autostart_conversation, source="scene_autostart")

        autostart_wave = str(self.scene_tree.root.metadata.get("autostart_wave") or "").strip()
        if autostart_wave:
            if self.start_wave(autostart_wave, frame_index=0):
                self._autostarted_waves.add(autostart_wave)

        self.telemetry.log_event(
            "engine_bootstrap",
            genre=self.genre,
            dimension=self.scene_tree.root.metadata.get("dimension", ""),
            live2d_enabled=self.live2d.summary()["enabled"],
        )
        self._bootstrapped = True

    def _ensure_content_loaded(self) -> None:
        if self._content_loaded:
            return
        self._load_content_tables()
        self._apply_economy_defaults()
        self._register_live2d_nodes()
        self._content_loaded = True

    def _load_content_tables(self) -> None:
        self.navigation.clear()
        self.paths.clear()
        bundle = self.resource_manager.load_content_bundle()
        for payload in bundle.values():
            if not isinstance(payload, dict):
                continue
            if isinstance(payload.get("conversations"), dict):
                self.dialogues.update(dict(payload["conversations"]))
            if isinstance(payload.get("quests"), dict):
                self.quests.update(dict(payload["quests"]))
            elif isinstance(payload.get("quests"), list):
                for item in payload["quests"]:
                    if isinstance(item, dict) and str(item.get("id", "")).strip():
                        self.quests[str(item["id"])] = dict(item)
            self.navigation.load_payload(payload)
            if isinstance(payload.get("waves"), dict):
                self.waves.update(dict(payload["waves"]))
            if isinstance(payload.get("towers"), dict):
                self.tower_blueprints.update(dict(payload["towers"]))
            if isinstance(payload.get("economy"), dict):
                self.economy.update(dict(payload["economy"]))
        self.paths.update(self.navigation.export_path_points())

    def _apply_economy_defaults(self) -> None:
        for key, value in dict(self.economy.get("starting_resources") or {}).items():
            self.state.resources[str(key)] = _coerce_int(value)
        for quest_id, definition in self.quests.items():
            initial_state = str(definition.get("initial_state") or "inactive")
            self.state.quests[str(quest_id)] = initial_state

    def _conditions_met(self, payload: Dict[str, Any]) -> bool:
        conditions = dict(payload or {})
        nested = conditions.get("conditions")
        if isinstance(nested, dict):
            merged = dict(nested)
            for key, value in conditions.items():
                if key != "conditions":
                    merged[key] = value
            conditions = merged

        if _coerce_bool(conditions.get("always_false", False)):
            return False

        all_conditions = list(conditions.get("all_conditions") or [])
        if any(not self._conditions_met(item) for item in all_conditions if isinstance(item, dict)):
            return False

        any_conditions = [item for item in list(conditions.get("any_conditions") or []) if isinstance(item, dict)]
        if any_conditions and not any(self._conditions_met(item) for item in any_conditions):
            return False

        not_conditions = [item for item in list(conditions.get("not_conditions") or []) if isinstance(item, dict)]
        if any(self._conditions_met(item) for item in not_conditions):
            return False

        requires_flags = _string_list(conditions.get("requires_flags"))
        blocked_flags = _string_list(conditions.get("blocked_flags"))
        requires_any_flags = _string_list(conditions.get("requires_any_flags"))
        if any(not self.state.has_flag(flag) for flag in requires_flags):
            return False
        if requires_any_flags and not any(self.state.has_flag(flag) for flag in requires_any_flags):
            return False
        if any(self.state.has_flag(flag) for flag in blocked_flags):
            return False

        for key, value in dict(conditions.get("requires_resources") or {}).items():
            if self.state.resources.get(str(key), 0) < _coerce_int(value):
                return False
        for key, value in dict(conditions.get("requires_notes") or {}).items():
            if self.state.notes.get(str(key)) != value:
                return False
        for key, value in dict(conditions.get("requires_notes_not") or {}).items():
            if self.state.notes.get(str(key)) == value:
                return False
        for key in _string_list(conditions.get("requires_truthy_notes")):
            if not _coerce_bool(self.state.notes.get(str(key), False)):
                return False
        for key in _string_list(conditions.get("blocked_truthy_notes")):
            if _coerce_bool(self.state.notes.get(str(key), False)):
                return False
        for key, value in dict(conditions.get("requires_notes_min") or {}).items():
            if _coerce_float(self.state.notes.get(str(key), 0.0), 0.0) < _coerce_float(value, 0.0):
                return False
        for key, value in dict(conditions.get("requires_notes_max") or {}).items():
            if _coerce_float(self.state.notes.get(str(key), 0.0), 0.0) > _coerce_float(value, 0.0):
                return False
        for key, value in dict(conditions.get("requires_note_greater_than") or {}).items():
            if _coerce_float(self.state.notes.get(str(key), 0.0), 0.0) <= _coerce_float(value, 0.0):
                return False
        for key, value in dict(conditions.get("requires_note_less_than") or {}).items():
            if _coerce_float(self.state.notes.get(str(key), 0.0), 0.0) >= _coerce_float(value, 0.0):
                return False
        for key, values in dict(conditions.get("requires_notes_in") or {}).items():
            if self.state.notes.get(str(key)) not in list(values or []):
                return False
        for key, values in dict(conditions.get("blocked_notes_in") or {}).items():
            if self.state.notes.get(str(key)) in list(values or []):
                return False
        for quest_id, expected_state in dict(conditions.get("requires_quests") or {}).items():
            if self.state.quests.get(str(quest_id)) != str(expected_state):
                return False
        return True

    def _localized_text(self, text: Any = "", *, text_key: Any = "", default: str = "", params: Optional[Dict[str, Any]] = None) -> str:
        if self.localization is None:
            if text_key:
                return str(default or text_key)
            return str(text or default)
        key = str(text_key or "").strip()
        if key:
            return self.localization.translate(key, default=str(default or text or key), params=params)
        return self.localization.resolve_text(str(text or default), params=params, default=default)

    def _resolve_dialogue_node(self, conversation_id: str, node_id: str) -> tuple[str, Dict[str, Any]] | tuple[None, None]:
        conversation = dict(self.dialogues.get(conversation_id) or {})
        nodes = dict(conversation.get("nodes") or {})
        current_node_id = str(node_id or "")
        visited: set[str] = set()

        while current_node_id:
            if current_node_id in visited:
                break
            visited.add(current_node_id)
            node = dict(nodes.get(current_node_id) or {})
            if not node:
                return None, None

            redirects = list(node.get("redirect_if") or [])
            redirected = False
            for redirect in redirects:
                if not isinstance(redirect, dict):
                    continue
                if self._conditions_met(redirect):
                    target = str(redirect.get("next") or redirect.get("node") or "")
                    if target and target != current_node_id:
                        self.telemetry.log_event("dialogue_redirected", conversation_id=conversation_id, from_node=current_node_id, to_node=target)
                        current_node_id = target
                        redirected = True
                        break
            if redirected:
                continue

            if not self._conditions_met(node):
                fallback = str(node.get("fallback") or node.get("blocked_next") or "")
                if fallback and fallback != current_node_id:
                    self.telemetry.log_event("dialogue_redirected", conversation_id=conversation_id, from_node=current_node_id, to_node=fallback, reason="conditions")
                    current_node_id = fallback
                    continue
                self.telemetry.log_event("dialogue_blocked", conversation_id=conversation_id, node_id=current_node_id)
                return None, None
            return current_node_id, node
        return None, None

    def _filtered_choices(self, node: Dict[str, Any]) -> list[Dict[str, Any]]:
        choices: list[Dict[str, Any]] = []
        for item in list(node.get("choices") or []):
            choice = dict(item or {})
            if self._conditions_met(choice):
                choices.append(choice)
        return choices

    def get_active_dialogue_view(self) -> Dict[str, Any]:
        session = self.state.active_dialogue
        if session is None:
            return {
                "conversation_id": "",
                "node_id": "",
                "speaker": "",
                "text": "",
                "choices": [],
                "history": [],
            }
        node_id, node = self._resolve_dialogue_node(session.conversation_id, session.current_node_id)
        if node_id is None or node is None:
            return {
                "conversation_id": session.conversation_id,
                "node_id": session.current_node_id,
                "speaker": session.speaker,
                "text": "",
                "choices": [],
                "history": list(session.history),
            }
        return {
            "conversation_id": session.conversation_id,
            "node_id": node_id,
            "speaker": self._localized_text(
                node.get("speaker"),
                text_key=node.get("speaker_key"),
                default=str(node.get("speaker") or ""),
                params={"speaker": str(node.get("speaker") or "")},
            ),
            "text": self._localized_text(
                node.get("text"),
                text_key=node.get("text_key"),
                default=str(node.get("text") or ""),
                params={
                    "speaker": str(node.get("speaker") or ""),
                    **{str(key): value for key, value in self.state.resources.items()},
                    **{str(key): value for key, value in self.state.notes.items()},
                },
            ),
            "choices": [
                {
                    "index": index,
                    "text": self._localized_text(
                        choice.get("text"),
                        text_key=choice.get("text_key"),
                        default=str(choice.get("text") or ""),
                        params=self.state.notes,
                    ),
                    "next": str(choice.get("next") or ""),
                }
                for index, choice in enumerate(self._filtered_choices(node))
            ],
            "history": list(session.history),
        }

    def _register_live2d_nodes(self) -> None:
        summary = self.live2d.summary()
        if not summary["enabled"]:
            return
        for node in list(self.scene_tree.iter_nodes()):
            live2d_component = node.get_component("Live2D")
            if isinstance(live2d_component, Live2DComponent) and live2d_component.model_id:
                self.state.live2d_state[node.name] = {
                    "model_id": live2d_component.model_id,
                    "expression": "",
                    "motion": live2d_component.idle_motion,
                }
                if node.name not in self._registered_live2d:
                    event_payload = self.live2d.compose_motion_event(
                        live2d_component.model_id,
                        live2d_component.idle_motion,
                        source=f"node:{node.name}:idle",
                    )
                    self.telemetry.log_event("live2d_bound", node=node.name, **event_payload)
                    self._registered_live2d.add(node.name)

    def update(self, frame_index: int, delta: float) -> None:
        self.bootstrap()
        self._autostart_wave_spawners(frame_index)
        self._update_navigation_agents(delta)
        self._update_tower_defense(frame_index)
        self._update_dialogue_idle(frame_index)

    def handle_overlap(self, actor: Node, target: Node, *, source: str = "overlap") -> None:
        if not actor.active or not target.active:
            return
        collider = target.get_component("Collider")
        script = target.get_component("ScriptBehaviour")
        dialogue = target.get_component("Dialogue")
        tower_defense = target.get_component("TowerDefense")

        dedupe_key = f"{actor.name}:{target.name}:{source}"
        if isinstance(collider, ColliderComponent) and collider.is_trigger and dedupe_key in self._consumed_triggers:
            return

        if isinstance(script, ScriptBehaviourComponent):
            if self._handle_script_overlap(actor, target, script, source=source):
                if isinstance(collider, ColliderComponent) and collider.is_trigger:
                    self._consumed_triggers.add(dedupe_key)
                return

        if isinstance(dialogue, DialogueComponent) and dialogue.conversation_id:
            self.start_dialogue(dialogue.conversation_id, source=f"{source}:{target.name}")
            self._consumed_triggers.add(dedupe_key)
            return

        if isinstance(tower_defense, TowerDefenseComponent) and tower_defense.role == "spawner" and tower_defense.wave_id:
            self.start_wave(tower_defense.wave_id, frame_index=0)
            self._consumed_triggers.add(dedupe_key)

    def _handle_script_overlap(self, actor: Node, target: Node, script: ScriptBehaviourComponent, *, source: str) -> bool:
        script_name = str(script.script or "").strip()
        params = dict(script.params or {})
        if script_name == "collectible":
            reward_type = str(params.get("reward_type") or "currency")
            amount = _coerce_int(params.get("amount"), 1)
            if reward_type in {"currency", "gold", "credits"}:
                self.state.add_resource(reward_type, amount)
            else:
                self.state.add_inventory(reward_type, amount)
            flag = params.get("set_flag")
            if flag:
                self.state.set_flag(str(flag), True)
            target.active = False
            self.telemetry.log_event(
                "reward_claimed",
                player=actor.name,
                target=target.name,
                reward_type=reward_type,
                amount=amount,
                source=source,
            )
            return True

        if script_name == "goal_trigger":
            goal_id = str(params.get("goal_id") or target.name)
            self.state.set_flag(f"goal:{goal_id}", True)
            self.telemetry.log_event("goal_reached", player=actor.name, goal_id=goal_id, target=target.name)
            return True

        if script_name == "dialogue_trigger":
            conversation_id = str(params.get("conversation_id") or params.get("dialogue_id") or "")
            if conversation_id:
                self.start_dialogue(conversation_id, source=f"{source}:{target.name}")
                return True

        if script_name == "quest_offer":
            quest_id = str(params.get("quest_id") or "")
            if quest_id:
                self.state.quests[quest_id] = "active"
                self.telemetry.log_event("quest_updated", quest_id=quest_id, state="active", source=target.name)
                return True

        if script_name == "wave_spawner":
            wave_id = str(params.get("wave_id") or "")
            if wave_id:
                self.start_wave(wave_id, frame_index=0)
                return True

        if script_name == "damage_volume":
            self.apply_damage(actor, _coerce_float(params.get("damage"), 1.0), source=target.name)
            return True

        if script_name == "flag_setter":
            flag_name = str(params.get("flag") or params.get("set_flag") or "")
            if flag_name:
                self.state.set_flag(flag_name, True)
                self.telemetry.log_event("flag_updated", flag=flag_name, source=target.name, value=True)
                return True

        return False

    def handle_interaction(self, actor: Node, target: Optional[Node] = None) -> None:
        if target is None:
            if self.state.active_dialogue:
                self.advance_dialogue()
            return

        script = target.get_component("ScriptBehaviour")
        dialogue = target.get_component("Dialogue")
        if isinstance(dialogue, DialogueComponent) and dialogue.conversation_id:
            self.start_dialogue(dialogue.conversation_id, source=f"interact:{target.name}")
            return
        if isinstance(script, ScriptBehaviourComponent):
            if str(script.script) == "dialogue_trigger":
                conversation_id = str(script.params.get("conversation_id") or "")
                if conversation_id:
                    self.start_dialogue(conversation_id, source=f"interact:{target.name}")
                    return
            if str(script.script) == "wave_spawner":
                wave_id = str(script.params.get("wave_id") or "")
                if wave_id:
                    self.start_wave(wave_id, frame_index=0)
                    return
        self.telemetry.log_event("interaction", actor=actor.name, target=target.name)

    def handle_input_action(self, action: Dict[str, Any], frame_index: int) -> None:
        action_name = str(action.get("action") or "").strip().lower()
        if not action_name:
            return

        if action_name == "advance_dialogue":
            self.advance_dialogue()
            return

        if action_name == "choose":
            self.advance_dialogue(choice_index=_coerce_int(action.get("choice"), 0))
            return

        if action_name == "start_wave":
            self.start_wave(str(action.get("wave_id") or ""), frame_index=frame_index)
            return

        if action_name == "build_tower":
            self.build_tower(str(action.get("node") or action.get("slot") or ""), str(action.get("tower_id") or ""))
            return

        if action_name == "sell_tower":
            self.sell_tower(str(action.get("node") or action.get("slot") or ""))
            return

        if action_name == "set_flag":
            flag_name = str(action.get("flag") or "")
            if flag_name:
                self.state.set_flag(flag_name, _coerce_bool(action.get("value", True)))
                self.telemetry.log_event("flag_updated", flag=flag_name, value=self.state.has_flag(flag_name), source="input")
            return

        if action_name == "add_resource":
            resource_id = str(action.get("resource") or "gold")
            amount = _coerce_int(action.get("amount"), 1)
            self.state.add_resource(resource_id, amount)
            self.telemetry.log_event("resource_changed", resource=resource_id, amount=amount, source="input")
            return

        if action_name == "trigger_dialogue":
            conversation_id = str(action.get("conversation_id") or "")
            if conversation_id:
                self.start_dialogue(conversation_id, source="input")
            return

        if action_name == "set_locale" and self.localization is not None:
            locale = self.localization.set_locale(str(action.get("locale") or "en"))
            self.telemetry.log_event("locale_changed", locale=locale, source="input")
            return

        if action_name == "play_live2d_motion":
            model_id = str(action.get("model_id") or "")
            motion = str(action.get("motion") or "idle")
            expression = str(action.get("expression") or "")
            if model_id:
                self._emit_live2d_motion(model_id, motion, expression=expression, source="input")

    def start_dialogue(self, conversation_id: str, *, source: str = "") -> bool:
        self._ensure_content_loaded()
        conversation = self.dialogues.get(str(conversation_id))
        if not isinstance(conversation, dict):
            return False
        if not self._conditions_met(conversation):
            self.telemetry.log_event("dialogue_blocked", conversation_id=conversation_id, source=source)
            return False
        start_node = str(conversation.get("start") or "start")
        nodes = conversation.get("nodes") or {}
        if start_node not in nodes:
            return False
        self.state.active_dialogue = DialogueSession(
            conversation_id=str(conversation_id),
            current_node_id=start_node,
            source=source,
        )
        self._apply_effects(conversation.get("effects_on_start") or {})
        self.telemetry.log_event("dialogue_started", conversation_id=conversation_id, source=source)
        self._present_dialogue_node()
        return True

    def advance_dialogue(self, choice_index: Optional[int] = None) -> bool:
        session = self.state.active_dialogue
        if session is None:
            return False

        conversation = self.dialogues.get(session.conversation_id) or {}
        nodes = dict(conversation.get("nodes") or {})
        resolved_node_id, node = self._resolve_dialogue_node(session.conversation_id, session.current_node_id)
        if resolved_node_id is None or node is None:
            self.state.active_dialogue = None
            return False
        session.current_node_id = resolved_node_id

        self._apply_effects(node.get("effects_on_exit") or {})
        next_node_id = str(node.get("next") or "")

        choices = self._filtered_choices(node)
        if choices:
            index = max(0, min(_coerce_int(choice_index, 0), len(choices) - 1))
            choice = dict(choices[index] or {})
            next_node_id = str(choice.get("next") or next_node_id)
            self._apply_effects(choice.get("effects") or {})
            self.telemetry.log_event(
                "dialogue_choice",
                conversation_id=session.conversation_id,
                node_id=session.current_node_id,
                choice_index=index,
                choice_text=str(choice.get("text") or ""),
            )

        if not next_node_id:
            session.completed = True
            self.telemetry.log_event("dialogue_completed", conversation_id=session.conversation_id)
            self.state.active_dialogue = None
            return True

        session.current_node_id = next_node_id
        self._present_dialogue_node()
        return True

    def _present_dialogue_node(self) -> None:
        session = self.state.active_dialogue
        if session is None:
            return
        visited: set[str] = set()

        while session is not None:
            resolved_node_id, node = self._resolve_dialogue_node(session.conversation_id, session.current_node_id)
            if resolved_node_id is None or node is None:
                self.state.active_dialogue = None
                return
            if resolved_node_id in visited:
                return
            visited.add(resolved_node_id)
            session.current_node_id = resolved_node_id
            if session.history and session.history[-1] == resolved_node_id:
                return

            speaker = str(node.get("speaker") or "")
            session.speaker = speaker
            session.history.append(resolved_node_id)
            self._apply_effects(node.get("effects_on_enter") or {})
            text = self._localized_text(
                node.get("text"),
                text_key=node.get("text_key"),
                default=str(node.get("text") or ""),
                params=self.state.notes,
            )
            choices = self._filtered_choices(node)
            auto_advance = _coerce_bool(node.get("auto_advance", False))
            if auto_advance and not text.strip() and not speaker.strip() and not choices:
                next_node_id = str(node.get("next") or "")
                self.telemetry.log_event(
                    "dialogue_auto_advanced",
                    conversation_id=session.conversation_id,
                    node_id=resolved_node_id,
                    renpy_statement=str(node.get("renpy_statement") or ""),
                )
                if not next_node_id:
                    session.completed = True
                    self.telemetry.log_event("dialogue_completed", conversation_id=session.conversation_id)
                    self.state.active_dialogue = None
                    return
                session.current_node_id = next_node_id
                continue

            self.telemetry.log_event(
                "dialogue_line_presented",
                conversation_id=session.conversation_id,
                node_id=resolved_node_id,
                speaker=speaker,
                text=text,
                choice_count=len(choices),
            )

            live2d_motion = str(node.get("live2d_motion") or "")
            expression = str(node.get("expression") or "")
            conversation = dict(self.dialogues.get(session.conversation_id) or {})
            cast = dict(conversation.get("cast") or {})
            cast_entry = dict(cast.get(speaker) or {})
            model_id = str(node.get("model_id") or cast_entry.get("live2d_model") or "")
            if model_id and live2d_motion:
                self._emit_live2d_motion(model_id, live2d_motion, expression=expression, source=f"dialogue:{speaker}")
            return

    def _update_dialogue_idle(self, frame_index: int) -> None:
        session = self.state.active_dialogue
        if session is None:
            return
        self.state.add_counter("dialogue_frames", 1)
        self.state.notes["last_dialogue_frame"] = frame_index

    def _apply_effects(self, payload: Dict[str, Any]) -> None:
        effects = dict(payload or {})
        for flag_name in effects.get("set_flags", []) or []:
            self.state.set_flag(str(flag_name), True)
            self.telemetry.log_event("flag_updated", flag=str(flag_name), value=True, source="effect")
        for key, value in dict(effects.get("add_resources") or {}).items():
            amount = _coerce_int(value, 0)
            self.state.add_resource(str(key), amount)
            self.telemetry.log_event("resource_changed", resource=str(key), amount=amount, source="effect")
        for key, value in dict(effects.get("add_inventory") or {}).items():
            amount = _coerce_int(value, 1)
            self.state.add_inventory(str(key), amount)
            self.telemetry.log_event("inventory_changed", item_id=str(key), amount=amount, source="effect")
        for quest_id in effects.get("activate_quests", []) or []:
            self.state.quests[str(quest_id)] = "active"
            self.telemetry.log_event("quest_updated", quest_id=str(quest_id), state="active", source="effect")
        for quest_id in effects.get("complete_quests", []) or []:
            self.state.quests[str(quest_id)] = "completed"
            self.telemetry.log_event("quest_updated", quest_id=str(quest_id), state="completed", source="effect")
        for key, value in dict(effects.get("set_notes") or {}).items():
            self.state.notes[str(key)] = value
            self.telemetry.log_event("note_updated", key=str(key), value=value, source="effect")
        for key, value in dict(effects.get("add_notes") or {}).items():
            note_key = str(key)
            current = self.state.notes.get(note_key, 0)
            if isinstance(current, (int, float)) and isinstance(value, (int, float)):
                updated = current + value
            else:
                updated = _coerce_float(current, 0.0) + _coerce_float(value, 0.0)
            self.state.notes[note_key] = updated
            self.telemetry.log_event("note_updated", key=note_key, value=updated, source="effect")
        for key, value in dict(effects.get("add_counters") or {}).items():
            amount = _coerce_float(value, 0.0)
            self.state.add_counter(str(key), amount)
            self.telemetry.log_event("counter_updated", counter=str(key), amount=amount, source="effect")
        for quest_id, state in dict(effects.get("set_quests") or {}).items():
            self.state.quests[str(quest_id)] = str(state)
            self.telemetry.log_event("quest_updated", quest_id=str(quest_id), state=str(state), source="effect")

        live2d = effects.get("live2d") or {}
        if isinstance(live2d, dict):
            model_id = str(live2d.get("model_id") or "")
            motion = str(live2d.get("motion") or "")
            expression = str(live2d.get("expression") or "")
            if model_id and motion:
                self._emit_live2d_motion(model_id, motion, expression=expression, source="effect")

        for command in list(effects.get("renpy_commands") or []):
            if isinstance(command, dict):
                self._apply_renpy_command(command)

    def _renpy_stage_state(self) -> Dict[str, Any]:
        state = self.state.notes.get("_renpy_stage")
        if not isinstance(state, dict):
            state = {"background": {}, "slots": {}, "audio": {}}
            self.state.notes["_renpy_stage"] = state
        state.setdefault("background", {})
        state.setdefault("slots", {})
        state.setdefault("audio", {})
        return state

    def _renpy_stage_node(self, slot: str) -> Optional[Node]:
        names = {
            "background": "RenPyBackground",
            "left": "RenPyCharacterLeft",
            "center": "RenPyCharacterCenter",
            "right": "RenPyCharacterRight",
        }
        return self.scene_tree.find(names.get(str(slot), ""))

    def _set_renpy_stage_visibility(self, slot: str, *, visible: bool, texture: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
        node = self._renpy_stage_node(slot)
        if node is None:
            return False
        node.active = bool(visible)
        ui = node.get_component("UIControl")
        if isinstance(ui, UIControlComponent):
            ui.visible = bool(visible)
        image = node.get_component("Image")
        if isinstance(image, ImageComponent) and texture:
            image.texture = texture
        if isinstance(metadata, dict):
            node.metadata.update(metadata)
        return True

    def _clear_renpy_stage_slot(self, slot: str) -> None:
        node = self._renpy_stage_node(slot)
        if node is None:
            return
        image = node.get_component("Image")
        if isinstance(image, ImageComponent):
            image.texture = ""
        ui = node.get_component("UIControl")
        if isinstance(ui, UIControlComponent):
            ui.visible = False
        node.active = False
        for key in ["renpy_tag", "renpy_alias", "renpy_image", "renpy_expression", "renpy_texture"]:
            node.metadata.pop(key, None)

    def _find_renpy_stage_slot(self, target: str) -> str:
        normalized = str(target or "").strip().lower()
        if normalized in {"background", "bg"}:
            return "background"
        stage = self._renpy_stage_state()
        for slot, payload in dict(stage.get("slots") or {}).items():
            candidates = {
                str(payload.get("tag") or "").lower(),
                str(payload.get("alias") or "").lower(),
                str(payload.get("image") or "").lower(),
                str(payload.get("expression") or "").lower(),
            }
            if normalized and normalized in candidates:
                return str(slot)
        return ""

    def _resolve_renpy_texture(self, image_name: str, *, background: bool) -> str:
        raw = str(image_name or "").strip()
        if not raw:
            return ""

        normalized = re.sub(r"[^\w/.-]+", "_", raw.replace("\\", "/")).strip("_")
        candidates: list[str] = []
        if "." in Path(raw).name:
            candidates.extend([raw, f"assets/{raw}"])
        else:
            base_dir = "backgrounds" if background else "characters"
            for ext in [".png", ".webp", ".jpg", ".jpeg"]:
                candidates.extend(
                    [
                        f"assets/renpy/{base_dir}/{normalized}{ext}",
                        f"assets/images/{base_dir}/{normalized}{ext}",
                        f"assets/images/{normalized}{ext}",
                        f"assets/{normalized}{ext}",
                    ]
                )
        for candidate in candidates:
            try:
                if self.resource_manager.exists(candidate):
                    return str(candidate).replace("\\", "/")
            except Exception:
                continue
        return raw

    def _resolve_renpy_audio(self, asset_name: str, *, channel: str) -> str:
        raw = str(asset_name or "").strip()
        if not raw:
            return ""
        normalized = re.sub(r"[^\w/.-]+", "_", raw.replace("\\", "/")).strip("_")
        candidates: list[str] = []
        if "." in Path(raw).name:
            candidates.extend([raw, f"assets/audio/{raw}", f"assets/{raw}"])
        else:
            folder = "music" if channel == "music" else ("voice" if channel == "voice" else "audio")
            for ext in [".ogg", ".opus", ".wav", ".mp3"]:
                candidates.extend(
                    [
                        f"assets/{folder}/{normalized}{ext}",
                        f"assets/audio/{normalized}{ext}",
                        f"assets/{normalized}{ext}",
                    ]
                )
        for candidate in candidates:
            try:
                if self.resource_manager.exists(candidate):
                    return str(candidate).replace("\\", "/")
            except Exception:
                continue
        return raw

    def _select_renpy_stage_slot(self, position: str, tag: str, alias: str) -> str:
        normalized_position = str(position or "").strip().lower()
        if normalized_position in {"left", "center", "right"}:
            return normalized_position
        existing = self._find_renpy_stage_slot(alias or tag)
        if existing in {"left", "center", "right"}:
            return existing
        stage = self._renpy_stage_state()
        occupied = {str(slot) for slot in dict(stage.get("slots") or {}).keys()}
        for slot in ["center", "left", "right"]:
            if slot not in occupied:
                return slot
        return "center"

    def _apply_renpy_command(self, command: Dict[str, Any]) -> None:
        kind = str(command.get("kind") or "").strip().lower()
        if not kind:
            return

        stage = self._renpy_stage_state()
        if kind == "scene":
            image_name = str(command.get("image") or "").strip()
            texture = self._resolve_renpy_texture(image_name, background=True)
            if image_name:
                self._set_renpy_stage_visibility(
                    "background",
                    visible=True,
                    texture=texture or image_name,
                    metadata={"renpy_image": image_name, "renpy_texture": texture or image_name},
                )
                stage["background"] = {"image": image_name, "texture": texture or image_name}
            else:
                self._clear_renpy_stage_slot("background")
                stage["background"] = {}
            if _coerce_bool(command.get("clear_characters", True)):
                for slot in ["left", "center", "right"]:
                    self._clear_renpy_stage_slot(slot)
                stage["slots"] = {}
            self.telemetry.log_event("renpy_scene", image=image_name, texture=texture or image_name)
            return

        if kind == "show":
            image_name = str(command.get("image") or "").strip()
            tag = str(command.get("tag") or _image_tag(image_name)).strip()
            alias = str(command.get("alias") or "").strip()
            slot = self._select_renpy_stage_slot(str(command.get("position") or ""), tag, alias)
            texture = self._resolve_renpy_texture(image_name, background=False)
            previous_slot = self._find_renpy_stage_slot(alias or tag)
            if previous_slot and previous_slot != slot:
                self._clear_renpy_stage_slot(previous_slot)
                dict(stage.get("slots") or {}).pop(previous_slot, None)
            self._set_renpy_stage_visibility(
                slot,
                visible=True,
                texture=texture or image_name,
                metadata={
                    "renpy_tag": tag,
                    "renpy_alias": alias,
                    "renpy_image": image_name,
                    "renpy_expression": image_name,
                    "renpy_texture": texture or image_name,
                },
            )
            stage.setdefault("slots", {})[slot] = {
                "tag": tag,
                "alias": alias,
                "image": image_name,
                "expression": image_name,
                "texture": texture or image_name,
            }
            self.telemetry.log_event("renpy_show", slot=slot, tag=tag, image=image_name, texture=texture or image_name)
            return

        if kind == "hide":
            slot = self._find_renpy_stage_slot(str(command.get("target") or command.get("tag") or ""))
            if slot:
                self._clear_renpy_stage_slot(slot)
                dict(stage.get("slots") or {}).pop(slot, None)
                self.telemetry.log_event("renpy_hide", slot=slot, target=str(command.get("target") or ""))
            return

        if kind in {"play", "stop"}:
            channel = str(command.get("channel") or "sfx").strip().lower() or "sfx"
            player_id = f"renpy_{channel}"
            if kind == "stop":
                if self.audio_manager is not None:
                    self.audio_manager.stop(player_id)
                stage.setdefault("audio", {}).pop(channel, None)
                self.telemetry.log_event("renpy_audio_stop", channel=channel)
                return

            asset_name = str(command.get("asset") or "").strip()
            resolved_asset = self._resolve_renpy_audio(asset_name, channel=channel)
            loop = _coerce_bool(command.get("loop", channel == "music"))
            stage.setdefault("audio", {})[channel] = {"asset": resolved_asset or asset_name, "loop": loop}
            playback_started = False
            if self.audio_manager is not None and resolved_asset:
                audio_id = f"{player_id}_stream"
                self.audio_manager.stop(player_id)
                if self.audio_manager.load_stream(audio_id, resolved_asset):
                    player = self.audio_manager.create_player(
                        player_id,
                        audio_id,
                        loop=loop,
                        category=channel,
                    )
                    if player is not None:
                        playback_started = self.audio_manager.play(player_id)
            self.telemetry.log_event(
                "renpy_audio_play",
                channel=channel,
                asset=resolved_asset or asset_name,
                loop=loop,
                playback_started=playback_started,
            )

    def start_wave(self, wave_id: str, *, frame_index: int) -> bool:
        self._ensure_content_loaded()
        wave_key = str(wave_id).strip()
        if not wave_key or wave_key not in self.waves:
            return False
        if wave_key in self.state.active_waves and not self.state.active_waves[wave_key].completed:
            return False

        definition = dict(self.waves[wave_key] or {})
        entries = self._expand_wave_entries(definition)
        self.state.active_waves[wave_key] = ActiveWave(
            wave_id=wave_key,
            started_frame=frame_index,
            pending_entries=entries,
            reward_resources={str(key): _coerce_int(value) for key, value in dict(definition.get("reward_resources") or {}).items()},
            next_wave_id=str(definition.get("next_wave") or ""),
        )
        self.telemetry.log_event("wave_started", wave_id=wave_key, enemy_count=len(entries))
        return True

    def _autostart_wave_spawners(self, frame_index: int) -> None:
        for node in list(self.scene_tree.iter_nodes()):
            script = node.get_component("ScriptBehaviour")
            tower = node.get_component("TowerDefense")
            if isinstance(script, ScriptBehaviourComponent) and str(script.script) == "wave_spawner":
                if _coerce_bool(script.params.get("auto_start", True)):
                    wave_id = str(script.params.get("wave_id") or "")
                    if wave_id and wave_id not in self._autostarted_waves:
                        if self.start_wave(wave_id, frame_index=frame_index):
                            self._autostarted_waves.add(wave_id)
            if isinstance(tower, TowerDefenseComponent) and tower.role == "spawner" and tower.wave_id:
                auto_start = _coerce_bool(node.metadata.get("auto_start", True))
                if auto_start and tower.wave_id not in self._autostarted_waves:
                    if self.start_wave(tower.wave_id, frame_index=frame_index):
                        self._autostarted_waves.add(tower.wave_id)

    def _spawn_enemy(self, wave: ActiveWave, entry: Dict[str, Any], spawn_index: int) -> None:
        enemy_id = str(entry.get("enemy_id") or entry.get("id") or f"{wave.wave_id}_{spawn_index}")
        path_id = str(entry.get("path_id") or entry.get("path") or entry.get("lane_id") or entry.get("lane") or "")
        if not path_id or not self.navigation.has_path(path_id):
            return

        points = self.navigation.resolve_path_points(path_id)
        if not points:
            return
        start_position = Vector3.from_any(points[0] if points else [0, 0, 0])
        node = Node(
            name=f"{enemy_id}_{spawn_index}",
            node_type="Enemy",
            tags=["enemy", "tower_defense", "spawned"],
            metadata={"wave_id": wave.wave_id},
        )
        node.transform.position = start_position
        node.add_component(ColliderComponent(size=Vector3(0.9, 0.9, 0.9), layer="enemy", is_trigger=True))
        node.add_component(
            HealthComponent(
                max_health=_coerce_float(entry.get("health"), 4.0),
                current_health=_coerce_float(entry.get("health"), 4.0),
                faction="enemy",
            )
        )
        node.add_component(
            NavigationAgentComponent(
                path_id=path_id,
                speed=_coerce_float(entry.get("speed"), 1.5),
                waypoint_index=1,
                loop=False,
                stopping_distance=0.05,
            )
        )
        node.add_component(
            TowerDefenseComponent(
                role="enemy",
                reward=_coerce_int(entry.get("reward"), 5),
                path_id=path_id,
            )
        )
        self.scene_tree.spawn_node(node)
        wave.spawned_nodes.add(node.name)
        self.telemetry.log_event("enemy_spawned", wave_id=wave.wave_id, enemy_id=enemy_id, node_name=node.name, path_id=path_id)

    def _update_navigation_agents(self, delta: float) -> None:
        for node in list(self.scene_tree.iter_nodes()):
            if not node.active:
                continue
            agent = node.get_component("NavigationAgent")
            if not isinstance(agent, NavigationAgentComponent) or not agent.path_id:
                continue
            waypoints = self.navigation.resolve_path_points(agent.path_id, start_position=node.transform.position)
            if not waypoints:
                continue
            max_advances = len(waypoints) + 1
            for _ in range(max_advances):
                agent.waypoint_index = max(0, min(agent.waypoint_index, len(waypoints) - 1))
                target_point = Vector3.from_any(waypoints[agent.waypoint_index])
                current_position = node.transform.position
                offset = target_point - current_position
                distance = offset.length()

                if distance > agent.stopping_distance:
                    step = min(agent.speed * delta, distance)
                    node.transform.position = current_position + offset.normalized().scale(step)
                    break

                if agent.waypoint_index >= len(waypoints) - 1:
                    if self._node_td_role(node) == "enemy":
                        self._enemy_reached_goal(node)
                    elif agent.loop and len(waypoints) > 1:
                        agent.waypoint_index = 0
                        continue
                    break
                agent.waypoint_index += 1

    def _node_td_role(self, node: Node) -> str:
        tower = node.get_component("TowerDefense")
        if isinstance(tower, TowerDefenseComponent):
            return tower.role
        return ""

    def _enemy_reached_goal(self, node: Node) -> None:
        wave_id = str(node.metadata.get("wave_id") or "")
        node.active = False
        self.state.add_resource("lives", -1)
        self.telemetry.log_event("enemy_leaked", node_name=node.name, wave_id=wave_id, lives=self.state.resources.get("lives", 0))
        self._remove_enemy_from_wave(node.name, wave_id)

    def build_tower(self, node_name: str, tower_id: str) -> bool:
        self._ensure_content_loaded()
        if not node_name or not tower_id:
            return False
        node = self.scene_tree.find(node_name)
        blueprint = dict(self.tower_blueprints.get(tower_id) or {})
        if node is None or not blueprint:
            return False
        allowed_towers = _string_list(node.metadata.get("allowed_towers"))
        blocked_towers = _string_list(node.metadata.get("blocked_towers"))
        existing = node.get_component("TowerDefense")
        existing_tower_id = node.metadata.get("tower_id") or (existing.tower_id if isinstance(existing, TowerDefenseComponent) else "")

        if allowed_towers and tower_id not in allowed_towers:
            self.telemetry.log_event("tower_build_denied", node=node_name, tower_id=tower_id, reason="not_allowed")
            return False
        if blocked_towers and tower_id in blocked_towers:
            self.telemetry.log_event("tower_build_denied", node=node_name, tower_id=tower_id, reason="blocked")
            return False
        if isinstance(existing, TowerDefenseComponent) and existing.role == "tower":
            required_base = str(blueprint.get("upgrade_from") or "")
            if not required_base or required_base != str(existing_tower_id):
                self.telemetry.log_event("tower_build_denied", node=node_name, tower_id=tower_id, reason="occupied")
                return False

        cost = _coerce_int(blueprint.get("cost"), 0)
        gold = self.state.resources.get("gold", 0)
        if cost > gold:
            self.telemetry.log_event("tower_build_denied", node=node_name, tower_id=tower_id, gold=gold, cost=cost)
            return False

        self.state.add_resource("gold", -cost)
        node.tags = sorted(set(node.tags + ["tower", "tower_defense"]))
        node.add_component(
            TowerDefenseComponent(
                role="tower",
                tower_id=tower_id,
                range=_coerce_float(blueprint.get("range"), 4.0),
                damage=_coerce_float(blueprint.get("damage"), 1.0),
                cadence_frames=_coerce_int(blueprint.get("cadence_frames"), 30),
                projectile_speed=_coerce_float(blueprint.get("projectile_speed"), 6.0),
                target_priority=str(blueprint.get("target_priority") or "nearest"),
                upgrade_level=_coerce_int(blueprint.get("upgrade_level"), _coerce_int(node.metadata.get("tower_level"), 0) + 1),
                sell_value=_coerce_int(blueprint.get("sell_value"), max(1, int(cost * 0.6))),
                cost=cost,
            )
        )
        node.metadata["tower_id"] = tower_id
        node.metadata["tower_level"] = _coerce_int(blueprint.get("upgrade_level"), _coerce_int(node.metadata.get("tower_level"), 0) + 1)
        if isinstance(existing, TowerDefenseComponent) and existing.role == "tower":
            self.telemetry.log_event("tower_upgraded", node=node.name, tower_id=tower_id, cost=cost, level=node.metadata["tower_level"])
        else:
            self.telemetry.log_event("tower_built", node=node.name, tower_id=tower_id, cost=cost)
        return True

    def _update_tower_defense(self, frame_index: int) -> None:
        for wave in list(self.state.active_waves.values()):
            if wave.completed:
                continue
            remaining_pending = []
            for index, entry in enumerate(list(wave.pending_entries)):
                spawn_frame = _coerce_int(entry.get("spawn_frame"), index * 20)
                if frame_index - wave.started_frame >= spawn_frame:
                    self._spawn_enemy(wave, entry, index)
                else:
                    remaining_pending.append(entry)
            wave.pending_entries = remaining_pending

        enemies = [
            node
            for node in list(self.scene_tree.iter_nodes())
            if node.active and self._node_td_role(node) == "enemy"
        ]
        towers = [
            node
            for node in list(self.scene_tree.iter_nodes())
            if node.active and self._node_td_role(node) == "tower"
        ]

        for tower_node in towers:
            tower = tower_node.get_component("TowerDefense")
            if not isinstance(tower, TowerDefenseComponent):
                continue
            cooldown_key = f"tower:{tower_node.name}"
            if frame_index < self.state.cooldowns.get(cooldown_key, 0):
                continue

            target = self._nearest_enemy_in_range(tower_node, tower.range, enemies)
            if target is None:
                continue

            self.apply_damage(target, tower.damage, source=tower_node.name)
            self.state.cooldowns[cooldown_key] = frame_index + max(1, tower.cadence_frames)
            distance = (target.transform.position - tower_node.transform.position).length()
            self.telemetry.log_event(
                "tower_fired",
                tower=tower_node.name,
                target=target.name,
                damage=tower.damage,
                distance=round(distance, 3),
            )

        for wave_id, wave in list(self.state.active_waves.items()):
            if wave.completed:
                continue
            if not wave.pending_entries and not wave.spawned_nodes:
                wave.completed = True
                for resource_id, amount in wave.reward_resources.items():
                    self.state.add_resource(resource_id, amount)
                    self.telemetry.log_event("resource_changed", resource=resource_id, amount=amount, source=f"wave:{wave_id}")
                self.telemetry.log_event("wave_completed", wave_id=wave_id)
                if wave.next_wave_id:
                    if self.start_wave(wave.next_wave_id, frame_index=frame_index + 1):
                        self.telemetry.log_event("wave_chained", wave_id=wave_id, next_wave_id=wave.next_wave_id)

    def _nearest_enemy_in_range(self, tower_node: Node, max_range: float, enemies: Iterable[Node]) -> Optional[Node]:
        tower = tower_node.get_component("TowerDefense")
        priority = str(tower.target_priority).lower() if isinstance(tower, TowerDefenseComponent) else "nearest"
        best: tuple[float, Node] | None = None
        tower_position = tower_node.transform.position
        for enemy in enemies:
            distance = (enemy.transform.position - tower_position).length()
            if distance > max_range:
                continue
            score = distance
            if priority == "first":
                agent = enemy.get_component("NavigationAgent")
                progress = float(agent.waypoint_index) if isinstance(agent, NavigationAgentComponent) else 0.0
                score = -(progress * 1000.0) + distance
            elif priority == "last":
                agent = enemy.get_component("NavigationAgent")
                progress = float(agent.waypoint_index) if isinstance(agent, NavigationAgentComponent) else 0.0
                score = (progress * 1000.0) + distance
            elif priority == "strongest":
                health = enemy.get_component("Health")
                score = -(health.current_health if isinstance(health, HealthComponent) else 0.0)
            if best is None or score < best[0]:
                best = (score, enemy)
        return best[1] if best else None

    def sell_tower(self, node_name: str) -> bool:
        node = self.scene_tree.find(node_name)
        tower = node.get_component("TowerDefense") if node is not None else None
        if node is None or not isinstance(tower, TowerDefenseComponent) or tower.role != "tower":
            return False
        refund = max(0, int(tower.sell_value))
        if refund:
            self.state.add_resource("gold", refund)
        node.components.pop("TowerDefense", None)
        node.metadata["tower_id"] = ""
        self.telemetry.log_event("tower_sold", node=node.name, refund=refund)
        return True

    def _expand_wave_entries(self, definition: Dict[str, Any]) -> list[Dict[str, Any]]:
        expanded: list[Dict[str, Any]] = []
        for index, raw_entry in enumerate(list(definition.get("enemies") or [])):
            entry = dict(raw_entry or {})
            count = max(1, _coerce_int(entry.get("count"), 1))
            base_spawn = _coerce_int(entry.get("spawn_frame"), index * 20)
            interval = _coerce_int(entry.get("interval_frames"), _coerce_int(entry.get("interval"), 0))
            spawn_overrides = list(entry.get("spawn_overrides") or [])
            for spawn_index in range(count):
                payload = dict(entry)
                payload.pop("count", None)
                payload.pop("interval_frames", None)
                payload.pop("interval", None)
                payload["spawn_frame"] = base_spawn + (spawn_index * interval)
                if spawn_index < len(spawn_overrides) and isinstance(spawn_overrides[spawn_index], dict):
                    payload.update(dict(spawn_overrides[spawn_index]))
                expanded.append(payload)
        return expanded

    def apply_damage(self, node: Node, damage: float, *, source: str = "") -> bool:
        health = node.get_component("Health")
        if not isinstance(health, HealthComponent) or health.invulnerable or not node.active:
            return False
        effective_damage = max(0.1, float(damage) - max(0.0, health.armor))
        health.current_health = max(0.0, health.current_health - effective_damage)
        self.telemetry.log_event(
            "damage_applied",
            target=node.name,
            amount=round(effective_damage, 3),
            remaining_health=round(health.current_health, 3),
            source=source,
        )
        if health.current_health <= 0:
            self._destroy_enemy(node, source=source)
        return True

    def _destroy_enemy(self, node: Node, *, source: str) -> None:
        tower = node.get_component("TowerDefense")
        reward = tower.reward if isinstance(tower, TowerDefenseComponent) else 0
        wave_id = str(node.metadata.get("wave_id") or "")
        node.active = False
        if reward:
            self.state.add_resource("gold", reward)
        self.telemetry.log_event("enemy_destroyed", node_name=node.name, reward=reward, source=source, wave_id=wave_id)
        self._remove_enemy_from_wave(node.name, wave_id)

    def _remove_enemy_from_wave(self, node_name: str, wave_id: str) -> None:
        if wave_id in self.state.active_waves:
            self.state.active_waves[wave_id].spawned_nodes.discard(node_name)

    def _emit_live2d_motion(self, model_id: str, motion: str, *, expression: str = "", source: str = "") -> None:
        payload = self.live2d.compose_motion_event(model_id, motion, expression=expression, source=source)
        self.state.live2d_state[model_id] = {
            "motion": motion,
            "expression": expression,
            "source": source,
        }
        self.telemetry.log_event("live2d_motion", **payload)

    def export_state(self) -> Dict[str, Any]:
        active_dialogue = None
        if self.state.active_dialogue is not None:
            active_dialogue = {
                "conversation_id": self.state.active_dialogue.conversation_id,
                "current_node_id": self.state.active_dialogue.current_node_id,
                "source": self.state.active_dialogue.source,
                "speaker": self.state.active_dialogue.speaker,
                "history": list(self.state.active_dialogue.history),
                "completed": self.state.active_dialogue.completed,
            }
        active_waves = {
            wave_id: {
                "wave_id": wave.wave_id,
                "started_frame": wave.started_frame,
                "pending_entries": [dict(item) for item in wave.pending_entries],
                "spawned_nodes": sorted(wave.spawned_nodes),
                "reward_resources": dict(wave.reward_resources),
                "next_wave_id": wave.next_wave_id,
                "completed": wave.completed,
            }
            for wave_id, wave in self.state.active_waves.items()
        }
        return {
            "flags": dict(self.state.flags),
            "counters": dict(self.state.counters),
            "resources": dict(self.state.resources),
            "inventory": dict(self.state.inventory),
            "quests": dict(self.state.quests),
            "cooldowns": dict(self.state.cooldowns),
            "live2d_state": dict(self.state.live2d_state),
            "notes": dict(self.state.notes),
            "active_dialogue": active_dialogue,
            "active_waves": active_waves,
        }

    def restore_state(self, payload: Dict[str, Any]) -> None:
        data = dict(payload or {})
        self._ensure_content_loaded()
        self.state.flags = {str(key): bool(value) for key, value in dict(data.get("flags") or {}).items()}
        self.state.counters = {str(key): float(value) for key, value in dict(data.get("counters") or {}).items()}
        self.state.resources = {str(key): int(value) for key, value in dict(data.get("resources") or {}).items()}
        self.state.inventory = {str(key): int(value) for key, value in dict(data.get("inventory") or {}).items()}
        self.state.quests = {str(key): str(value) for key, value in dict(data.get("quests") or {}).items()}
        self.state.cooldowns = {str(key): int(value) for key, value in dict(data.get("cooldowns") or {}).items()}
        self.state.live2d_state = {str(key): dict(value or {}) for key, value in dict(data.get("live2d_state") or {}).items()}
        self.state.notes = dict(data.get("notes") or {})

        dialogue = dict(data.get("active_dialogue") or {})
        if dialogue:
            self.state.active_dialogue = DialogueSession(
                conversation_id=str(dialogue.get("conversation_id") or ""),
                current_node_id=str(dialogue.get("current_node_id") or ""),
                source=str(dialogue.get("source") or ""),
                speaker=str(dialogue.get("speaker") or ""),
                history=[str(item) for item in list(dialogue.get("history") or [])],
                completed=bool(dialogue.get("completed", False)),
            )
        else:
            self.state.active_dialogue = None

        self.state.active_waves = {}
        for wave_id, wave_payload in dict(data.get("active_waves") or {}).items():
            wave = dict(wave_payload or {})
            self.state.active_waves[str(wave_id)] = ActiveWave(
                wave_id=str(wave.get("wave_id") or wave_id),
                started_frame=_coerce_int(wave.get("started_frame"), 0),
                pending_entries=[dict(item or {}) for item in list(wave.get("pending_entries") or [])],
                spawned_nodes={str(item) for item in list(wave.get("spawned_nodes") or [])},
                reward_resources={str(key): _coerce_int(value) for key, value in dict(wave.get("reward_resources") or {}).items()},
                next_wave_id=str(wave.get("next_wave_id") or ""),
                completed=bool(wave.get("completed", False)),
            )
