"""Animation, timeline, and state orchestration for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from .components import AnimatorComponent, StateMachineComponent
from .math3d import Vector2, Vector3
from .scene import Node, SceneTree


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))


def _interpolate_value(start: Any, end: Any, alpha: float) -> Any:
    alpha = max(0.0, min(1.0, float(alpha)))
    if _is_number(start) and _is_number(end):
        return (float(start) * (1.0 - alpha)) + (float(end) * alpha)
    if isinstance(start, Vector2) or isinstance(end, Vector2):
        start_v = Vector2.from_any(start)
        end_v = Vector2.from_any(end)
        return Vector2(
            (start_v.x * (1.0 - alpha)) + (end_v.x * alpha),
            (start_v.y * (1.0 - alpha)) + (end_v.y * alpha),
        )
    if isinstance(start, Vector3) or isinstance(end, Vector3):
        start_v = Vector3.from_any(start)
        end_v = Vector3.from_any(end)
        return Vector3(
            (start_v.x * (1.0 - alpha)) + (end_v.x * alpha),
            (start_v.y * (1.0 - alpha)) + (end_v.y * alpha),
            (start_v.z * (1.0 - alpha)) + (end_v.z * alpha),
        )
    if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)) and len(start) == len(end):
        if all(_is_number(item) for item in list(start) + list(end)):
            return [(float(start[i]) * (1.0 - alpha)) + (float(end[i]) * alpha) for i in range(len(start))]
    return end if alpha >= 1.0 else start


def _coerce_value_like(current: Any, value: Any) -> Any:
    if isinstance(current, Vector2):
        return Vector2.from_any(value)
    if isinstance(current, Vector3):
        return Vector3.from_any(value)
    if isinstance(current, tuple) and isinstance(value, list):
        return tuple(value)
    return value


def _resolve_target(scene_tree: SceneTree, owner: Node, target: str) -> Optional[Node]:
    query = str(target or ".").strip()
    if query in {"", ".", "self"}:
        return owner
    if query.startswith("/"):
        return scene_tree.root.find(query)
    return owner.find(query) or scene_tree.find(query)


def _get_property_value(node: Node, property_path: str) -> Any:
    path = str(property_path or "").strip()
    if not path:
        return None
    if path.startswith("metadata."):
        return node.metadata.get(path.split(".", 1)[1])
    if path.startswith("transform."):
        transform_attr = path.split(".", 1)[1]
        value: Any = node.transform
        for segment in transform_attr.split("."):
            value = getattr(value, segment)
        return value
    if path.startswith("component:"):
        component_path = path[len("component:"):]
        component_name, _, attr_path = component_path.partition(".")
        component = node.get_component(component_name)
        if component is None:
            return None
        value = component
        for segment in filter(None, attr_path.split(".")):
            value = getattr(value, segment)
        return value
    value = node
    for segment in path.split("."):
        value = getattr(value, segment)
    return value


def _set_property_value(node: Node, property_path: str, value: Any) -> None:
    path = str(property_path or "").strip()
    if not path:
        return
    if path.startswith("metadata."):
        node.metadata[path.split(".", 1)[1]] = value
        return
    if path.startswith("transform."):
        target: Any = node.transform
        segments = path.split(".")[1:]
        for segment in segments[:-1]:
            target = getattr(target, segment)
        current = getattr(target, segments[-1], None)
        setattr(target, segments[-1], _coerce_value_like(current, value))
        return
    if path.startswith("component:"):
        component_path = path[len("component:"):]
        component_name, _, attr_path = component_path.partition(".")
        component = node.get_component(component_name)
        if component is None or not attr_path:
            return
        target = component
        segments = attr_path.split(".")
        for segment in segments[:-1]:
            target = getattr(target, segment)
        current = getattr(target, segments[-1], None)
        setattr(target, segments[-1], _coerce_value_like(current, value))
        return
    target = node
    segments = path.split(".")
    for segment in segments[:-1]:
        target = getattr(target, segment)
    current = getattr(target, segments[-1], None)
    setattr(target, segments[-1], _coerce_value_like(current, value))


@dataclass
class AnimationKeyframe:
    time: float
    value: Any

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "AnimationKeyframe":
        return cls(time=_coerce_float(payload.get("time"), 0.0), value=payload.get("value"))


@dataclass
class AnimationTrack:
    target: str
    property_path: str
    interpolation: str = "linear"
    keyframes: list[AnimationKeyframe] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "AnimationTrack":
        keyframes = [AnimationKeyframe.from_payload(item) for item in list(payload.get("keyframes") or [])]
        keyframes.sort(key=lambda item: item.time)
        return cls(
            target=str(payload.get("target") or "."),
            property_path=str(payload.get("property") or payload.get("property_path") or ""),
            interpolation=str(payload.get("interpolation") or "linear").strip().lower(),
            keyframes=keyframes,
        )

    def sample(self, time_cursor: float) -> Any:
        if not self.keyframes:
            return None
        if len(self.keyframes) == 1 or time_cursor <= self.keyframes[0].time:
            return self.keyframes[0].value
        for index in range(1, len(self.keyframes)):
            previous = self.keyframes[index - 1]
            current = self.keyframes[index]
            if time_cursor < current.time:
                if self.interpolation == "step":
                    return previous.value
                duration = max(0.00001, current.time - previous.time)
                alpha = (time_cursor - previous.time) / duration
                return _interpolate_value(previous.value, current.value, alpha)
        return self.keyframes[-1].value


@dataclass
class AnimationClip:
    clip_id: str
    length: float = 0.0
    loop: bool = False
    tracks: list[AnimationTrack] = field(default_factory=list)

    @classmethod
    def from_payload(cls, clip_id: str, payload: Dict[str, Any]) -> "AnimationClip":
        tracks = [AnimationTrack.from_payload(item) for item in list(payload.get("tracks") or [])]
        derived_length = 0.0
        for track in tracks:
            if track.keyframes:
                derived_length = max(derived_length, track.keyframes[-1].time)
        return cls(
            clip_id=str(clip_id),
            length=max(_coerce_float(payload.get("length"), derived_length), derived_length),
            loop=bool(payload.get("loop", False)),
            tracks=tracks,
        )


@dataclass
class TimelineEvent:
    frame: int
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    fired: bool = False

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "TimelineEvent":
        params = {
            str(key): value
            for key, value in dict(payload or {}).items()
            if key not in {"frame", "action"}
        }
        return cls(frame=max(0, _coerce_int(payload.get("frame"), 0)), action=str(payload.get("action") or ""), params=params)


@dataclass
class Timeline:
    timeline_id: str
    events: list[TimelineEvent] = field(default_factory=list)
    loop: bool = False
    stop_on_complete: bool = True

    @classmethod
    def from_payload(cls, timeline_id: str, payload: Dict[str, Any]) -> "Timeline":
        events = [TimelineEvent.from_payload(item) for item in list(payload.get("events") or [])]
        events.sort(key=lambda item: item.frame)
        return cls(
            timeline_id=str(timeline_id),
            events=events,
            loop=bool(payload.get("loop", False)),
            stop_on_complete=bool(payload.get("stop_on_complete", True)),
        )


@dataclass
class StateTransition:
    target: str
    after_frames: int = 0
    when_flag: str = ""
    when_not_flag: str = ""
    when_counter_at_least: Dict[str, float] = field(default_factory=dict)
    when_metadata_equals: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "StateTransition":
        return cls(
            target=str(payload.get("target") or ""),
            after_frames=max(0, _coerce_int(payload.get("after_frames"), 0)),
            when_flag=str(payload.get("when_flag") or ""),
            when_not_flag=str(payload.get("when_not_flag") or ""),
            when_counter_at_least={str(key): _coerce_float(value) for key, value in dict(payload.get("when_counter_at_least") or {}).items()},
            when_metadata_equals=dict(payload.get("when_metadata_equals") or {}),
        )

    def is_triggered(self, node: Node, context: Dict[str, Any], elapsed_frames: int) -> bool:
        if self.after_frames and elapsed_frames < self.after_frames:
            return False
        gameplay = context.get("gameplay")
        if self.when_flag:
            if gameplay is None or not gameplay.state.has_flag(self.when_flag):
                return False
        if self.when_not_flag:
            if gameplay is not None and gameplay.state.has_flag(self.when_not_flag):
                return False
        if self.when_counter_at_least:
            if gameplay is None:
                return False
            for key, threshold in self.when_counter_at_least.items():
                if gameplay.state.counters.get(key, 0.0) < threshold:
                    return False
        if self.when_metadata_equals:
            for key, expected in self.when_metadata_equals.items():
                if node.metadata.get(key) != expected:
                    return False
        return True


@dataclass
class StateDefinition:
    state_id: str
    clip: str = ""
    duration_frames: int = 0
    next_state: str = ""
    transitions: list[StateTransition] = field(default_factory=list)
    on_enter: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, state_id: str, payload: Dict[str, Any]) -> "StateDefinition":
        transitions = [StateTransition.from_payload(item) for item in list(payload.get("transitions") or [])]
        next_state = str(payload.get("next") or payload.get("next_state") or "")
        duration_frames = max(0, _coerce_int(payload.get("duration_frames"), 0))
        if next_state and duration_frames and not transitions:
            transitions = [StateTransition(target=next_state, after_frames=duration_frames)]
        return cls(
            state_id=str(state_id),
            clip=str(payload.get("clip") or ""),
            duration_frames=duration_frames,
            next_state=next_state,
            transitions=transitions,
            on_enter=dict(payload.get("on_enter") or {}),
        )


@dataclass
class AnimationPlaybackState:
    clip_id: str
    time_cursor: float = 0.0
    playing: bool = False
    completed_loops: int = 0


@dataclass
class TimelinePlaybackState:
    timeline_id: str
    playing: bool = True
    start_frame: int = 0
    loop_count: int = 0


@dataclass
class StateMachineRuntime:
    current_state: str
    entered_frame: int = 0


class SequenceDirector:
    """Coordinates animation playback, state machines, and timeline actions."""

    def __init__(self, scene_tree: SceneTree, telemetry: Any, *, gameplay: Any = None) -> None:
        self.scene_tree = scene_tree
        self.telemetry = telemetry
        self.gameplay = gameplay
        self._clips_by_node: Dict[str, Dict[str, AnimationClip]] = {}
        self._animations: Dict[str, AnimationPlaybackState] = {}
        self._state_definitions: Dict[str, Dict[str, StateDefinition]] = {}
        self._state_machines: Dict[str, StateMachineRuntime] = {}
        self._timelines: Dict[str, Timeline] = {}
        self._timeline_types: Dict[str, str] = {}
        self._timeline_runtime: Dict[str, TimelinePlaybackState] = {}
        self._bootstrapped = False

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self._bootstrap_animators()
        self._bootstrap_state_machines()
        self._bootstrap_timelines()
        self._bootstrapped = True

    def _bootstrap_animators(self) -> None:
        for node in self.scene_tree.iter_nodes():
            animator = node.get_component("Animator")
            if not isinstance(animator, AnimatorComponent):
                continue
            clips = {
                str(clip_id): AnimationClip.from_payload(str(clip_id), dict(payload or {}))
                for clip_id, payload in dict(animator.state_machine.get("clips") or {}).items()
            }
            self._clips_by_node[node.node_path] = clips
            play_on_start = str(animator.state_machine.get("play_on_start") or animator.current_state or "")
            if play_on_start and play_on_start in clips:
                self.play_animation(node, play_on_start)

    def _bootstrap_state_machines(self) -> None:
        for node in self.scene_tree.iter_nodes():
            component = node.get_component("StateMachine")
            if not isinstance(component, StateMachineComponent):
                continue
            states = {
                str(state_id): StateDefinition.from_payload(str(state_id), dict(payload or {}))
                for state_id, payload in dict(component.states or {}).items()
            }
            if not states:
                continue
            self._state_definitions[node.node_path] = states
            current_state = component.current_state if component.current_state in states else next(iter(states.keys()))
            self._state_machines[node.node_path] = StateMachineRuntime(current_state=current_state, entered_frame=self.scene_tree.current_frame)
            self._apply_state_entry(node, states[current_state], self.scene_tree.current_frame)

    def _bootstrap_timelines(self) -> None:
        root_metadata = dict(self.scene_tree.root.metadata or {})
        raw_cutscenes = dict(root_metadata.get("cutscenes") or {})
        for timeline_id, payload in raw_cutscenes.items():
            timeline = Timeline.from_payload(str(timeline_id), dict(payload or {}))
            self._timelines[timeline.timeline_id] = timeline
            self._timeline_types[timeline.timeline_id] = "cutscene"
            if bool(payload.get("autoplay", False)):
                self.play_timeline(timeline.timeline_id)

        raw_dialogue = dict(root_metadata.get("dialogue_timelines") or {})
        for timeline_id, payload in raw_dialogue.items():
            timeline = Timeline.from_payload(str(timeline_id), dict(payload or {}))
            self._timelines[timeline.timeline_id] = timeline
            self._timeline_types[timeline.timeline_id] = "dialogue"
            if bool(payload.get("autoplay", False)):
                self.play_timeline(timeline.timeline_id)

    def play_animation(self, node: Node | str, clip_id: str) -> bool:
        target = self.scene_tree.find(node) if isinstance(node, str) else node
        if target is None:
            return False
        clips = self._clips_by_node.get(target.node_path, {})
        if clip_id not in clips:
            return False
        self._animations[target.node_path] = AnimationPlaybackState(clip_id=str(clip_id), time_cursor=0.0, playing=True)
        animator = target.get_component("Animator")
        if isinstance(animator, AnimatorComponent):
            animator.current_state = str(clip_id)
        self.telemetry.log_event("animation_started", node=target.name, clip_id=str(clip_id))
        self._apply_clip(target, clips[clip_id], 0.0)
        return True

    def play_timeline(self, timeline_id: str, *, start_frame: Optional[int] = None) -> bool:
        key = str(timeline_id or "").strip()
        if key not in self._timelines:
            return False
        frame = self.scene_tree.current_frame if start_frame is None else int(start_frame)
        timeline = self._timelines[key]
        for event in timeline.events:
            event.fired = False
        self._timeline_runtime[key] = TimelinePlaybackState(timeline_id=key, start_frame=frame)
        self.telemetry.log_event(self._timeline_event_name(key, "started"), timeline_id=key)
        return True

    def update(self, delta: float, frame_index: int) -> None:
        self.bootstrap()
        self._update_state_machines(frame_index)
        self._update_animations(delta)
        self._update_timelines(frame_index)

    def summary(self) -> Dict[str, Any]:
        return {
            "animation_players": len(self._animations),
            "state_machines": len(self._state_machines),
            "active_timelines": sorted(key for key, state in self._timeline_runtime.items() if state.playing),
            "known_timelines": sorted(self._timelines.keys()),
        }

    def _update_animations(self, delta: float) -> None:
        for node_path, playback in list(self._animations.items()):
            if not playback.playing:
                continue
            node = self.scene_tree.root.find(node_path)
            if node is None:
                continue
            clip = self._clips_by_node.get(node_path, {}).get(playback.clip_id)
            if clip is None:
                continue
            playback.time_cursor += max(0.0, float(delta))
            effective_time = playback.time_cursor
            if clip.length > 0.0 and playback.time_cursor >= clip.length:
                if clip.loop:
                    playback.completed_loops += 1
                    playback.time_cursor = playback.time_cursor % max(0.00001, clip.length)
                    effective_time = playback.time_cursor
                    self.telemetry.log_event("animation_looped", node=node.name, clip_id=clip.clip_id, loop_count=playback.completed_loops)
                else:
                    playback.playing = False
                    effective_time = clip.length
                    self.telemetry.log_event("animation_completed", node=node.name, clip_id=clip.clip_id)
            self._apply_clip(node, clip, effective_time)

    def _apply_clip(self, owner: Node, clip: AnimationClip, time_cursor: float) -> None:
        for track in clip.tracks:
            target = _resolve_target(self.scene_tree, owner, track.target)
            if target is None:
                continue
            value = track.sample(time_cursor)
            if value is None:
                continue
            _set_property_value(target, track.property_path, value)

    def _update_state_machines(self, frame_index: int) -> None:
        context = {"frame_index": frame_index, "gameplay": self.gameplay, "telemetry": self.telemetry}
        for node_path, runtime in list(self._state_machines.items()):
            node = self.scene_tree.root.find(node_path)
            definitions = self._state_definitions.get(node_path, {})
            if node is None or runtime.current_state not in definitions:
                continue
            component = node.get_component("StateMachine")
            elapsed_frames = frame_index - runtime.entered_frame
            state = definitions[runtime.current_state]
            target_state = ""
            for transition in state.transitions:
                if transition.target in definitions and transition.is_triggered(node, context, elapsed_frames):
                    target_state = transition.target
                    break
            if not target_state:
                continue
            runtime.current_state = target_state
            runtime.entered_frame = frame_index
            if isinstance(component, StateMachineComponent):
                component.current_state = target_state
            self._apply_state_entry(node, definitions[target_state], frame_index)
            self.telemetry.log_event("state_changed", node=node.name, state=target_state)

    def _apply_state_entry(self, node: Node, state: StateDefinition, frame_index: int) -> None:
        animator = node.get_component("Animator")
        if isinstance(animator, AnimatorComponent):
            clip_id = state.clip or state.state_id
            if clip_id:
                self.play_animation(node, clip_id)
        for key, value in dict(state.on_enter).items():
            if key.startswith("metadata."):
                node.metadata[key.split(".", 1)[1]] = value
        self.telemetry.log_event("state_entered", node=node.name, state=state.state_id, frame_index=frame_index)

    def _update_timelines(self, frame_index: int) -> None:
        for timeline_id, runtime in list(self._timeline_runtime.items()):
            if not runtime.playing:
                continue
            timeline = self._timelines.get(timeline_id)
            if timeline is None:
                continue
            local_frame = frame_index - runtime.start_frame
            all_fired = True
            for event in timeline.events:
                if event.fired:
                    continue
                if local_frame < event.frame:
                    all_fired = False
                    continue
                self._execute_timeline_event(timeline_id, event)
                event.fired = True
            if all_fired and timeline.events:
                if timeline.loop:
                    runtime.loop_count += 1
                    runtime.start_frame = frame_index
                    for event in timeline.events:
                        event.fired = False
                    self.telemetry.log_event(self._timeline_event_name(timeline_id, "looped"), timeline_id=timeline_id, loop_count=runtime.loop_count)
                elif timeline.stop_on_complete:
                    runtime.playing = False
                    self.telemetry.log_event(self._timeline_event_name(timeline_id, "completed"), timeline_id=timeline_id)

    def _timeline_event_name(self, timeline_id: str, suffix: str) -> str:
        category = self._timeline_types.get(timeline_id, "timeline")
        if category == "dialogue":
            return f"dialogue_timeline_{suffix}"
        return f"{category}_{suffix}"

    def _execute_timeline_event(self, timeline_id: str, event: TimelineEvent) -> None:
        action = event.action.strip().lower()
        params = dict(event.params or {})
        if action == "emit_event":
            name = str(params.pop("name", "") or "timeline_event")
            self.telemetry.log_event(name, timeline_id=timeline_id, **params)
            return
        if action == "set_metadata":
            target = _resolve_target(self.scene_tree, self.scene_tree.root, str(params.get("target") or "."))
            if target is None:
                return
            key = str(params.get("key") or "")
            if key:
                target.metadata[key] = params.get("value")
            self.telemetry.log_event("timeline_metadata_set", timeline_id=timeline_id, target=target.name, key=key)
            return
        if action == "play_animation":
            target_name = str(params.get("target") or ".")
            clip_id = str(params.get("clip") or params.get("clip_id") or "")
            target = _resolve_target(self.scene_tree, self.scene_tree.root, target_name)
            if target and clip_id:
                self.play_animation(target, clip_id)
            return
        if action == "set_property":
            target = _resolve_target(self.scene_tree, self.scene_tree.root, str(params.get("target") or "."))
            property_path = str(params.get("property") or params.get("property_path") or "")
            if target and property_path:
                _set_property_value(target, property_path, params.get("value"))
                self.telemetry.log_event("timeline_property_set", timeline_id=timeline_id, target=target.name, property_path=property_path)
            return
        if action == "start_dialogue" and self.gameplay is not None:
            conversation_id = str(params.get("conversation_id") or params.get("id") or "")
            if conversation_id:
                self.gameplay.start_dialogue(conversation_id, source=f"timeline:{timeline_id}")
            return
        if action == "advance_dialogue" and self.gameplay is not None:
            self.gameplay.advance_dialogue(choice_index=params.get("choice_index"))
            return
        if action == "set_flag" and self.gameplay is not None:
            flag_name = str(params.get("flag") or "")
            if flag_name:
                self.gameplay.state.set_flag(flag_name, bool(params.get("value", True)))
                self.telemetry.log_event("flag_updated", flag=flag_name, value=bool(params.get("value", True)), source=f"timeline:{timeline_id}")
            return
        if action == "live2d_motion" and self.gameplay is not None:
            model_id = str(params.get("model_id") or "")
            motion = str(params.get("motion") or "")
            expression = str(params.get("expression") or "")
            if model_id and motion and hasattr(self.gameplay, "_emit_live2d_motion"):
                self.gameplay._emit_live2d_motion(model_id, motion, expression=expression, source=f"timeline:{timeline_id}")  # type: ignore[attr-defined]
