"""Navigation services for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
from typing import Any, Dict, Iterable, Optional

from .math3d import Vector2, Vector3


def _coerce_point_list(values: Iterable[Any]) -> list[Vector3]:
    return [Vector3.from_any(item) for item in list(values or [])]


def _coerce_cell(value: Any) -> Optional[tuple[int, int]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except Exception:
            return None
    return None


def _coerce_cell_size(value: Any) -> Vector2:
    if isinstance(value, (int, float)):
        size = float(value)
        return Vector2(size, size)
    vector = Vector2.from_any(value)
    if vector.x <= 0.0:
        vector.x = 1.0
    if vector.y <= 0.0:
        vector.y = vector.x
    return vector


def _dedupe_points(points: Iterable[Vector3]) -> list[Vector3]:
    deduped: list[Vector3] = []
    for point in points:
        point = Vector3.from_any(point)
        if deduped:
            previous = deduped[-1]
            if (point - previous).length() <= 0.00001:
                continue
        deduped.append(point)
    return deduped


@dataclass
class NavigationPath:
    path_id: str
    path_type: str = "waypoint"
    points: list[Vector3] = field(default_factory=list)
    lane_id: str = ""
    grid_id: str = ""
    loop: bool = False
    start_cell: Optional[tuple[int, int]] = None
    goal_cell: Optional[tuple[int, int]] = None
    start_position: Optional[Vector3] = None
    goal_position: Optional[Vector3] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, path_id: str, payload: Any) -> "NavigationPath":
        if isinstance(payload, list):
            return cls(path_id=str(path_id), path_type="waypoint", points=_coerce_point_list(payload))

        data = dict(payload or {})
        raw_type = str(data.get("type") or data.get("kind") or "waypoint").strip().lower().replace("-", "_")
        if raw_type in {"points", "waypoints"}:
            raw_type = "waypoint"
        if raw_type in {"td_lane", "tower_defense_lane"}:
            raw_type = "lane"
        path = cls(
            path_id=str(path_id),
            path_type=raw_type or "waypoint",
            points=_coerce_point_list(data.get("points") or data.get("waypoints") or data.get("checkpoints") or []),
            lane_id=str(data.get("lane") or data.get("lane_id") or ""),
            grid_id=str(data.get("grid") or data.get("grid_id") or ""),
            loop=bool(data.get("loop", False)),
            start_cell=_coerce_cell(data.get("start_cell")),
            goal_cell=_coerce_cell(data.get("goal_cell")),
            start_position=Vector3.from_any(data.get("start")) if data.get("start") is not None else None,
            goal_position=Vector3.from_any(data.get("goal")) if data.get("goal") is not None else None,
            metadata={},
        )
        for key, value in data.items():
            if key in {
                "type",
                "kind",
                "points",
                "waypoints",
                "checkpoints",
                "lane",
                "lane_id",
                "grid",
                "grid_id",
                "loop",
                "start_cell",
                "goal_cell",
                "start",
                "goal",
            }:
                continue
            path.metadata[str(key)] = value
        return path

    def to_points(self) -> list[Vector3]:
        return _dedupe_points(self.points)


@dataclass
class TowerDefenseLane:
    lane_id: str
    spawn_position: Vector3 = field(default_factory=Vector3.zero)
    checkpoints: list[Vector3] = field(default_factory=list)
    goal_position: Vector3 = field(default_factory=Vector3.zero)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, lane_id: str, payload: Any) -> "TowerDefenseLane":
        data = dict(payload or {})
        spawn = data.get("spawn")
        if spawn is None:
            spawn = data.get("entry")
        if spawn is None:
            spawn = data.get("start")
        goal = data.get("goal")
        if goal is None:
            goal = data.get("exit")
        if goal is None:
            goal = data.get("end")
        checkpoints = data.get("checkpoints")
        if checkpoints is None:
            checkpoints = data.get("points")
        if checkpoints is None:
            checkpoints = data.get("waypoints")

        lane = cls(
            lane_id=str(lane_id),
            spawn_position=Vector3.from_any(spawn),
            checkpoints=_coerce_point_list(checkpoints or []),
            goal_position=Vector3.from_any(goal),
        )
        for key, value in data.items():
            if key in {"spawn", "entry", "start", "goal", "exit", "end", "checkpoints", "points", "waypoints"}:
                continue
            lane.metadata[str(key)] = value
        return lane

    def to_points(self) -> list[Vector3]:
        return _dedupe_points([self.spawn_position, *self.checkpoints, self.goal_position])


@dataclass
class GridNavigationMap:
    grid_id: str
    width: int
    height: int
    cell_size: Vector2 = field(default_factory=lambda: Vector2(1.0, 1.0))
    origin: Vector3 = field(default_factory=Vector3.zero)
    plane: str = "xz"
    allow_diagonal: bool = False
    blocked: set[tuple[int, int]] = field(default_factory=set)
    weights: Dict[tuple[int, int], float] = field(default_factory=dict)
    start_cell: Optional[tuple[int, int]] = None
    goal_cell: Optional[tuple[int, int]] = None

    @classmethod
    def from_payload(cls, grid_id: str, payload: Any) -> "GridNavigationMap":
        data = dict(payload or {})
        blocked = {
            cell
            for item in list(data.get("blocked") or data.get("blocked_cells") or [])
            if (cell := _coerce_cell(item)) is not None
        }
        weights: Dict[tuple[int, int], float] = {}
        raw_weights = data.get("weights") or {}
        if isinstance(raw_weights, dict):
            for key, value in raw_weights.items():
                if isinstance(key, str) and "," in key:
                    parts = key.split(",", 1)
                    cell = _coerce_cell(parts)
                else:
                    cell = _coerce_cell(key)
                if cell is not None:
                    try:
                        weights[cell] = max(0.001, float(value))
                    except Exception:
                        continue

        return cls(
            grid_id=str(grid_id),
            width=max(1, int(data.get("width", 1))),
            height=max(1, int(data.get("height", 1))),
            cell_size=_coerce_cell_size(data.get("cell_size", 1.0)),
            origin=Vector3.from_any(data.get("origin")),
            plane=str(data.get("plane") or "xz").strip().lower(),
            allow_diagonal=bool(data.get("allow_diagonal", False)),
            blocked=blocked,
            weights=weights,
            start_cell=_coerce_cell(data.get("start_cell")),
            goal_cell=_coerce_cell(data.get("goal_cell")),
        )

    def contains(self, cell: tuple[int, int]) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def is_walkable(self, cell: tuple[int, int]) -> bool:
        return self.contains(cell) and cell not in self.blocked

    def default_start_position(self) -> Vector3:
        return self.cell_to_world(self.start_cell or (0, 0))

    def default_goal_position(self) -> Vector3:
        fallback = (self.width - 1, self.height - 1)
        return self.cell_to_world(self.goal_cell or fallback)

    def world_to_cell(self, position: Any) -> tuple[int, int]:
        point = Vector3.from_any(position)
        axis_a = point.x - self.origin.x
        if self.plane == "xy":
            axis_b = point.y - self.origin.y
        else:
            axis_b = point.z - self.origin.z
        return (
            int(round(axis_a / max(0.00001, self.cell_size.x))),
            int(round(axis_b / max(0.00001, self.cell_size.y))),
        )

    def cell_to_world(self, cell: tuple[int, int]) -> Vector3:
        x = self.origin.x + (cell[0] * self.cell_size.x)
        second_axis = cell[1] * self.cell_size.y
        if self.plane == "xy":
            return Vector3(x, self.origin.y + second_axis, self.origin.z)
        return Vector3(x, self.origin.y, self.origin.z + second_axis)

    def neighbors(self, cell: tuple[int, int], *, allow_diagonal: Optional[bool] = None) -> list[tuple[int, int]]:
        use_diagonal = self.allow_diagonal if allow_diagonal is None else bool(allow_diagonal)
        offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if use_diagonal:
            offsets.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
        results: list[tuple[int, int]] = []
        for dx, dy in offsets:
            candidate = (cell[0] + dx, cell[1] + dy)
            if self.is_walkable(candidate):
                results.append(candidate)
        return results

    def _movement_cost(self, current: tuple[int, int], neighbor: tuple[int, int]) -> float:
        diagonal = current[0] != neighbor[0] and current[1] != neighbor[1]
        base_cost = math.sqrt(2.0) if diagonal else 1.0
        return base_cost * self.weights.get(neighbor, 1.0)

    def _heuristic(self, cell: tuple[int, int], goal: tuple[int, int]) -> float:
        dx = abs(cell[0] - goal[0])
        dy = abs(cell[1] - goal[1])
        if self.allow_diagonal:
            return max(dx, dy)
        return dx + dy

    def find_path(
        self,
        *,
        start_position: Any = None,
        goal_position: Any = None,
        start_cell: Any = None,
        goal_cell: Any = None,
        allow_diagonal: Optional[bool] = None,
    ) -> list[Vector3]:
        resolved_start = _coerce_cell(start_cell)
        resolved_goal = _coerce_cell(goal_cell)
        if resolved_start is None:
            resolved_start = self.world_to_cell(start_position) if start_position is not None else self.start_cell or (0, 0)
        if resolved_goal is None:
            if goal_position is not None:
                resolved_goal = self.world_to_cell(goal_position)
            else:
                resolved_goal = self.goal_cell or (self.width - 1, self.height - 1)

        if not self.is_walkable(resolved_start) or not self.is_walkable(resolved_goal):
            return []

        frontier: list[tuple[float, int, tuple[int, int]]] = []
        heapq.heappush(frontier, (0.0, 0, resolved_start))
        sequence = 1
        came_from: Dict[tuple[int, int], Optional[tuple[int, int]]] = {resolved_start: None}
        cost_so_far: Dict[tuple[int, int], float] = {resolved_start: 0.0}
        diagonal = self.allow_diagonal if allow_diagonal is None else bool(allow_diagonal)

        while frontier:
            _, _, current = heapq.heappop(frontier)
            if current == resolved_goal:
                break
            for neighbor in self.neighbors(current, allow_diagonal=diagonal):
                new_cost = cost_so_far[current] + self._movement_cost(current, neighbor)
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    priority = new_cost + self._heuristic(neighbor, resolved_goal)
                    heapq.heappush(frontier, (priority, sequence, neighbor))
                    sequence += 1
                    came_from[neighbor] = current

        if resolved_goal not in came_from:
            return []

        cells: list[tuple[int, int]] = []
        cursor: Optional[tuple[int, int]] = resolved_goal
        while cursor is not None:
            cells.append(cursor)
            cursor = came_from.get(cursor)
        cells.reverse()
        return [self.cell_to_world(cell) for cell in cells]


@dataclass
class NavigationServer:
    paths: Dict[str, NavigationPath] = field(default_factory=dict)
    grids: Dict[str, GridNavigationMap] = field(default_factory=dict)
    lanes: Dict[str, TowerDefenseLane] = field(default_factory=dict)

    def clear(self) -> None:
        self.paths.clear()
        self.grids.clear()
        self.lanes.clear()

    def register_path(self, definition: NavigationPath) -> None:
        self.paths[str(definition.path_id)] = definition

    def register_grid(self, grid: GridNavigationMap) -> None:
        self.grids[str(grid.grid_id)] = grid

    def register_lane(self, lane: TowerDefenseLane) -> None:
        self.lanes[str(lane.lane_id)] = lane

    def load_payload(self, payload: Dict[str, Any]) -> None:
        raw_grids = payload.get("grids") or payload.get("navigation_grids") or {}
        if isinstance(raw_grids, dict):
            for grid_id, value in raw_grids.items():
                self.register_grid(GridNavigationMap.from_payload(str(grid_id), value))

        raw_lanes = payload.get("lanes") or payload.get("tower_defense_lanes") or {}
        if isinstance(raw_lanes, dict):
            for lane_id, value in raw_lanes.items():
                self.register_lane(TowerDefenseLane.from_payload(str(lane_id), value))

        raw_paths = payload.get("paths") or payload.get("navigation_paths") or {}
        if isinstance(raw_paths, dict):
            for path_id, value in raw_paths.items():
                self.register_path(NavigationPath.from_payload(str(path_id), value))

    def get_path(self, path_id: str) -> Optional[NavigationPath]:
        key = str(path_id or "").strip()
        if not key:
            return None
        if key in self.paths:
            return self.paths[key]
        if key in self.lanes:
            return NavigationPath(path_id=key, path_type="lane", lane_id=key)
        if key in self.grids:
            return NavigationPath(path_id=key, path_type="grid", grid_id=key)
        return None

    def has_path(self, path_id: str) -> bool:
        return self.get_path(path_id) is not None

    def resolve_path_points(self, path_id: str, *, start_position: Any = None) -> list[Vector3]:
        definition = self.get_path(path_id)
        if definition is None:
            return []
        if definition.path_type == "waypoint":
            return definition.to_points()
        if definition.path_type == "lane":
            if definition.points:
                return definition.to_points()
            lane = self.lanes.get(definition.lane_id or definition.path_id)
            if lane is None:
                return []
            return lane.to_points()
        if definition.path_type == "grid":
            if definition.points:
                return definition.to_points()
            grid = self.grids.get(definition.grid_id or definition.path_id)
            if grid is None:
                return []
            return grid.find_path(
                start_position=start_position if start_position is not None else definition.start_position or grid.default_start_position(),
                goal_position=definition.goal_position or grid.default_goal_position(),
                start_cell=definition.start_cell or grid.start_cell,
                goal_cell=definition.goal_cell or grid.goal_cell,
                allow_diagonal=definition.metadata.get("allow_diagonal"),
            )
        return definition.to_points()

    def export_path_points(self) -> Dict[str, list[list[float]]]:
        exported: Dict[str, list[list[float]]] = {}
        keys = set(self.paths.keys()) | set(self.lanes.keys())
        for path_id in sorted(keys):
            points = self.resolve_path_points(path_id)
            if points:
                exported[path_id] = [point.to_list() for point in points]
        return exported
