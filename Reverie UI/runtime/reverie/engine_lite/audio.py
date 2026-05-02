"""Audio system for Reverie Engine Lite."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import pyglet
    from pyglet.media import Player, load as load_audio
except ImportError:  # pragma: no cover - optional dependency
    pyglet = None
    Player = None
    load_audio = None


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass
class AudioStream:
    """Represents a loaded audio resource."""

    path: str
    source: Any = None
    duration: float = 0.0

    def is_loaded(self) -> bool:
        return self.source is not None


@dataclass
class AudioBus:
    """A lightweight Godot-style audio bus."""

    name: str
    parent: Optional[str] = None
    volume: float = 1.0
    muted: bool = False
    solo: bool = False
    send: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent or "",
            "volume": round(self.volume, 4),
            "muted": self.muted,
            "solo": self.solo,
            "send": self.send or "",
            "tags": list(self.tags),
        }


@dataclass
class AudioPlayer:
    """Audio player instance."""

    stream: Optional[AudioStream] = None
    player: Any = None
    volume: float = 1.0
    pitch: float = 1.0
    loop: bool = False
    playing: bool = False
    position: float = 0.0
    bus: str = "Master"
    category: str = "sfx"

    def play(self) -> None:
        """Start or resume playback."""
        if self.player and not self.playing:
            self.player.play()
            self.playing = True

    def pause(self) -> None:
        """Pause playback."""
        if self.player and self.playing:
            self.player.pause()
            self.playing = False

    def stop(self) -> None:
        """Stop playback and reset position."""
        if self.player:
            self.player.pause()
            self.player.seek(0)
            self.playing = False
            self.position = 0.0

    def set_volume(self, volume: float) -> None:
        """Set local playback volume (0.0 to 1.0)."""
        self.volume = _clamp_volume(volume)

    def update(self, delta: float) -> None:
        """Update player state."""
        if self.player and self.playing:
            if hasattr(self.player, "time"):
                self.position = self.player.time
            if not self.player.playing:
                if self.loop:
                    self.player.seek(0)
                    self.player.play()
                else:
                    self.playing = False


class AudioManager:
    """Manages audio resources, buses, and playback."""

    DEFAULT_BUSES = (
        ("Master", None, ["master"]),
        ("Music", "Master", ["music"]),
        ("SFX", "Master", ["sfx"]),
        ("UI", "SFX", ["ui"]),
        ("Voice", "Master", ["voice"]),
        ("Ambient", "Master", ["ambient"]),
    )

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.streams: Dict[str, AudioStream] = {}
        self.players: Dict[str, AudioPlayer] = {}
        self.buses: Dict[str, AudioBus] = {}
        self.master_volume: float = 1.0
        self.music_volume: float = 1.0
        self.sfx_volume: float = 1.0
        self._initialized = pyglet is not None
        for name, parent, tags in self.DEFAULT_BUSES:
            self.create_bus(name, parent=parent, tags=tags)

    def is_available(self) -> bool:
        """Check if audio system is available."""
        return self._initialized

    def create_bus(
        self,
        name: str,
        *,
        parent: Optional[str] = "Master",
        volume: float = 1.0,
        muted: bool = False,
        solo: bool = False,
        send: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> AudioBus:
        bus_name = str(name or "Master").strip() or "Master"
        if bus_name == "Master":
            parent = None
        elif parent and parent not in self.buses:
            parent = "Master"
        bus = AudioBus(
            name=bus_name,
            parent=parent,
            volume=_clamp_volume(volume),
            muted=bool(muted),
            solo=bool(solo),
            send=str(send).strip() or None if send else None,
            tags=list(tags or []),
        )
        self.buses[bus_name] = bus
        self._refresh_player_volumes()
        return bus

    def ensure_bus(self, name: str) -> AudioBus:
        bus_name = str(name or "Master").strip() or "Master"
        return self.buses.get(bus_name) or self.create_bus(bus_name)

    def set_bus_volume(self, name: str, volume: float) -> bool:
        bus = self.buses.get(str(name or "").strip())
        if not bus:
            return False
        bus.volume = _clamp_volume(volume)
        self._refresh_player_volumes()
        return True

    def mute_bus(self, name: str, muted: bool = True) -> bool:
        bus = self.buses.get(str(name or "").strip())
        if not bus:
            return False
        bus.muted = bool(muted)
        self._refresh_player_volumes()
        return True

    def solo_bus(self, name: str, solo: bool = True) -> bool:
        bus = self.buses.get(str(name or "").strip())
        if not bus:
            return False
        bus.solo = bool(solo)
        self._refresh_player_volumes()
        return True

    def set_bus_send(self, name: str, send: Optional[str]) -> bool:
        bus = self.buses.get(str(name or "").strip())
        if not bus:
            return False
        target = str(send).strip() if send else ""
        bus.send = target if target and target in self.buses and target != bus.name else None
        return True

    def get_bus(self, name: str) -> Optional[AudioBus]:
        return self.buses.get(str(name or "").strip())

    def load_stream(self, audio_id: str, path: str | Path) -> bool:
        """Load an audio file."""
        if not self._initialized or not load_audio:
            return False
        if audio_id in self.streams:
            return True
        try:
            full_path = self.project_root / path
            if not full_path.exists():
                return False
            source = load_audio(str(full_path), streaming=False)
            stream = AudioStream(
                path=str(path),
                source=source,
                duration=source.duration if hasattr(source, "duration") else 0.0,
            )
            self.streams[audio_id] = stream
            return True
        except Exception:
            return False

    def unload_stream(self, audio_id: str) -> None:
        """Unload an audio stream."""
        if audio_id in self.streams:
            for player_id, player in list(self.players.items()):
                if player.stream and player.stream == self.streams[audio_id]:
                    player.stop()
                    del self.players[player_id]
            del self.streams[audio_id]

    def _bus_for_category(self, category: str, requested_bus: Optional[str]) -> str:
        if requested_bus and requested_bus in self.buses:
            return requested_bus
        normalized = str(category or "sfx").strip().lower()
        if normalized == "music":
            return "Music"
        if normalized == "voice":
            return "Voice"
        if normalized == "ui":
            return "UI"
        if normalized == "ambient":
            return "Ambient"
        return "SFX"

    def create_player(
        self,
        player_id: str,
        audio_id: str,
        *,
        loop: bool = False,
        volume: float = 1.0,
        bus: Optional[str] = None,
        category: str = "sfx",
    ) -> Optional[AudioPlayer]:
        """Create a new audio player."""
        if audio_id not in self.streams:
            return None
        stream = self.streams[audio_id]
        if not stream.is_loaded() and self._initialized:
            return None

        player_obj = None
        if self._initialized and Player and stream.is_loaded():
            try:
                player_obj = Player()
                player_obj.queue(stream.source)
            except Exception:
                player_obj = None

        resolved_bus = self._bus_for_category(category, bus)
        audio_player = AudioPlayer(
            stream=stream,
            player=player_obj,
            volume=_clamp_volume(volume),
            loop=loop,
            bus=resolved_bus,
            category=str(category or "sfx").strip().lower(),
        )
        self.players[player_id] = audio_player
        self._apply_player_volume(audio_player)
        return audio_player

    def assign_player_bus(self, player_id: str, bus: str) -> bool:
        player = self.players.get(player_id)
        if not player:
            return False
        player.bus = self.ensure_bus(bus).name
        self._apply_player_volume(player)
        return True

    def get_player(self, player_id: str) -> Optional[AudioPlayer]:
        """Get an existing audio player."""
        return self.players.get(player_id)

    def play(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if player:
            player.play()
            return True
        return False

    def play_oneshot(
        self,
        audio_id: str,
        *,
        volume: float = 1.0,
        bus: Optional[str] = None,
        category: str = "sfx",
    ) -> bool:
        """Play a sound effect once (fire and forget)."""
        if audio_id not in self.streams:
            return False
        import uuid

        player_id = f"oneshot_{uuid.uuid4().hex[:8]}"
        player = self.create_player(player_id, audio_id, loop=False, volume=volume, bus=bus, category=category)
        if player:
            player.play()
            return True
        return False

    def stop(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if player:
            player.stop()
            return True
        return False

    def stop_all(self) -> None:
        for player in self.players.values():
            player.stop()

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = _clamp_volume(volume)
        self._refresh_player_volumes()

    def set_music_volume(self, volume: float) -> None:
        self.music_volume = _clamp_volume(volume)
        self._refresh_player_volumes()

    def set_sfx_volume(self, volume: float) -> None:
        self.sfx_volume = _clamp_volume(volume)
        self._refresh_player_volumes()

    def _category_scalar(self, player: AudioPlayer) -> float:
        if player.category == "music" or player.bus == "Music":
            return self.music_volume
        if player.category in {"voice", "ambient"}:
            return 1.0
        return self.sfx_volume

    def _bus_chain(self, bus_name: str) -> list[AudioBus]:
        chain: list[AudioBus] = []
        visited: set[str] = set()
        current = self.buses.get(bus_name) or self.buses.get("Master")
        while current and current.name not in visited:
            chain.append(current)
            visited.add(current.name)
            current = self.buses.get(current.parent or "") if current.parent else None
        if not chain and "Master" in self.buses:
            chain.append(self.buses["Master"])
        return chain

    def _solo_buses(self) -> set[str]:
        return {name for name, bus in self.buses.items() if bus.solo}

    def _is_player_audible(self, player: AudioPlayer) -> bool:
        solo_buses = self._solo_buses()
        chain_names = {bus.name for bus in self._bus_chain(player.bus)}
        if any(bus.muted for bus in self._bus_chain(player.bus)):
            return False
        if solo_buses and not chain_names.intersection(solo_buses):
            return False
        return True

    def get_effective_volume(self, player_id: str) -> float:
        player = self.players.get(player_id)
        if not player:
            return 0.0
        if not self._is_player_audible(player):
            return 0.0
        effective = _clamp_volume(player.volume) * self.master_volume * self._category_scalar(player)
        for bus in self._bus_chain(player.bus):
            effective *= bus.volume
            if bus.send and bus.send in self.buses:
                effective *= self.buses[bus.send].volume
        return round(_clamp_volume(effective), 6)

    def _apply_player_volume(self, player: AudioPlayer) -> None:
        if player.player:
            player.player.volume = self.get_effective_volume_for_player(player)

    def get_effective_volume_for_player(self, player: AudioPlayer) -> float:
        if not self._is_player_audible(player):
            return 0.0
        effective = _clamp_volume(player.volume) * self.master_volume * self._category_scalar(player)
        for bus in self._bus_chain(player.bus):
            effective *= bus.volume
            if bus.send and bus.send in self.buses:
                effective *= self.buses[bus.send].volume
        return _clamp_volume(effective)

    def _refresh_player_volumes(self) -> None:
        for player in self.players.values():
            self._apply_player_volume(player)

    def mix_snapshot(self) -> Dict[str, Any]:
        return {
            "available": self._initialized,
            "master_volume": round(self.master_volume, 4),
            "music_volume": round(self.music_volume, 4),
            "sfx_volume": round(self.sfx_volume, 4),
            "bus_count": len(self.buses),
            "buses": {name: bus.to_dict() for name, bus in sorted(self.buses.items())},
            "active_players": {
                player_id: {
                    "bus": player.bus,
                    "category": player.category,
                    "local_volume": round(player.volume, 4),
                    "effective_volume": self.get_effective_volume(player_id),
                    "playing": player.playing,
                    "loop": player.loop,
                    "position": round(player.position, 4),
                }
                for player_id, player in sorted(self.players.items())
            },
        }

    def summary(self) -> Dict[str, Any]:
        snapshot = self.mix_snapshot()
        snapshot["stream_count"] = len(self.streams)
        return snapshot

    def update(self, delta: float) -> None:
        finished = []
        for player_id, player in self.players.items():
            player.update(delta)
            self._apply_player_volume(player)
            if player_id.startswith("oneshot_") and not player.playing:
                finished.append(player_id)
        for player_id in finished:
            del self.players[player_id]

    def cleanup(self) -> None:
        self.stop_all()
        self.players.clear()
        self.streams.clear()
