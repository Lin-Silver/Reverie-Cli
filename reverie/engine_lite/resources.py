"""Resource loading and dependency tracking for Reverie Engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, DefaultDict, Dict, Iterable, Optional
import json

import yaml


@dataclass
class ResourceDescriptor:
    path: str
    loader: str
    suffix: str
    exists: bool
    size: int


class ResourceManager:
    """Caches parsed resources and records dependency relationships."""

    CACHE_REUSE = "reuse"
    CACHE_RELOAD = "reload"
    CACHE_BYPASS = "bypass"

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.cache: Dict[str, Any] = {}
        self.resource_records: Dict[str, ResourceDescriptor] = {}
        self.dependencies: DefaultDict[str, set[str]] = defaultdict(set)
        self.resource_remaps = self._load_resource_remaps()
        self._loaders: Dict[str, Callable[[Path], Any]] = {}
        self._loader_names: Dict[str, str] = {}
        self._register_builtin_loaders()

    def resolve(self, raw_path: str | Path) -> Path:
        path = Path(self.remap_path(raw_path))
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def register_dependency(self, owner: str, dependency: str) -> None:
        normalized_owner = str(owner).strip()
        normalized_dependency = str(dependency).strip().replace("\\", "/")
        if normalized_owner and normalized_dependency:
            self.dependencies[normalized_owner].add(normalized_dependency)

    def register_loader(self, loader_name: str, suffixes: Iterable[str], loader: Callable[[Path], Any]) -> None:
        for suffix in suffixes:
            normalized = str(suffix).strip().lower()
            if not normalized:
                continue
            if not normalized.startswith("."):
                normalized = f".{normalized}"
            self._loaders[normalized] = loader
            self._loader_names[normalized] = str(loader_name).strip() or "custom"

    def remap_path(self, raw_path: str | Path) -> str:
        text = str(raw_path).replace("\\", "/").strip()
        if not text:
            return text
        return self.resource_remaps.get(text, self.resource_remaps.get(text.lstrip("./"), text))

    def exists(self, raw_path: str | Path) -> bool:
        return self.resolve(raw_path).exists()

    def load(
        self,
        raw_path: str | Path,
        *,
        cache_mode: str = CACHE_REUSE,
        owner: str = "",
    ) -> Any:
        path = self.resolve(raw_path)
        cache_key = str(path)
        cache_mode = str(cache_mode or self.CACHE_REUSE).strip().lower()
        if cache_mode == self.CACHE_REUSE and cache_key in self.cache:
            if owner:
                self.register_dependency(owner, self._project_relative(path))
            return self.cache[cache_key]

        if not path.exists():
            raise FileNotFoundError(f"Resource not found: {path}")

        loader, loader_name = self._select_loader(path)
        payload = loader(path)
        descriptor = ResourceDescriptor(
            path=self._project_relative(path),
            loader=loader_name,
            suffix=path.suffix.lower(),
            exists=True,
            size=path.stat().st_size if path.is_file() else 0,
        )
        self.resource_records[cache_key] = descriptor
        if cache_mode != self.CACHE_BYPASS:
            self.cache[cache_key] = payload
        if owner:
            self.register_dependency(owner, descriptor.path)
        return payload

    def summary(self) -> dict:
        return {
            "cached_resources": len(self.cache),
            "registered_loaders": sorted(set(self._loader_names.values())),
            "resource_remaps": dict(self.resource_remaps),
            "dependency_roots": len(self.dependencies),
            "resources": {key: descriptor.__dict__ for key, descriptor in self.resource_records.items()},
            "dependencies": {key: sorted(value) for key, value in self.dependencies.items()},
        }

    def dependency_graph(self) -> dict:
        """Return a structured owner-to-resource dependency graph."""
        resources = sorted(
            {
                dependency
                for dependency_set in self.dependencies.values()
                for dependency in dependency_set
            }
        )
        reverse: DefaultDict[str, set[str]] = defaultdict(set)
        edges: list[dict[str, str]] = []

        for owner, dependency_set in sorted(self.dependencies.items()):
            for dependency in sorted(dependency_set):
                reverse[dependency].add(owner)
                edges.append({"from": owner, "to": dependency})

        return {
            "owners": sorted(self.dependencies.keys()),
            "resources": resources,
            "edges": edges,
            "dependencies": {key: sorted(value) for key, value in self.dependencies.items()},
            "reverse_dependencies": {key: sorted(value) for key, value in reverse.items()},
        }

    def export_dependency_graph(self, path: str | Path) -> Path:
        """Persist the dependency graph as JSON for tooling and inspection."""
        target = Path(path)
        if not target.is_absolute():
            target = self.project_root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.dependency_graph(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    def load_optional(self, raw_path: str | Path, default: Any = None) -> Any:
        if not self.exists(raw_path):
            return default
        return self.load(raw_path)

    def load_many(
        self,
        paths: Iterable[str | Path],
        *,
        cache_mode: str = CACHE_REUSE,
        owner: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for raw_path in paths:
            normalized = str(raw_path)
            payload[normalized] = self.load(raw_path, cache_mode=cache_mode, owner=owner)
        return payload

    def clear_cache(self, raw_path: str | Path | None = None) -> None:
        if raw_path is None:
            self.cache.clear()
            return
        key = str(self.resolve(raw_path))
        self.cache.pop(key, None)

    def load_content_bundle(self) -> Dict[str, Any]:
        bundle: Dict[str, Any] = {}
        for relative in ["data/content", "data/live2d"]:
            root = self.project_root / relative
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                    continue
                key = str(path.relative_to(self.project_root)).replace("\\", "/")
                bundle[key] = self.load(path, owner=f"bundle:{relative}")
        return bundle

    def discover_assets(self, relative_root: str | Path = "assets") -> Dict[str, list[str]]:
        root = self.resolve(relative_root)
        payload: Dict[str, list[str]] = {}
        if not root.exists():
            return payload
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            group = path.suffix.lower().lstrip(".") or "other"
            payload.setdefault(group, []).append(str(path.relative_to(self.project_root)).replace("\\", "/"))
        return payload

    def _register_builtin_loaders(self) -> None:
        self.register_loader("json", [".json"], self._load_json)
        self.register_loader("yaml", [".yaml", ".yml"], self._load_yaml)
        self.register_loader("text", [".txt", ".md", ".glsl", ".vert", ".frag"], self._load_text)

    def _select_loader(self, path: Path) -> tuple[Callable[[Path], Any], str]:
        suffix = path.suffix.lower()
        if suffix in self._loaders:
            return self._loaders[suffix], self._loader_names[suffix]
        return self._load_metadata, "metadata"

    def _load_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_yaml(self, path: Path) -> Any:
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def _load_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _load_metadata(self, path: Path) -> Dict[str, Any]:
        return {
            "path": str(path),
            "suffix": path.suffix.lower(),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() and path.is_file() else 0,
        }

    def _project_relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _load_resource_remaps(self) -> Dict[str, str]:
        remap_path = self.project_root / "data/config/resource_remap.yaml"
        if not remap_path.exists():
            return {}
        payload = yaml.safe_load(remap_path.read_text(encoding="utf-8")) or {}
        if isinstance(payload, dict) and isinstance(payload.get("remaps"), dict):
            payload = payload.get("remaps") or {}
        if not isinstance(payload, dict):
            return {}
        remaps: Dict[str, str] = {}
        for key, value in payload.items():
            source = str(key).replace("\\", "/").strip()
            target = str(value).replace("\\", "/").strip()
            if source and target:
                remaps[source] = target
        return remaps
