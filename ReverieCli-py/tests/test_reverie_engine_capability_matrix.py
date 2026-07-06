from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reverie.engine import (
    AnimationKeyframe,
    AnimationTrack,
    AudioManager,
    ColliderComponent,
    GridNavigationMap,
    InputManager,
    InputMap,
    LocalizationManager,
    Node,
    PhysicsRayQueryParameters,
    PhysicsWorld,
    RenderMode,
    Renderer,
    RigidBodyComponent,
    SaveDataManager,
    Scene,
    SceneTree,
    Vector3,
    assess_project_scope,
    create_project_skeleton,
    load_engine_config,
    run_project_smoke,
    supported_game_families,
    validate_project,
)


FAMILIES = supported_game_families()


@pytest.mark.parametrize("dimension", ["2D", "2.5D", "3D"])
@pytest.mark.parametrize("family", FAMILIES, ids=[item["id"] for item in FAMILIES])
def test_every_declared_game_family_builds_and_validates_in_every_dimension(
    tmp_path: Path,
    family: dict,
    dimension: str,
) -> None:
    project = tmp_path / dimension.replace(".", "_") / family["id"]
    create_project_skeleton(
        project,
        project_name=f"Matrix {family['id']} {dimension}",
        dimension=dimension,
        genre=family["id"],
        overwrite=True,
    )

    validation = validate_project(project)
    config = load_engine_config(project)
    scope = assess_project_scope(
        dimension=dimension,
        genre=family["id"],
        quality_tier="AA",
        world_structure="focused",
    )

    assert validation["valid"] is True, validation["errors"]
    assert config.dimension == dimension
    assert config.genre == family["id"]
    assert set(family["modules"]).issubset(set(config.modules))
    assert scope["supported"] is True


@pytest.mark.parametrize(
    ("dimension", "genre", "render_mode"),
    [("2D", "platformer", "2d"), ("2.5D", "adventure", "2.5d"), ("3D", "arena", "3d")],
)
def test_each_dimension_runs_a_real_headless_runtime_smoke(
    tmp_path: Path,
    dimension: str,
    genre: str,
    render_mode: str,
) -> None:
    project = tmp_path / dimension.replace(".", "_")
    create_project_skeleton(project, project_name=f"Smoke {dimension}", dimension=dimension, genre=genre, overwrite=True)
    config_path = project / "data" / "config" / "engine.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["runtime"]["deterministic_smoke_frames"] = 18
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = run_project_smoke(project)

    assert result["success"] is True
    assert result["summary"]["rendering"]["mode"] == render_mode
    assert result["summary"]["rendering"]["last_frame"]["frame_index"] == 17
    assert Path(result["log_path"]).is_file()


@pytest.mark.parametrize("family", FAMILIES, ids=[item["id"] for item in FAMILIES])
def test_every_game_family_executes_its_data_driven_primary_rule(tmp_path: Path, family: dict) -> None:
    project = tmp_path / family["id"]
    create_project_skeleton(
        project,
        project_name=f"Rules {family['id']}",
        dimension="2D",
        genre=family["id"],
        overwrite=True,
    )
    rules = yaml.safe_load((project / "data" / "content" / "rules.yaml").read_text(encoding="utf-8"))
    primary_action = rules["primary_action"]
    expected_event = rules["rules"][primary_action]["event"]

    result = run_project_smoke(project)

    events = result["summary"]["events_by_name"]
    assert events[expected_event] == 1
    assert events["rule_action_executed"] >= 1
    assert result["summary"]["world_state"]["notes"]["rules_profile"] == family["id"]


def test_card_game_foundation_runs_draw_play_and_victory_loop(tmp_path: Path) -> None:
    project = tmp_path / "card-game"
    create_project_skeleton(project, project_name="Card Loop", dimension="2D", genre="card_game", overwrite=True)

    result = run_project_smoke(project)

    events = result["summary"]["events_by_name"]
    state = result["summary"]["world_state"]
    assert events["card_drawn"] == 1
    assert events["card_played"] == 1
    assert events["card_battle_won"] == 1
    assert state["counters"]["victory_progress"] == 1
    assert state["resources"]["energy"] == 9
    assert "victory:first_battle" in state["flags"]


def test_core_runtime_subsystems_interoperate(tmp_path: Path) -> None:
    scene = Scene("Integration")
    player = scene.add_child(Node("Player"))
    player.transform.position = Vector3(0, 0, 0)
    player.add_component(ColliderComponent(size=Vector3(1, 1, 1), layer="player", mask=["world"]))
    player.add_component(RigidBodyComponent(gravity_scale=0))
    obstacle = scene.add_child(Node("Obstacle"))
    obstacle.transform.position = Vector3(0.5, 0, 0)
    obstacle.add_component(ColliderComponent(size=Vector3(1, 1, 1), layer="world", mask=["player"]))
    obstacle.add_component(RigidBodyComponent(gravity_scale=0, is_kinematic=True))
    tree = SceneTree(scene)
    tree.step(1 / 60)

    physics = PhysicsWorld()
    physics.add_body(player)
    physics.add_body(obstacle)
    collisions = physics.resolve_collisions()
    ray_hit = physics.intersect_ray(
        PhysicsRayQueryParameters(origin=Vector3(-5, 0, 0), direction=Vector3(1, 0, 0), max_distance=20)
    )

    navigation = GridNavigationMap("main", 5, 5, blocked={(2, 2)})
    path = navigation.find_path(start_cell=(0, 0), goal_cell=(4, 4))

    inputs = InputManager()
    inputs.input_map = InputMap({87: "move_up"}, {})
    inputs.on_key_press(87)

    renderer = Renderer(RenderMode.RENDER_2D, headless=True)
    assert renderer.initialize() is True
    frame = renderer.render_frame(tree)

    localization_dir = tmp_path / "data" / "localization"
    localization_dir.mkdir(parents=True)
    (localization_dir / "strings.yaml").write_text(
        'en:\n  hello: "Hello {name}"\nzh-CN:\n  hello: "你好{name}"\n',
        encoding="utf-8",
    )
    localization = LocalizationManager(tmp_path, locale="zh-CN")
    audio = AudioManager(tmp_path)
    audio.create_bus("Dialogue", parent="Master")
    save_data = SaveDataManager(tmp_path)
    save_path = save_data.save_slot("integration", tree, localization=localization)
    animation = AnimationTrack(
        "Player",
        "transform.position.x",
        keyframes=[AnimationKeyframe(0.0, 0.0), AnimationKeyframe(1.0, 10.0)],
    )

    assert len(collisions) == 1
    assert ray_hit is not None and ray_hit.node_name == "Player"
    assert len(path) >= 2 and Vector3(2, 0, 2) not in path
    assert inputs.is_action_just_pressed("move_up") is True
    assert frame.backend.value == "headless"
    assert localization.translate("hello", params={"name": "Reverie"}) == "你好Reverie"
    assert audio.get_bus("Dialogue") is not None
    assert save_path.is_file() and save_data.load_slot("integration")["scene"]["name"] == "Integration"
    assert animation.sample(0.5) == pytest.approx(5.0)
