"""Save and load state support for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json

from .serialization import scene_from_dict


SAVE_DATA_VERSION = 1


@dataclass
class SaveDataManager:
    project_root: Path
    slots_dir: str = "save_data"

    def __init__(self, project_root: Path, *, slots_dir: str = "save_data") -> None:
        self.project_root = Path(project_root)
        self.slots_dir = str(slots_dir or "save_data")

    @property
    def save_root(self) -> Path:
        root = self.project_root / self.slots_dir
        root.mkdir(parents=True, exist_ok=True)
        return root

    def capture_state(
        self,
        scene_tree: Any,
        *,
        gameplay: Any = None,
        localization: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": SAVE_DATA_VERSION,
            "scene": scene_tree.root.to_dict(),
            "frame_index": int(getattr(scene_tree, "current_frame", 0)),
            "metadata": dict(metadata or {}),
        }
        if gameplay is not None and hasattr(gameplay, "export_state"):
            payload["gameplay"] = gameplay.export_state()
        if localization is not None and hasattr(localization, "current_locale"):
            payload["localization"] = {"current_locale": str(localization.current_locale)}
        return payload

    def restore_state(
        self,
        scene_tree: Any,
        payload: Dict[str, Any],
        *,
        gameplay: Any = None,
        localization: Any = None,
    ) -> Dict[str, Any]:
        scene_payload = dict(payload.get("scene") or {})
        if scene_payload:
            scene_tree.change_scene(scene_from_dict(scene_payload))
        scene_tree.current_frame = int(payload.get("frame_index", 0))
        if gameplay is not None and hasattr(gameplay, "restore_state"):
            gameplay.restore_state(dict(payload.get("gameplay") or {}))
        if localization is not None:
            locale_payload = dict(payload.get("localization") or {})
            if locale_payload.get("current_locale"):
                localization.set_locale(str(locale_payload["current_locale"]))
        return {
            "scene_id": getattr(scene_tree.root, "scene_id", ""),
            "frame_index": scene_tree.current_frame,
        }

    def save_slot(
        self,
        slot_name: str,
        scene_tree: Any,
        *,
        gameplay: Any = None,
        localization: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        path = self.save_root / f"{str(slot_name).strip() or 'slot_1'}.save.json"
        payload = self.capture_state(scene_tree, gameplay=gameplay, localization=localization, metadata=metadata)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load_slot(self, slot_name: str) -> Dict[str, Any]:
        path = self.save_root / f"{str(slot_name).strip() or 'slot_1'}.save.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def list_slots(self) -> list[str]:
        return sorted(path.stem.replace(".save", "") for path in self.save_root.glob("*.save.json"))
