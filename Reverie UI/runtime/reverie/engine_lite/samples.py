"""Built-in sample definitions for Reverie Engine Lite."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def _base_scene(name: str, scene_id: str, dimension: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "Scene",
        "scene_id": scene_id,
        "metadata": {
            "dimension": dimension,
            "entry_camera": "MainCamera",
        },
        "components": [
            {
                "type": "Transform",
                "position": [0, 0, 0],
                "rotation": [0, 0, 0],
                "scale": [1, 1, 1],
            }
        ],
        "children": [],
    }


SAMPLE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "2d_platformer": {
        "project_name": "Reverie Platformer Slice",
        "dimension": "2D",
        "genre": "platformer",
        "description": "A compact side-view platformer sample with a pickup and goal trigger.",
        "scene": {
            **_base_scene("PlatformerMain", "main", "2D"),
            "children": [
                {
                    "name": "Player",
                    "type": "Actor",
                    "tags": ["player"],
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Sprite", "texture": "assets/textures/player_placeholder.png", "size": [1, 2]},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "player", "mask": ["world", "pickup", "goal"]},
                        {"type": "KinematicBody", "speed": 5.0, "gravity": 0.0},
                        {"type": "ScriptBehaviour", "script": "player_avatar"},
                    ],
                    "children": [],
                },
                {
                    "name": "MainCamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 2, 0]},
                        {"type": "Camera2D", "zoom": 1.0, "follow_target": "Player"},
                    ],
                    "children": [],
                },
                {
                    "name": "Coin",
                    "type": "Pickup",
                    "components": [
                        {"type": "Transform", "position": [4, 0, 0]},
                        {"type": "Collider", "size": [1, 1, 1], "layer": "pickup", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "collectible", "params": {"reward_type": "currency", "amount": 1}},
                    ],
                    "children": [],
                },
                {
                    "name": "ExitGate",
                    "type": "Goal",
                    "components": [
                        {"type": "Transform", "position": [8, 0, 0]},
                        {"type": "Collider", "size": [1, 3, 1], "layer": "goal", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "goal_trigger", "params": {"goal_id": "platformer_exit"}},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "player.relprefab.json": {
                "name": "Player",
                "type": "Actor",
                "tags": ["player"],
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Sprite", "texture": "assets/textures/player_placeholder.png", "size": [1, 2]},
                    {"type": "Collider", "size": [1, 2, 1], "layer": "player", "mask": ["world", "pickup", "goal"]},
                    {"type": "KinematicBody", "speed": 5.0, "gravity": 0.0},
                ],
                "children": [],
            }
        },
        "content": {
            "progression.yaml": {
                "tracks": [{"id": "movement", "levels": [1, 2, 3], "perks": ["dash", "double_jump", "air_control"]}],
                "reward_table": [{"type": "currency", "id": "coin", "amount": 1}],
            }
        },
        "input_script": [
            {"from_frame": 0, "to_frame": 120, "node": "Player", "move": [0.08, 0, 0]},
        ],
        "expected_events": ["reward_claimed", "goal_reached"],
    },
    "iso_adventure": {
        "project_name": "Reverie Isometric Slice",
        "dimension": "2.5D",
        "genre": "adventure",
        "description": "An isometric adventure sample with pickup and room progression.",
        "scene": {
            **_base_scene("IsoAdventure", "main", "2.5D"),
            "children": [
                {
                    "name": "Player",
                    "type": "Actor",
                    "tags": ["player"],
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Sprite", "texture": "assets/textures/iso_player_placeholder.png", "size": [1, 2], "billboard": True},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "player", "mask": ["world", "pickup", "goal"]},
                        {"type": "KinematicBody", "speed": 4.5},
                        {"type": "ScriptBehaviour", "script": "player_avatar"},
                    ],
                    "children": [],
                },
                {
                    "name": "MainCamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 10, -10]},
                        {"type": "Camera3D", "mode": "isometric", "fov": 55.0},
                    ],
                    "children": [],
                },
                {
                    "name": "QuestRelic",
                    "type": "Pickup",
                    "components": [
                        {"type": "Transform", "position": [3, 0, 3]},
                        {"type": "Collider", "size": [1, 1, 1], "layer": "pickup", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "collectible", "params": {"reward_type": "narrative", "amount": 1}},
                    ],
                    "children": [],
                },
                {
                    "name": "ExitDoor",
                    "type": "Goal",
                    "components": [
                        {"type": "Transform", "position": [6, 0, 6]},
                        {"type": "Collider", "size": [1, 3, 1], "layer": "goal", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "goal_trigger", "params": {"goal_id": "room_exit"}},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "relic.relprefab.json": {
                "name": "QuestRelic",
                "type": "Pickup",
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Collider", "size": [1, 1, 1], "layer": "pickup", "is_trigger": True},
                    {"type": "ScriptBehaviour", "script": "collectible", "params": {"reward_type": "narrative", "amount": 1}},
                ],
                "children": [],
            }
        },
        "content": {
            "quests.yaml": {
                "quests": [{"id": "first_relic", "steps": ["find_relic", "reach_exit"], "rewards": ["story_flag:first_relic"]}]
            }
        },
        "input_script": [
            {"from_frame": 0, "to_frame": 90, "node": "Player", "move": [0.04, 0, 0.04]},
            {"from_frame": 91, "to_frame": 180, "node": "Player", "move": [0.04, 0, 0.04]},
        ],
        "expected_events": ["reward_claimed", "goal_reached"],
    },
    "3d_arena": {
        "project_name": "Reverie Arena Slice",
        "dimension": "3D",
        "genre": "arena",
        "description": "A third-person arena sample with interaction and encounter telemetry.",
        "scene": {
            **_base_scene("ArenaMain", "main", "3D"),
            "children": [
                {
                    "name": "Player",
                    "type": "Actor",
                    "tags": ["player"],
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "player", "mask": ["world", "enemy", "goal"]},
                        {"type": "KinematicBody", "speed": 5.5},
                        {"type": "ScriptBehaviour", "script": "player_avatar"},
                    ],
                    "children": [],
                },
                {
                    "name": "MainCamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 4, -8]},
                        {"type": "Camera3D", "mode": "third_person", "fov": 68.0},
                    ],
                    "children": [],
                },
                {
                    "name": "TrainingDummy",
                    "type": "Enemy",
                    "components": [
                        {"type": "Transform", "position": [4, 0, 0]},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "enemy", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "enemy_dummy"},
                    ],
                    "children": [],
                },
                {
                    "name": "ObjectiveConsole",
                    "type": "Goal",
                    "components": [
                        {"type": "Transform", "position": [8, 0, 0]},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "goal", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "goal_trigger", "params": {"goal_id": "arena_console"}},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "dummy.relprefab.json": {
                "name": "TrainingDummy",
                "type": "Enemy",
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Collider", "size": [1, 2, 1], "layer": "enemy", "is_trigger": True},
                    {"type": "ScriptBehaviour", "script": "enemy_dummy"},
                ],
                "children": [],
            }
        },
        "content": {
            "encounters.yaml": {
                "encounters": [{"id": "arena_intro", "enemies": ["dummy"], "reward": {"type": "power", "amount": 1}}]
            }
        },
        "input_script": [
            {"from_frame": 0, "to_frame": 60, "node": "Player", "move": [0.06, 0, 0]},
            {"from_frame": 61, "to_frame": 150, "node": "Player", "move": [0.05, 0, 0]},
            {"frame": 151, "node": "Player", "action": "interact", "direction": [1, 0, 0]},
        ],
        "expected_events": ["encounter_started", "goal_reached"],
    },
    "galgame_live2d": {
        "project_name": "Reverie Live2D Story Slice",
        "dimension": "2D",
        "genre": "galgame",
        "description": "A branching dialogue sample with Live2D-ready character presentation and route flags.",
        "scene": {
            **_base_scene("Live2DStoryMain", "main", "2D"),
            "metadata": {
                "dimension": "2D",
                "entry_camera": "UICamera",
                "genre": "galgame",
                "autostart_conversation": "intro_route",
            },
            "children": [
                {
                    "name": "UICamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Camera2D", "zoom": 1.0},
                    ],
                    "children": [],
                },
                {
                    "name": "HeroineA",
                    "type": "Character",
                    "tags": ["cast", "heroine"],
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Dialogue", "conversation_id": "intro_route", "speaker": "Ariel"},
                        {"type": "Live2D", "model_id": "heroine_alpha", "idle_motion": "idle"},
                        {"type": "ScriptBehaviour", "script": "live2d_avatar", "params": {"model_id": "heroine_alpha"}},
                    ],
                    "children": [],
                },
                {
                    "name": "DialogueFrame",
                    "type": "UI",
                    "components": [
                        {
                            "type": "UIControl",
                            "anchor_left": 0.04,
                            "anchor_top": 0.67,
                            "anchor_right": 0.96,
                            "anchor_bottom": 0.96,
                            "min_size": [640, 180],
                        },
                        {"type": "Panel", "style": "dialogue"},
                        {"type": "DialogueBox", "speaker_prefix": ""},
                    ],
                    "children": [],
                },
                {
                    "name": "ChoiceStack",
                    "type": "UI",
                    "components": [
                        {
                            "type": "UIControl",
                            "anchor_left": 0.58,
                            "anchor_top": 0.32,
                            "anchor_right": 0.95,
                            "anchor_bottom": 0.60,
                            "min_size": [320, 180],
                        },
                        {"type": "ChoiceList", "choice_prefix": ">> "},
                    ],
                    "children": [],
                },
                {
                    "name": "StoryGoal",
                    "type": "Goal",
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "ScriptBehaviour", "script": "goal_trigger", "params": {"goal_id": "route_locked_in"}},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "heroine_alpha.relprefab.json": {
                "name": "HeroineA",
                "type": "Character",
                "tags": ["cast", "heroine"],
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Dialogue", "conversation_id": "intro_route", "speaker": "Ariel"},
                    {"type": "Live2D", "model_id": "heroine_alpha", "idle_motion": "idle"},
                ],
                "children": [],
            }
        },
        "content": {
            "dialogue.yaml": {
                "conversations": {
                    "intro_route": {
                        "start": "opening",
                        "cast": {
                            "Ariel": {"live2d_model": "heroine_alpha"}
                        },
                        "nodes": {
                            "opening": {
                                "speaker": "Ariel",
                                "text": "Welcome to Reverie. Which route should we chart tonight?",
                                "live2d_motion": "greet",
                                "choices": [
                                    {
                                        "text": "A gentle story route",
                                        "next": "gentle_route",
                                        "effects": {
                                            "set_flags": ["route:gentle"],
                                            "add_resources": {"affection": 1},
                                        },
                                    },
                                    {
                                        "text": "A bold dramatic route",
                                        "next": "dramatic_route",
                                        "effects": {
                                            "set_flags": ["route:dramatic"],
                                            "add_resources": {"affection": 2},
                                        },
                                    },
                                ],
                            },
                            "gentle_route": {
                                "speaker": "Ariel",
                                "text": "Then let's keep the night warm and close to the heart.",
                                "live2d_motion": "smile",
                                "next": "route_lock",
                            },
                            "dramatic_route": {
                                "speaker": "Ariel",
                                "text": "Then we lean into the thunder and see who flinches first.",
                                "live2d_motion": "surprised",
                                "next": "route_lock",
                            },
                            "route_lock": {
                                "speaker": "Ariel",
                                "text": "The first chapter is ready. Your route flag is now locked in.",
                                "live2d_motion": "idle",
                                "effects_on_enter": {"set_flags": ["story:chapter_1_ready", "goal:route_locked_in"]},
                            },
                        },
                    }
                }
            },
            "quests.yaml": {
                "quests": {
                    "chapter_1": {"initial_state": "active"}
                }
            },
        },
        "files": {
            "data/live2d/models.yaml": {
                "enabled": True,
                "renderer": "web",
                "sdk_candidates": [
                    "vendor/live2d/live2dcubismcore.min.js",
                    "web/vendor/live2d/live2dcubismcore.min.js",
                ],
                "models": {
                    "heroine_alpha": {
                        "model_id": "heroine_alpha",
                        "model_json": "assets/live2d/heroine_alpha/heroine_alpha.model3.json",
                        "motions": {
                            "idle": ["Idle_01"],
                            "greet": ["Greet_01"],
                            "smile": ["Smile_01"],
                            "surprised": ["Surprised_01"],
                        },
                        "expressions": {"soft": "Soft.exp3.json"},
                        "textures": [],
                        "placeholder": True,
                    }
                },
            },
            "assets/live2d/heroine_alpha/heroine_alpha.model3.json": "{\n  \"Version\": 3,\n  \"FileReferences\": {\n    \"Moc\": \"heroine_alpha.moc3\"\n  }\n}\n",
        },
        "input_script": [
            {"frame": 5, "action": "choose", "choice": 1},
            {"frame": 15, "action": "advance_dialogue"},
            {"frame": 25, "action": "advance_dialogue"},
        ],
        "expected_events": ["dialogue_started", "dialogue_choice", "dialogue_completed", "live2d_motion"],
    },
    "tower_defense": {
        "project_name": "Reverie Tower Defense Slice",
        "dimension": "2D",
        "genre": "tower_defense",
        "description": "A deterministic tower defense sample with waves, pathing, economy, and auto-firing turrets.",
        "scene": {
            **_base_scene("TowerDefenseMain", "main", "2D"),
            "metadata": {
                "dimension": "2D",
                "entry_camera": "MainCamera",
                "genre": "tower_defense",
                "autostart_wave": "tutorial_wave",
            },
            "children": [
                {
                    "name": "MainCamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Camera2D", "zoom": 0.8},
                    ],
                    "children": [],
                },
                {
                    "name": "TurretSlotAlpha",
                    "type": "TowerSlot",
                    "tags": ["tower", "tower_defense"],
                    "components": [
                        {"type": "Transform", "position": [3, 0, 0]},
                        {"type": "TowerDefense", "role": "tower", "range": 4.5, "damage": 2.0, "cadence_frames": 20},
                    ],
                    "children": [],
                },
                {
                    "name": "WaveSpawnerA",
                    "type": "Spawner",
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "TowerDefense", "role": "spawner", "wave_id": "tutorial_wave"},
                        {"type": "ScriptBehaviour", "script": "wave_spawner", "params": {"wave_id": "tutorial_wave", "auto_start": True}},
                    ],
                    "children": [],
                },
                {
                    "name": "GoldHud",
                    "type": "UI",
                    "components": [
                        {"type": "UIControl", "anchor_left": 0.02, "anchor_top": 0.03, "min_size": [260, 28]},
                        {"type": "ResourceBar", "resource_id": "gold", "label": "Gold", "max_value": 300},
                        {"type": "ProgressBar", "show_percentage": False},
                    ],
                    "children": [],
                },
                {
                    "name": "LivesHud",
                    "type": "UI",
                    "components": [
                        {"type": "UIControl", "anchor_left": 0.02, "anchor_top": 0.08, "min_size": [260, 28]},
                        {"type": "ResourceBar", "resource_id": "lives", "label": "Lives", "max_value": 10},
                        {"type": "ProgressBar", "show_percentage": False},
                    ],
                    "children": [],
                },
                {
                    "name": "BuildHud",
                    "type": "UI",
                    "components": [
                        {
                            "type": "UIControl",
                            "anchor_left": 0.72,
                            "anchor_top": 0.08,
                            "anchor_right": 0.98,
                            "anchor_bottom": 0.46,
                            "min_size": [260, 220],
                        },
                        {"type": "Panel", "style": "build"},
                        {"type": "TowerBuildPanel", "title": "Build Towers"},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "turret_alpha.relprefab.json": {
                "name": "TurretSlotAlpha",
                "type": "TowerSlot",
                "tags": ["tower", "tower_defense"],
                "components": [
                    {"type": "Transform", "position": [3, 0, 0]},
                    {"type": "TowerDefense", "role": "tower", "range": 4.5, "damage": 2.0, "cadence_frames": 20},
                ],
                "children": [],
            }
        },
        "content": {
            "tower_defense.yaml": {
                "economy": {
                    "starting_resources": {"gold": 200, "lives": 10}
                },
                "lanes": {
                    "lane_a": {
                        "spawn": [0, 0, 0],
                        "checkpoints": [
                            [2, 0, 0],
                            [4, 0, 0],
                            [6, 0, 0]
                        ],
                        "goal": [8, 0, 0]
                    }
                },
                "paths": {
                    "lane_a": {
                        "type": "lane",
                        "lane": "lane_a"
                    }
                },
                "towers": {
                    "arrow_basic": {
                        "cost": 60,
                        "range": 4.5,
                        "damage": 2.0,
                        "cadence_frames": 20,
                        "projectile_speed": 8.0
                    }
                },
                "waves": {
                    "tutorial_wave": {
                        "enemies": [
                            {"enemy_id": "slime", "path_id": "lane_a", "spawn_frame": 0, "speed": 1.0, "health": 3, "reward": 5},
                            {"enemy_id": "slime", "path_id": "lane_a", "spawn_frame": 18, "speed": 1.1, "health": 3, "reward": 5},
                            {"enemy_id": "brute", "path_id": "lane_a", "spawn_frame": 48, "speed": 0.8, "health": 5, "reward": 10}
                        ]
                    }
                }
            }
        },
        "input_script": [],
        "expected_events": ["wave_started", "enemy_spawned", "tower_fired", "enemy_destroyed", "wave_completed"],
    },
}


def _topdown_action_sample() -> Dict[str, Any]:
    return {
        "project_name": "Reverie Topdown Action Slice",
        "dimension": "2D",
        "genre": "action_rpg",
        "description": "A topdown combat sample with navigation pressure, loot pickup, and an extraction goal.",
        "scene": {
            **_base_scene("TopdownActionMain", "main", "2D"),
            "children": [
                {
                    "name": "Player",
                    "type": "Actor",
                    "tags": ["player"],
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Sprite", "texture": "assets/textures/topdown_player.png", "size": [1, 1]},
                        {"type": "Collider", "size": [1, 1, 1], "layer": "player", "mask": ["enemy", "pickup", "goal"]},
                        {"type": "KinematicBody", "speed": 4.8},
                        {"type": "ScriptBehaviour", "script": "player_avatar"},
                    ],
                    "children": [],
                },
                {
                    "name": "MainCamera",
                    "type": "CameraRig",
                    "components": [
                        {"type": "Transform", "position": [0, 0, 0]},
                        {"type": "Camera2D", "zoom": 0.95, "follow_target": "Player"},
                    ],
                    "children": [],
                },
                {
                    "name": "ScoutEnemy",
                    "type": "Enemy",
                    "components": [
                        {"type": "Transform", "position": [3, 0, 0]},
                        {"type": "Collider", "size": [1, 1, 1], "layer": "enemy", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "enemy_dummy"},
                    ],
                    "children": [],
                },
                {
                    "name": "SupplyCache",
                    "type": "Pickup",
                    "components": [
                        {"type": "Transform", "position": [6, 0, 0]},
                        {"type": "Collider", "size": [1, 1, 1], "layer": "pickup", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "collectible", "params": {"reward_type": "gold", "amount": 3}},
                    ],
                    "children": [],
                },
                {
                    "name": "ExtractionGate",
                    "type": "Goal",
                    "components": [
                        {"type": "Transform", "position": [9, 0, 0]},
                        {"type": "Collider", "size": [1, 2, 1], "layer": "goal", "is_trigger": True},
                        {"type": "ScriptBehaviour", "script": "goal_trigger", "params": {"goal_id": "topdown_exit"}},
                    ],
                    "children": [],
                },
            ],
        },
        "prefabs": {
            "scout_enemy.relprefab.json": {
                "name": "ScoutEnemy",
                "type": "Enemy",
                "components": [
                    {"type": "Transform", "position": [0, 0, 0]},
                    {"type": "Collider", "size": [1, 1, 1], "layer": "enemy", "is_trigger": True},
                    {"type": "ScriptBehaviour", "script": "enemy_dummy"},
                ],
                "children": [],
            }
        },
        "content": {
            "encounters.yaml": {
                "encounters": [{"id": "topdown_patrol", "enemies": ["scout_enemy"], "reward": {"type": "gold", "amount": 3}}]
            }
        },
        "input_script": [
            {"from_frame": 0, "to_frame": 50, "node": "Player", "move": [0.06, 0, 0]},
            {"from_frame": 51, "to_frame": 110, "node": "Player", "move": [0.06, 0, 0]},
            {"from_frame": 111, "to_frame": 170, "node": "Player", "move": [0.05, 0, 0]},
        ],
        "expected_events": ["encounter_started", "reward_claimed", "goal_reached"],
    }


def _derive_alias(base_name: str, *, sample_name: str, project_name: str, genre: str | None = None, description: str | None = None) -> None:
    sample = deepcopy(SAMPLE_LIBRARY[base_name])
    sample["project_name"] = project_name
    if genre is not None:
        sample["genre"] = genre
    if description is not None:
        sample["description"] = description
    SAMPLE_LIBRARY[sample_name] = sample


SAMPLE_LIBRARY["topdown_action"] = _topdown_action_sample()
_derive_alias(
    "iso_adventure",
    sample_name="2_5d_exploration",
    project_name="Reverie 2.5D Exploration Slice",
    genre="adventure",
    description="A reusable 2.5D exploration template with pickups, traversal, and room goals.",
)
_derive_alias(
    "3d_arena",
    sample_name="3d_third_person",
    project_name="Reverie Third Person Slice",
    genre="arena",
    description="A reusable third-person 3D action template with interaction and combat beats.",
)
_derive_alias(
    "galgame_live2d",
    sample_name="galgame",
    project_name="Reverie Galgame Slice",
    genre="galgame",
    description="A reusable Galgame template with branching dialogue, UI, and Live2D-ready presentation.",
)


def list_samples() -> list[str]:
    return sorted(SAMPLE_LIBRARY.keys())


def get_sample_definition(name: str) -> Dict[str, Any]:
    key = str(name or "").strip()
    if key not in SAMPLE_LIBRARY:
        raise KeyError(f"Unknown Reverie Engine sample: {name}")
    return SAMPLE_LIBRARY[key]
