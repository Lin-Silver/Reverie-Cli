"""Scene tree primitives for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

from .components import Component, TransformComponent
from .events import EventBus, Signal
from .math3d import Transform


class Node:
    """A scene-tree node with attachable components."""

    PROCESS_MODE_INHERIT = "inherit"
    PROCESS_MODE_PAUSABLE = "pausable"
    PROCESS_MODE_WHEN_PAUSED = "when_paused"
    PROCESS_MODE_ALWAYS = "always"
    PROCESS_MODE_DISABLED = "disabled"

    NOTIFICATION_ENTER_TREE = 10
    NOTIFICATION_READY = 13
    NOTIFICATION_PROCESS = 17
    NOTIFICATION_PHYSICS_PROCESS = 18
    NOTIFICATION_EXIT_TREE = 19
    NOTIFICATION_PAUSED = 20
    NOTIFICATION_UNPAUSED = 21
    NOTIFICATION_SCENE_CHANGED = 22

    def __init__(
        self,
        name: str,
        *,
        node_type: str = "Node",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        groups: Optional[list[str]] = None,
        process_mode: str = PROCESS_MODE_INHERIT,
        active: bool = True,
    ) -> None:
        self.name = str(name)
        self.node_type = str(node_type)
        self.metadata = dict(metadata or {})
        self.tags = list(tags or [])
        self.groups = {str(item).strip() for item in (groups or []) if str(item).strip()}
        self.process_mode = self._normalize_process_mode(process_mode)
        self.active = bool(active)
        self.parent: Optional["Node"] = None
        self.tree: Optional["SceneTree"] = None
        self.children: list["Node"] = []
        self.components: Dict[str, Component] = {}
        self.signals: Dict[str, Signal] = {}
        self._in_tree = False
        self._ready_called = False
        self._queued_for_deletion = False
        self.add_component(TransformComponent())

    def add_child(self, child: "Node") -> "Node":
        if child.parent is self:
            return child
        if child.parent is not None:
            child.parent.remove_child(child)
        child.parent = self
        self.children.append(child)
        if self.tree is not None:
            self.tree._attach_subtree(child)
        return child

    def remove_child(self, child: "Node") -> None:
        if child in self.children:
            if self.tree is not None:
                self.tree._detach_subtree(child)
            self.children.remove(child)
            child.parent = None

    def add_component(self, component: Component) -> Component:
        self.components[component.component_type] = component
        return component

    def get_component(self, component_type: str) -> Optional[Component]:
        normalized = str(component_type).replace("Component", "")
        return self.components.get(normalized)

    @property
    def transform(self) -> TransformComponent:
        return self.components["Transform"]  # type: ignore[return-value]

    @property
    def node_path(self) -> str:
        if self.parent is None:
            return f"/{self.name}"
        return f"{self.parent.node_path}/{self.name}"

    @property
    def is_inside_tree(self) -> bool:
        return self._in_tree

    @classmethod
    def _normalize_process_mode(cls, value: str | None) -> str:
        raw = str(value or cls.PROCESS_MODE_INHERIT).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "inherit": cls.PROCESS_MODE_INHERIT,
            "pausable": cls.PROCESS_MODE_PAUSABLE,
            "paused": cls.PROCESS_MODE_PAUSABLE,
            "always": cls.PROCESS_MODE_ALWAYS,
            "when_paused": cls.PROCESS_MODE_WHEN_PAUSED,
            "process_when_paused": cls.PROCESS_MODE_WHEN_PAUSED,
            "disabled": cls.PROCESS_MODE_DISABLED,
            "off": cls.PROCESS_MODE_DISABLED,
        }
        return aliases.get(raw, cls.PROCESS_MODE_INHERIT)

    def world_transform(self) -> Transform:
        local = self.transform.transform
        if self.parent is None:
            return local
        return local.combine(self.parent.world_transform())

    def connect(self, signal_name: str, listener) -> None:
        self.signals.setdefault(signal_name, Signal()).connect(listener)

    def emit(self, signal_name: str, *args: Any, **kwargs: Any) -> None:
        self.signals.setdefault(signal_name, Signal()).emit(*args, **kwargs)

    def notify(self, notification: int, context: Optional[Dict[str, Any]] = None) -> None:
        payload = dict(context or {})
        payload["notification"] = int(notification)
        self.emit("notification", notification=int(notification), node=self, tree=self.tree, context=payload)
        self.notification(int(notification), payload)

    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def has_tag(self, tag: str) -> bool:
        return str(tag) in self.tags

    def add_tag(self, tag: str) -> None:
        value = str(tag).strip()
        if value and value not in self.tags:
            self.tags.append(value)

    def add_to_group(self, group: str) -> None:
        value = str(group).strip()
        if not value or value in self.groups:
            return
        self.groups.add(value)
        if self.tree is not None:
            self.tree._register_group(self, value)

    def remove_from_group(self, group: str) -> None:
        value = str(group).strip()
        if value in self.groups:
            self.groups.remove(value)
            if self.tree is not None:
                self.tree._unregister_group(self, value)

    def call_deferred(self, method_name: str, *args: Any, **kwargs: Any) -> bool:
        if self.tree is None:
            return False
        callback = getattr(self, str(method_name), None)
        if not callable(callback):
            return False
        self.tree.defer_call(callback, *args, **kwargs)
        return True

    def queue_free(self) -> bool:
        if self.tree is None:
            self.remove_from_parent()
            return True
        return self.tree.queue_delete(self)

    def remove_from_parent(self) -> None:
        if self.parent:
            self.parent.remove_child(self)

    def has_node(self, name: str) -> bool:
        return self.find(name) is not None

    def find(self, name: str) -> Optional["Node"]:
        query = str(name or "").strip()
        if not query:
            return None
        if "/" in query:
            return self._find_path(query)
        for node in self.walk():
            if node.name == query:
                return node
        return None

    def _find_path(self, path: str) -> Optional["Node"]:
        if path.startswith("/"):
            current: Optional[Node] = self
            while current and current.parent is not None:
                current = current.parent
        else:
            current = self
        if current is None:
            return None

        segments = [segment for segment in str(path).split("/") if segment]
        if not segments:
            return current
        if segments[0] == current.name:
            segments = segments[1:]
        for segment in segments:
            current = next((child for child in current.children if child.name == segment), None)
            if current is None:
                return None
        return current

    def find_all(self, *, tag: str = "", node_type: str = "", group: str = "") -> list["Node"]:
        results: list["Node"] = []
        normalized_tag = str(tag).strip()
        normalized_type = str(node_type).strip()
        normalized_group = str(group).strip()
        for node in self.walk():
            if normalized_tag and normalized_tag not in node.tags:
                continue
            if normalized_type and normalized_type != node.node_type:
                continue
            if normalized_group and normalized_group not in node.groups:
                continue
            results.append(node)
        return results

    def enter_tree(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook fired when the node enters the active tree."""

    def ready(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook fired after the node and its children enter the tree."""

    def exit_tree(self, context: Dict[str, Any]) -> None:
        """Lifecycle hook fired before the node leaves the active tree."""

    def notification(self, notification: int, context: Dict[str, Any]) -> None:
        """Generic notification hook for lifecycle and tree state changes."""

    def process(self, delta: float, context: Dict[str, Any]) -> None:
        """Per-frame callback."""

    def physics_process(self, delta: float, context: Dict[str, Any]) -> None:
        """Fixed-timestep callback."""

    def update(self, delta: float, context: Dict[str, Any]) -> None:
        scene_tree = context.get("scene_tree")
        if scene_tree is None or scene_tree._should_process_node(self):
            self.notify(self.NOTIFICATION_PROCESS, context)
            self.process(delta, context)
        for child in list(self.children):
            if child.active and not child._queued_for_deletion:
                child.update(delta, context)

    def fixed_update(self, delta: float, context: Dict[str, Any]) -> None:
        scene_tree = context.get("scene_tree")
        if scene_tree is None or scene_tree._should_process_node(self):
            self.notify(self.NOTIFICATION_PHYSICS_PROCESS, context)
            self.physics_process(delta, context)
        for child in list(self.children):
            if child.active and not child._queued_for_deletion:
                child.fixed_update(delta, context)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.node_type,
            "active": self.active,
            "tags": list(self.tags),
            "groups": sorted(self.groups),
            "process_mode": self.process_mode,
            "metadata": dict(self.metadata),
            "components": [component.to_dict() for component in self.components.values()],
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class Scene(Node):
    """A serializable scene root."""

    scene_id: str = "main"

    def __init__(self, name: str, scene_id: str = "main", **kwargs: Any) -> None:
        kwargs.setdefault("process_mode", Node.PROCESS_MODE_ALWAYS)
        super().__init__(name, node_type="Scene", **kwargs)
        self.scene_id = scene_id

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["scene_id"] = self.scene_id
        return payload


@dataclass
class DeferredCall:
    callback: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneTimer:
    duration: float
    callback: Optional[Callable[[], Any]] = None
    repeat: bool = False
    name: str = ""
    remaining: float = field(init=False)
    completed: bool = False

    def __post_init__(self) -> None:
        self.duration = max(float(self.duration), 0.0)
        self.remaining = self.duration


@dataclass
class SceneTree:
    """Owns the active scene and shared runtime services."""

    root: Scene
    event_bus: EventBus = field(default_factory=EventBus)
    fixed_step: float = 1.0 / 60.0
    telemetry: Any = None
    resource_manager: Any = None
    config: Any = None
    paused: bool = False
    current_frame: int = 0
    _accumulator: float = 0.0
    _deferred_calls: list[DeferredCall] = field(default_factory=list)
    _delete_queue: list[Node] = field(default_factory=list)
    _timers: list[SceneTimer] = field(default_factory=list)
    _groups: Dict[str, list[Node]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.current_scene = self.root
        self.root.parent = None
        self._attach_subtree(self.root)

    def iter_nodes(self) -> Iterable[Node]:
        return self.root.walk()

    def find(self, name: str) -> Optional[Node]:
        return self.root.find(name)

    def has_node(self, name: str) -> bool:
        return self.find(name) is not None

    def find_all(self, *, tag: str = "", node_type: str = "", group: str = "") -> list[Node]:
        return self.root.find_all(tag=tag, node_type=node_type, group=group)

    def get_nodes_in_group(self, group: str) -> list[Node]:
        return list(self._groups.get(str(group).strip(), []))

    def spawn_node(self, node: Node, parent_name: str = "") -> Node:
        parent = self.find(parent_name) if parent_name else self.root
        if parent is None:
            parent = self.root
        return parent.add_child(node)

    def remove_node(self, name: str) -> bool:
        node = self.find(name)
        if node is None or node is self.root:
            return False
        node.remove_from_parent()
        return True

    def build_context(self, *, delta: float = 0.0, frame_index: int | None = None) -> Dict[str, Any]:
        current_frame = self.current_frame if frame_index is None else int(frame_index)
        return {
            "scene_tree": self,
            "event_bus": self.event_bus,
            "telemetry": self.telemetry,
            "resource_manager": self.resource_manager,
            "config": self.config,
            "frame_index": current_frame,
            "delta": delta,
        }

    def create_timer(
        self,
        duration: float,
        callback: Optional[Callable[[], Any]] = None,
        *,
        repeat: bool = False,
        name: str = "",
    ) -> SceneTimer:
        timer = SceneTimer(duration=duration, callback=callback, repeat=repeat, name=str(name))
        self._timers.append(timer)
        return timer

    def set_paused(self, paused: bool) -> bool:
        desired = bool(paused)
        if self.paused == desired:
            return False
        self.paused = desired
        context = self.build_context()
        notification = Node.NOTIFICATION_PAUSED if desired else Node.NOTIFICATION_UNPAUSED
        for node in list(self.iter_nodes()):
            node.notify(notification, context)
        self.event_bus.publish("scene_tree.pause_changed", paused=desired, frame_index=self.current_frame)
        return True

    def defer_call(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._deferred_calls.append(DeferredCall(callback=callback, args=tuple(args), kwargs=dict(kwargs)))

    def queue_delete(self, node: Node) -> bool:
        if node is self.root:
            return False
        if node._queued_for_deletion:
            return True
        node._queued_for_deletion = True
        self._delete_queue.append(node)
        return True

    def call_group(self, group: str, method_name: str, *args: Any, **kwargs: Any) -> int:
        method_name = str(method_name).strip()
        if not method_name:
            return 0
        invoked = 0
        for node in list(self._groups.get(str(group).strip(), [])):
            callback = getattr(node, method_name, None)
            if callable(callback) and node.tree is self and not node._queued_for_deletion:
                callback(*args, **kwargs)
                invoked += 1
        return invoked

    def change_scene(self, scene: Scene) -> Scene:
        if self.root is scene:
            return scene
        previous = self.root
        self.event_bus.publish(
            "scene_tree.scene_changing",
            old_scene=previous.scene_id,
            new_scene=scene.scene_id,
            old_root=previous.name,
            new_root=scene.name,
        )
        self._deferred_calls.clear()
        self._delete_queue.clear()
        self._timers.clear()
        self._accumulator = 0.0
        self._detach_subtree(previous)
        self.root.parent = None
        self.root = scene
        self.current_scene = scene
        self.root.parent = None
        self._attach_subtree(scene)
        context = self.build_context()
        for node in list(self.iter_nodes()):
            node.notify(Node.NOTIFICATION_SCENE_CHANGED, context)
        self.event_bus.publish(
            "scene_tree.scene_changed",
            old_scene=previous.scene_id,
            new_scene=scene.scene_id,
            old_root=previous.name,
            new_root=scene.name,
        )
        return scene

    def step(self, delta: float, *, frame_index: int = 0) -> None:
        self.current_frame = int(frame_index)
        self._process_timers(delta)
        self._accumulator += delta
        while self._accumulator >= self.fixed_step:
            fixed_context = self.build_context(delta=self.fixed_step, frame_index=frame_index)
            self.root.fixed_update(self.fixed_step, fixed_context)
            self._accumulator -= self.fixed_step
        context = self.build_context(delta=delta, frame_index=frame_index)
        self.root.update(delta, context)
        self._flush_deferred_calls()
        self._flush_delete_queue()

    def _attach_subtree(self, node: Node) -> None:
        self._bind_tree_recursive(node)
        context = self.build_context()
        self._enter_tree_recursive(node, context)
        self._ready_recursive(node, context)

    def _detach_subtree(self, node: Node) -> None:
        context = self.build_context()
        for child in list(node.children):
            self._detach_subtree(child)
        if node._in_tree:
            node.notify(Node.NOTIFICATION_EXIT_TREE, context)
            node.emit("exit_tree", node=node, tree=self, context=context)
            node.exit_tree(context)
        for group in list(node.groups):
            self._unregister_group(node, group)
        node._in_tree = False
        node._ready_called = False
        node._queued_for_deletion = False
        node.tree = None

    def _bind_tree_recursive(self, node: Node) -> None:
        node.tree = self
        for child in node.children:
            self._bind_tree_recursive(child)

    def _enter_tree_recursive(self, node: Node, context: Dict[str, Any]) -> None:
        node._in_tree = True
        for group in sorted(node.groups):
            self._register_group(node, group)
        node.notify(Node.NOTIFICATION_ENTER_TREE, context)
        node.emit("enter_tree", node=node, tree=self, context=context)
        node.enter_tree(context)
        for child in list(node.children):
            self._enter_tree_recursive(child, context)

    def _ready_recursive(self, node: Node, context: Dict[str, Any]) -> None:
        for child in list(node.children):
            self._ready_recursive(child, context)
        if not node._ready_called:
            node._ready_called = True
            node.notify(Node.NOTIFICATION_READY, context)
            node.emit("ready", node=node, tree=self, context=context)
            node.ready(context)

    def _register_group(self, node: Node, group: str) -> None:
        nodes = self._groups.setdefault(str(group), [])
        if node not in nodes:
            nodes.append(node)

    def _unregister_group(self, node: Node, group: str) -> None:
        group_name = str(group)
        nodes = self._groups.get(group_name)
        if not nodes:
            return
        if node in nodes:
            nodes.remove(node)
        if not nodes:
            self._groups.pop(group_name, None)

    def _process_timers(self, delta: float) -> None:
        finished: list[SceneTimer] = []
        for timer in list(self._timers):
            if timer.completed:
                finished.append(timer)
                continue
            timer.remaining -= delta
            if timer.remaining > 0:
                continue
            if timer.callback is not None:
                timer.callback()
            self.event_bus.publish("scene_tree.timer", name=timer.name, duration=timer.duration)
            if timer.repeat:
                timer.remaining = timer.duration
            else:
                timer.completed = True
                finished.append(timer)
        if finished:
            self._timers = [timer for timer in self._timers if timer not in finished]

    def _resolved_process_mode(self, node: Node) -> str:
        current: Optional[Node] = node
        while current is not None:
            mode = current.process_mode
            if mode != Node.PROCESS_MODE_INHERIT:
                return mode
            current = current.parent
        return Node.PROCESS_MODE_PAUSABLE

    def _should_process_node(self, node: Node) -> bool:
        if not node.active or node._queued_for_deletion:
            return False
        mode = self._resolved_process_mode(node)
        if mode == Node.PROCESS_MODE_DISABLED:
            return False
        if mode == Node.PROCESS_MODE_ALWAYS:
            return True
        if mode == Node.PROCESS_MODE_WHEN_PAUSED:
            return self.paused
        return not self.paused

    def _flush_deferred_calls(self) -> None:
        pending = list(self._deferred_calls)
        self._deferred_calls.clear()
        for call in pending:
            call.callback(*call.args, **call.kwargs)

    def _flush_delete_queue(self) -> None:
        pending = list(dict.fromkeys(self._delete_queue))
        self._delete_queue.clear()
        for node in pending:
            if node is self.root:
                continue
            if node.parent is not None:
                node.parent.remove_child(node)
