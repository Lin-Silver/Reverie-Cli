from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import random

from .base import BaseTool, ToolResult


class LevelDesignTool(BaseTool):
    name = "level_design"
    description = "Advanced level design: generate layouts, validate pathing, analyze difficulty, spatial analysis, export configs."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate_layout", "generate_rooms", "check_logic", "analyze_difficulty", "validate_path", "analyze_flow", "export_config", "npc_placement", "spatial_analysis"],
                "description": "Level design action"
            },
            "level_type": {
                "type": "string",
                "enum": ["platformer", "dungeon", "open_world", "arena"],
                "description": "Type of level"
            },
            "width": {"type": "integer", "description": "Width of layout grid"},
            "height": {"type": "integer", "description": "Height of layout grid"},
            "seed": {"type": "integer", "description": "Random seed"},
            "difficulty": {"type": "integer", "description": "Difficulty level 1-10"},
            "layout": {"type": "string", "description": "Layout string for check/analyze"},
            "config_path": {"type": "string", "description": "Config file path for export or analysis"},
            "output_path": {"type": "string", "description": "Output path for export_config"},
            "room_count": {"type": "integer", "description": "Room count for dungeon generation"},
            "min_room_size": {"type": "integer", "description": "Min room size"},
            "max_room_size": {"type": "integer", "description": "Max room size"}
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        level_type = kwargs.get("level_type", "dungeon")
        width = int(kwargs.get("width", 20))
        height = int(kwargs.get("height", 10))
        seed = kwargs.get("seed")
        difficulty = int(kwargs.get("difficulty", 5))

        if seed is not None:
            random.seed(seed)

        if action == "generate_layout":
            layout, config = self._generate_layout(level_type, width, height, difficulty)
            return ToolResult.ok(layout, {"layout": layout, "config": config})

        if action == "generate_rooms":
            room_count = int(kwargs.get("room_count", 6))
            min_room = int(kwargs.get("min_room_size", 3))
            max_room = int(kwargs.get("max_room_size", 6))
            layout, config = self._generate_rooms(width, height, room_count, min_room, max_room)
            return ToolResult.ok(layout, {"layout": layout, "config": config})

        if action == "check_logic":
            layout = kwargs.get("layout") or self._load_layout_from_config(kwargs.get("config_path"))
            if not layout:
                return ToolResult.fail("layout or config_path is required for check_logic")
            issues = self._check_logic(layout)
            output = "Logic check passed." if not issues else "Logic issues:\n" + "\n".join(issues)
            return ToolResult.ok(output, {"issues": issues})

        if action == "analyze_difficulty":
            layout = kwargs.get("layout") or self._load_layout_from_config(kwargs.get("config_path"))
            if not layout:
                return ToolResult.fail("layout or config_path is required for analyze_difficulty")
            analysis = self._analyze_difficulty(layout)
            return ToolResult.ok(analysis)

        if action == "validate_path":
            layout = kwargs.get("layout") or self._load_layout_from_config(kwargs.get("config_path"))
            if not layout:
                return ToolResult.fail("layout or config_path is required for validate_path")
            path_len = self._path_length(layout)
            if path_len is None:
                return ToolResult.ok("No valid path from S to E.", {"path_length": None})
            return ToolResult.ok(f"Valid path length: {path_len}", {"path_length": path_len})

        if action == "analyze_flow":
            layout = kwargs.get("layout") or self._load_layout_from_config(kwargs.get("config_path"))
            if not layout:
                return ToolResult.fail("layout or config_path is required for analyze_flow")
            report = self._analyze_flow(layout)
            return ToolResult.ok(report)

        if action == "export_config":
            layout = kwargs.get("layout")
            if not layout:
                return ToolResult.fail("layout is required for export_config")
            output_path = self._resolve_path(kwargs.get("output_path") or "level_config.json")
            config = self._layout_to_config(layout)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            return ToolResult.ok(f"Exported level config to {output_path}", {"output_path": str(output_path)})

        return ToolResult.fail(f"Unknown action: {action}")

    def _generate_layout(self, level_type: str, width: int, height: int, difficulty: int):
        grid = [["." for _ in range(width)] for _ in range(height)]
        grid[0][0] = "S"
        grid[height - 1][width - 1] = "E"

        obstacle_count = max(1, int(width * height * (0.1 + difficulty * 0.02)))
        enemy_count = max(1, int(width * height * (0.05 + difficulty * 0.01)))
        treasure_count = max(1, int(width * height * 0.03))

        self._place_random(grid, "#", obstacle_count)
        self._place_random(grid, "M", enemy_count)
        if level_type in ["dungeon", "arena"]:
            self._place_random(grid, "T", treasure_count)

        layout = "\n".join("".join(row) for row in grid)
        config = self._layout_to_config(layout)
        return layout, config

    def _generate_rooms(self, width: int, height: int, room_count: int, min_room: int, max_room: int):
        grid = [["#" for _ in range(width)] for _ in range(height)]
        rooms = []
        if room_count <= 0:
            room_count = 1
        for _ in range(room_count):
            w = random.randint(min_room, max_room)
            h = random.randint(min_room, max_room)
            x = random.randint(1, max(1, width - w - 2))
            y = random.randint(1, max(1, height - h - 2))
            room = (x, y, w, h)
            rooms.append(room)
            for iy in range(y, y + h):
                for ix in range(x, x + w):
                    grid[iy][ix] = "."
        for i in range(1, len(rooms)):
            x1, y1, w1, h1 = rooms[i - 1]
            x2, y2, w2, h2 = rooms[i]
            cx1, cy1 = x1 + w1 // 2, y1 + h1 // 2
            cx2, cy2 = x2 + w2 // 2, y2 + h2 // 2
            if random.random() < 0.5:
                self._carve_hallway(grid, cx1, cx2, cy1, horizontal=True)
                self._carve_hallway(grid, cy1, cy2, cx2, horizontal=False)
            else:
                self._carve_hallway(grid, cy1, cy2, cx1, horizontal=False)
                self._carve_hallway(grid, cx1, cx2, cy2, horizontal=True)
        grid[rooms[0][1] + 1][rooms[0][0] + 1] = "S"
        last = rooms[-1]
        grid[last[1] + 1][last[0] + 1] = "E"
        layout = "\n".join("".join(row) for row in grid)
        return layout, self._layout_to_config(layout)

    def _carve_hallway(self, grid: List[List[str]], start: int, end: int, fixed: int, horizontal: bool):
        step = 1 if end >= start else -1
        for i in range(start, end + step, step):
            if horizontal:
                grid[fixed][i] = "."
            else:
                grid[i][fixed] = "."

    def _place_random(self, grid: List[List[str]], token: str, count: int):
        height = len(grid)
        width = len(grid[0])
        placed = 0
        while placed < count:
            y = random.randint(0, height - 1)
            x = random.randint(0, width - 1)
            if grid[y][x] == ".":
                grid[y][x] = token
                placed += 1

    def _check_logic(self, layout: str) -> List[str]:
        issues = []
        if "S" not in layout:
            issues.append("Missing start point (S).")
        if "E" not in layout:
            issues.append("Missing exit point (E).")
        return issues

    def _analyze_difficulty(self, layout: str) -> str:
        total = len(layout.replace("\n", ""))
        enemies = layout.count("M")
        obstacles = layout.count("#")
        density = (enemies + obstacles) / max(total, 1)
        path_len = self._path_length(layout)
        return (
            "Difficulty Analysis:\n"
            f"- enemy count: {enemies}\n"
            f"- obstacle count: {obstacles}\n"
            f"- density: {density:.2f}\n"
            f"- path length: {path_len if path_len is not None else 'N/A'}"
        )

    def _analyze_flow(self, layout: str) -> str:
        grid = layout.splitlines()
        dead_ends = 0
        walkable = 0
        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell in [".", "S", "E", "T", "M"]:
                    walkable += 1
                    neighbors = self._walkable_neighbors(grid, x, y)
                    if neighbors <= 1:
                        dead_ends += 1
        ratio = dead_ends / max(walkable, 1)
        return (
            "Flow Analysis:\n"
            f"- walkable tiles: {walkable}\n"
            f"- dead ends: {dead_ends}\n"
            f"- dead end ratio: {ratio:.2f}"
        )

    def _layout_to_config(self, layout: str) -> Dict[str, Any]:
        lines = layout.splitlines()
        return {
            "width": len(lines[0]) if lines else 0,
            "height": len(lines),
            "layout": lines
        }

    def _load_layout_from_config(self, config_path: Optional[str]) -> Optional[str]:
        if not config_path:
            return None
        path = self._resolve_path(config_path)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = data.get("layout")
        if isinstance(lines, list):
            return "\n".join(lines)
        return None

    def _path_length(self, layout: str) -> Optional[int]:
        grid = layout.splitlines()
        start = end = None
        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell == "S":
                    start = (x, y)
                elif cell == "E":
                    end = (x, y)
        if not start or not end:
            return None
        queue = [start]
        visited = {start: 0}
        while queue:
            x, y = queue.pop(0)
            if (x, y) == end:
                return visited[(x, y)]
            for nx, ny in self._neighbors(grid, x, y):
                if (nx, ny) not in visited:
                    visited[(nx, ny)] = visited[(x, y)] + 1
                    queue.append((nx, ny))
        return None

    def _neighbors(self, grid: List[str], x: int, y: int) -> List[tuple]:
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        results = []
        for nx, ny in candidates:
            if 0 <= ny < len(grid) and 0 <= nx < len(grid[ny]):
                if grid[ny][nx] != "#":
                    results.append((nx, ny))
        return results

    def _walkable_neighbors(self, grid: List[str], x: int, y: int) -> int:
        count = 0
        for nx, ny in self._neighbors(grid, x, y):
            count += 1
        return count

    def _resolve_path(self, raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)
