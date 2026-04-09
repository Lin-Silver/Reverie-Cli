from pathlib import Path
import json

from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_metadata, get_mode_tool_discovery_profile
from reverie.tools.game_design_orchestrator import GameDesignOrchestratorTool
from reverie.tools.game_playtest_lab import GamePlaytestLabTool
from reverie.tools.game_project_scaffolder import GameProjectScaffolderTool


def _seed_reference_workspace(root: Path) -> None:
    references_root = root / "references"
    (references_root / "godot-tps-demo" / "player").mkdir(parents=True, exist_ok=True)
    (references_root / "godot-tps-demo" / "enemies" / "red_robot").mkdir(parents=True, exist_ok=True)
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps").mkdir(parents=True, exist_ok=True)
    (references_root / "o3de-multiplayersample" / "Documentation").mkdir(parents=True, exist_ok=True)
    (references_root / "o3de-multiplayersample" / "ExportScripts").mkdir(parents=True, exist_ok=True)
    (references_root / "o3de-multiplayersample-assets" / "Gems" / "character_mps").mkdir(parents=True, exist_ok=True)
    (references_root / "o3de-multiplayersample-assets" / "Gems" / "kb3d_mps").mkdir(parents=True, exist_ok=True)
    (references_root / "o3de-multiplayersample-assets" / "Guides").mkdir(parents=True, exist_ok=True)
    for repo_name in ("blender", "blockbench", "blockbench-plugins", "gltf-validator", "gltf-blender-io", "gltf-sample-assets"):
        (references_root / repo_name).mkdir(parents=True, exist_ok=True)

    (references_root / "godot-tps-demo" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (references_root / "godot-tps-demo" / "player" / "player.gd").write_text(
        "extends CharacterBody3D\nif multiplayer.is_server():\n    pass\n",
        encoding="utf-8",
    )
    (references_root / "godot-tps-demo" / "player" / "player_input.gd").write_text(
        "extends MultiplayerSynchronizer\nfunc rotate_camera(move):\n    pass\n",
        encoding="utf-8",
    )
    (references_root / "godot-tps-demo" / "enemies" / "red_robot" / "red_robot.gd").write_text(
        "extends CharacterBody3D\n",
        encoding="utf-8",
    )
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps" / "project.godot").write_text(
        "config_version=5\n",
        encoding="utf-8",
    )
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps" / "Main.tscn").write_text(
        "[gd_scene format=3]\n",
        encoding="utf-8",
    )

    (references_root / "o3de-multiplayersample" / "README.md").write_text(
        "Support for 1 to 10 players\nteleporters\nshield\n",
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample" / "project.json").write_text(
        json.dumps({"gem_names": ["character_mps", "props_mps"]}),
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample" / "Documentation" / "GamplayConfiguration.md").write_text(
        "teleporter\njump pads\n",
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample" / "ExportScripts" / "export_mps.py").write_text(
        "print('export')\n",
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample-assets" / "readme.md").write_text(
        "Asset Gems\n",
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample-assets" / "Guides" / "GettingStarted.md").write_text(
        "DCC bootstrap\n",
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample-assets" / "Gems" / "character_mps" / "gem.json").write_text(
        json.dumps({"name": "character_mps", "requirements": "Mixamo-derived assets"}),
        encoding="utf-8",
    )
    (references_root / "o3de-multiplayersample-assets" / "Gems" / "kb3d_mps" / "gem.json").write_text(
        json.dumps({"name": "kb3d_mps", "requirements": "Kitbash3D restricted"}),
        encoding="utf-8",
    )


def test_reverie_gamer_prompt_targets_prompt_to_vertical_slice_delivery() -> None:
    prompt = build_system_prompt(model_name="Test Model", mode="reverie-gamer")

    assert "prompt -> game program -> structured request -> blueprint -> engine-aware project foundation" in prompt
    assert "artifacts/game_program.json" in prompt
    assert "artifacts/game_bible.md" in prompt
    assert "artifacts/feature_matrix.json" in prompt
    assert "artifacts/content_matrix.json" in prompt
    assert "artifacts/milestone_board.json" in prompt
    assert "artifacts/risk_register.json" in prompt
    assert "artifacts/game_request.json" in prompt
    assert "artifacts/game_blueprint.json" in prompt
    assert "artifacts/runtime_registry.json" in prompt
    assert "artifacts/reference_intelligence.json" in prompt
    assert "artifacts/runtime_capability_graph.json" in prompt
    assert "artifacts/runtime_delivery_plan.json" in prompt
    assert "artifacts/production_plan.json" in prompt
    assert "artifacts/system_specs.json" in prompt
    assert "artifacts/task_graph.json" in prompt
    assert "artifacts/content_expansion.json" in prompt
    assert "artifacts/asset_pipeline.json" in prompt
    assert "artifacts/world_program.json" in prompt
    assert "artifacts/region_kits.json" in prompt
    assert "artifacts/faction_graph.json" in prompt
    assert "artifacts/questline_program.json" in prompt
    assert "artifacts/save_migration_plan.json" in prompt
    assert "artifacts/expansion_backlog.json" in prompt
    assert "artifacts/resume_state.json" in prompt
    assert "artifacts/vertical_slice_plan.md" in prompt
    assert "playtest/quality_gates.json" in prompt
    assert "playtest/performance_budget.json" in prompt
    assert "playtest/combat_feel_report.json" in prompt
    assert "playtest/slice_score.json" in prompt
    assert "playtest/continuation_recommendations.md" in prompt
    assert "automatically reduce it to the smallest credible prototype, first playable, or vertical slice" in prompt
    assert 'game_design_orchestrator(action="compile_program")' in prompt
    assert 'game_design_orchestrator(action="compile_request")' in prompt
    assert 'game_design_orchestrator(action="plan_production")' in prompt
    assert 'game_design_orchestrator(action="generate_vertical_slice")' in prompt
    assert 'game_project_scaffolder(action="generate_vertical_slice")' in prompt
    assert 'game_project_scaffolder(action="upgrade_runtime_project")' in prompt
    assert 'game_playtest_lab(action="create_test_plan")' in prompt
    assert 'game_playtest_lab(action="run_quality_gates")' in prompt
    assert 'game_playtest_lab(action="score_combat_feel")' in prompt
    assert 'game_playtest_lab(action="plan_next_iteration")' in prompt


def test_reverie_gamer_workflow_and_discovery_profile_bias_toward_slice_execution() -> None:
    workflow = get_tool_descriptions_for_mode("reverie-gamer")
    metadata = get_mode_metadata("reverie-gamer")
    profile = get_mode_tool_discovery_profile("reverie-gamer")

    assert "prompt-to-production flow" in workflow
    assert 'game_design_orchestrator(action="compile_program")' in workflow
    assert 'game_design_orchestrator(action="compile_request")' in workflow
    assert 'game_project_scaffolder(action="generate_vertical_slice")' in workflow
    assert "artifacts/game_program.json" in workflow
    assert "artifacts/reference_intelligence.json" in workflow
    assert "artifacts/runtime_capability_graph.json" in workflow
    assert "artifacts/runtime_delivery_plan.json" in workflow
    assert "artifacts/system_specs.json" in workflow
    assert "playtest/slice_score.json" in workflow
    assert "artifacts/asset_pipeline.json" in workflow
    assert "reduce scope to the first credible playable slice" in workflow
    assert "game_playtest_lab" in workflow
    assert "continuity artifacts" in str(metadata.get("description", ""))
    assert "tool_catalog" in profile["boost_tools"]
    assert "task_manager" in profile["boost_tools"]
    assert "retrieval" in profile["focus_categories"]
    assert "orchestration" in profile["focus_categories"]
    for token in ("vertical", "slice", "scope", "playable", "godot", "score", "task_graph", "resume", "expansion"):
        assert token in profile["domain_tokens"]


def test_compile_request_reduces_ambitious_3d_prompt_to_vertical_slice(tmp_path: Path) -> None:
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="compile_request",
        prompt="Build a Genshin Impact and Wuthering Waves inspired 3D open world action RPG with exploration, combat, growth, and shrine objectives.",
        project_name="Sky Ruin Slice",
    )

    assert result.success is True
    request_path = tmp_path / "artifacts" / "game_request.json"
    assert request_path.exists()

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["creative_target"]["primary_genre"] == "action_rpg"
    assert payload["experience"]["dimension"] == "3D"
    assert payload["experience"]["camera_model"] == "third_person"
    assert payload["production"]["delivery_scope"] == "vertical_slice"
    assert payload["runtime_preferences"]["preferred_runtime"] == "godot"


def test_plan_production_emits_system_specs_and_task_graph(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="plan_production",
        prompt="Build a Genshin-like 3D action RPG vertical slice with shrine combat, progression reward, and save/load support.",
        project_name="Sky Ruin Slice",
    )

    assert result.success is True
    game_program_path = tmp_path / "artifacts" / "game_program.json"
    milestone_board_path = tmp_path / "artifacts" / "milestone_board.json"
    reference_intelligence_path = tmp_path / "artifacts" / "reference_intelligence.json"
    runtime_capability_graph_path = tmp_path / "artifacts" / "runtime_capability_graph.json"
    runtime_delivery_plan_path = tmp_path / "artifacts" / "runtime_delivery_plan.json"
    system_specs_path = tmp_path / "artifacts" / "system_specs.json"
    task_graph_path = tmp_path / "artifacts" / "task_graph.json"
    content_expansion_path = tmp_path / "artifacts" / "content_expansion.json"
    asset_pipeline_path = tmp_path / "artifacts" / "asset_pipeline.json"
    world_program_path = tmp_path / "artifacts" / "world_program.json"
    region_kits_path = tmp_path / "artifacts" / "region_kits.json"
    faction_graph_path = tmp_path / "artifacts" / "faction_graph.json"
    expansion_backlog_path = tmp_path / "artifacts" / "expansion_backlog.json"
    resume_state_path = tmp_path / "artifacts" / "resume_state.json"
    assert game_program_path.exists()
    assert milestone_board_path.exists()
    assert reference_intelligence_path.exists()
    assert runtime_capability_graph_path.exists()
    assert runtime_delivery_plan_path.exists()
    assert system_specs_path.exists()
    assert task_graph_path.exists()
    assert content_expansion_path.exists()
    assert asset_pipeline_path.exists()
    assert world_program_path.exists()
    assert region_kits_path.exists()
    assert faction_graph_path.exists()
    assert expansion_backlog_path.exists()
    assert resume_state_path.exists()

    game_program = json.loads(game_program_path.read_text(encoding="utf-8"))
    reference_intelligence = json.loads(reference_intelligence_path.read_text(encoding="utf-8"))
    runtime_capability_graph = json.loads(runtime_capability_graph_path.read_text(encoding="utf-8"))
    system_specs = json.loads(system_specs_path.read_text(encoding="utf-8"))
    task_graph = json.loads(task_graph_path.read_text(encoding="utf-8"))
    content_expansion = json.loads(content_expansion_path.read_text(encoding="utf-8"))
    asset_pipeline = json.loads(asset_pipeline_path.read_text(encoding="utf-8"))
    resume_state = json.loads(resume_state_path.read_text(encoding="utf-8"))
    assert game_program["target_class"] == "large_scale_3d_action_rpg_base"
    assert any(item["id"] == "godot-tps-demo" for item in reference_intelligence["detected_repositories"])
    assert any(item["runtime_id"] == "godot" for item in reference_intelligence["runtime_alignment"])
    assert runtime_capability_graph["selected_runtime"] == "godot"
    assert "character_controller" in system_specs["packets"]
    assert "combat" in system_specs["packets"]
    assert "world_structure" in system_specs["packets"]
    assert "compile_program" in task_graph["resume_order"]
    assert "asset_pipeline_seed" in task_graph["resume_order"]
    assert "verification_loop" in task_graph["resume_order"]
    assert "continuity_snapshot" in task_graph["resume_order"]
    assert len(content_expansion["region_seeds"]) >= 3
    assert len(asset_pipeline["production_queue"]) >= 6
    assert asset_pipeline["modeling_workspace"]["registry_path"] == "data/models/model_registry.yaml"
    assert any(item["id"] == "player_avatar" for item in asset_pipeline["modeling_seed"])
    assert asset_pipeline["import_profile"]["runtime"] == "godot"
    assert "artifacts/game_program.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/reference_intelligence.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/asset_pipeline.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/resume_state.json" in resume_state["artifacts_to_open_first"]


def test_compile_program_emits_program_and_factory_artifacts(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="compile_program",
        prompt="Build a large-scale 3D action RPG with shrine regions, faction conflict, progression, and a future boss arc.",
        project_name="Program First Slice",
    )

    assert result.success is True
    assert (tmp_path / "artifacts" / "game_program.json").exists()
    assert (tmp_path / "artifacts" / "game_bible.md").exists()
    assert (tmp_path / "artifacts" / "feature_matrix.json").exists()
    assert (tmp_path / "artifacts" / "reference_intelligence.json").exists()
    assert (tmp_path / "artifacts" / "runtime_capability_graph.json").exists()
    assert (tmp_path / "artifacts" / "runtime_delivery_plan.json").exists()
    assert (tmp_path / "artifacts" / "gameplay_factory.json").exists()
    assert (tmp_path / "artifacts" / "boss_arc.json").exists()


def test_reference_intelligence_influences_runtime_delivery_and_guardrails(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="plan_production",
        prompt="Build a large-scale 3D action RPG with third-person combat, open-world exploration, and future multiplayer expansion.",
        project_name="Reference Driven Slice",
    )

    assert result.success is True
    reference_intelligence = json.loads((tmp_path / "artifacts" / "reference_intelligence.json").read_text(encoding="utf-8"))
    runtime_delivery_plan = json.loads((tmp_path / "artifacts" / "runtime_delivery_plan.json").read_text(encoding="utf-8"))
    runtime_registry = json.loads((tmp_path / "artifacts" / "runtime_registry.json").read_text(encoding="utf-8"))

    assert any(item["reference_id"] == "o3de-multiplayersample" for item in reference_intelligence["recommended_reference_stack"])
    assert any(item["policy"] == "do_not_redistribute" for item in reference_intelligence["legal_guardrails"])
    assert runtime_delivery_plan["reference_inputs"]["recommended_stack"]
    assert runtime_registry["reference_alignment"]["godot"]["reference_fit_score"] >= 0


def test_game_playtest_lab_runs_quality_gates_and_iteration_plan(tmp_path: Path) -> None:
    scaffold = GameProjectScaffolderTool({"project_root": tmp_path})
    scaffold.execute(
        action="generate_vertical_slice",
        output_dir="lab_slice",
        prompt="Create a 3D action RPG slice with shrine combat and progression reward.",
        requested_runtime="reverie_engine",
        project_name="Lab Slice",
    )

    tool = GamePlaytestLabTool({"project_root": tmp_path / "lab_slice"})

    gates = tool.execute(action="run_quality_gates")
    combat = tool.execute(action="score_combat_feel")
    nxt = tool.execute(action="plan_next_iteration")

    assert gates.success is True
    assert combat.success is True
    assert nxt.success is True
    assert (tmp_path / "lab_slice" / "playtest" / "quality_gates.json").exists()
    assert (tmp_path / "lab_slice" / "playtest" / "performance_budget.json").exists()
    assert (tmp_path / "lab_slice" / "playtest" / "combat_feel_report.json").exists()
    assert (tmp_path / "lab_slice" / "playtest" / "continuation_recommendations.md").exists()


def test_scaffolder_can_upgrade_runtime_project_and_apply_system_packet(tmp_path: Path) -> None:
    tool = GameProjectScaffolderTool({"project_root": tmp_path})

    generated = tool.execute(
        action="generate_vertical_slice",
        output_dir="upgrade_slice",
        prompt="Create a 3D action RPG slice with combat, quest flow, and save support.",
        requested_runtime="reverie_engine",
        project_name="Upgrade Slice",
    )
    assert generated.success is True

    upgraded = tool.execute(action="upgrade_runtime_project", output_dir="upgrade_slice")
    applied = tool.execute(action="apply_system_packet", output_dir="upgrade_slice", system_name="combat")

    assert upgraded.success is True
    assert applied.success is True
    assert (tmp_path / "upgrade_slice" / "artifacts" / "applied_packets" / "combat.json").exists()


def test_generate_vertical_slice_builds_verified_reverie_engine_project(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameProjectScaffolderTool({"project_root": tmp_path})

    result = tool.execute(
        action="generate_vertical_slice",
        output_dir="builtin_slice",
        prompt="Create a 3D action RPG vertical slice with third-person combat, a shrine objective, and one progression reward.",
        requested_runtime="reverie_engine",
        project_name="Builtin Slice",
    )

    assert result.success is True
    assert result.data["runtime"] == "reverie_engine"
    assert result.data["verification"]["valid"] is True
    assert result.data["slice_score"]["score"] >= 70

    slice_root = tmp_path / "builtin_slice"
    assert (slice_root / "artifacts" / "game_program.json").exists()
    assert (slice_root / "artifacts" / "reference_intelligence.json").exists()
    assert (slice_root / "artifacts" / "runtime_capability_graph.json").exists()
    assert (slice_root / "artifacts" / "runtime_delivery_plan.json").exists()
    assert (slice_root / "artifacts" / "game_request.json").exists()
    assert (slice_root / "artifacts" / "runtime_registry.json").exists()
    assert (slice_root / "artifacts" / "production_plan.json").exists()
    assert (slice_root / "artifacts" / "system_specs.json").exists()
    assert (slice_root / "artifacts" / "task_graph.json").exists()
    assert (slice_root / "artifacts" / "asset_pipeline.json").exists()
    assert (slice_root / "artifacts" / "world_program.json").exists()
    assert (slice_root / "artifacts" / "region_kits.json").exists()
    assert (slice_root / "artifacts" / "faction_graph.json").exists()
    assert (slice_root / "playtest" / "quality_gates.json").exists()
    assert (slice_root / "playtest" / "performance_budget.json").exists()
    assert (slice_root / "playtest" / "combat_feel_report.json").exists()
    assert (slice_root / "playtest" / "slice_score.json").exists()
    assert (slice_root / "playtest" / "continuation_recommendations.md").exists()
    assert (slice_root / "data" / "models" / "model_registry.yaml").exists()
    assert (slice_root / "assets" / "models" / "source" / "player_avatar.bbmodel").exists()
    assert (slice_root / "data" / "content" / "encounters.yaml").exists()
    assert (slice_root / "data" / "content" / "quests.yaml").exists()
    assert (slice_root / "data" / "content" / "save_schema.yaml").exists()
    assert (slice_root / "data" / "content" / "asset_registry.yaml").exists()
    assert (slice_root / "data" / "content" / "asset_import_profile.yaml").exists()
    assert (slice_root / "data" / "content" / "region_seeds.yaml").exists()
    assert (slice_root / "data" / "content" / "npc_roster.yaml").exists()
    assert (slice_root / "data" / "content" / "quest_arcs.yaml").exists()
    assert (slice_root / "data" / "content" / "region_routes.yaml").exists()
    assert (slice_root / "data" / "content" / "region_layouts.yaml").exists()
    assert (slice_root / "data" / "content" / "region_objectives.yaml").exists()
    assert (slice_root / "data" / "content" / "patrol_routes.yaml").exists()
    assert (slice_root / "data" / "content" / "alert_networks.yaml").exists()
    assert (slice_root / "data" / "content" / "world_graph.yaml").exists()


def test_generate_vertical_slice_builds_godot_foundation(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameProjectScaffolderTool({"project_root": tmp_path})

    result = tool.execute(
        action="generate_vertical_slice",
        output_dir="godot_slice",
        prompt="Use Godot to build a third-person 3D action RPG slice with combat, dash, shrine interaction, and HUD feedback.",
        requested_runtime="godot",
        project_name="Godot Slice",
    )

    assert result.success is True
    assert result.data["runtime"] == "godot"
    assert result.data["verification"]["valid"] is True
    assert result.data["slice_score"]["score"] >= 70

    slice_root = tmp_path / "godot_slice" / "engine" / "godot"
    assert (slice_root / "project.godot").exists()
    assert (slice_root / "scenes" / "main.tscn").exists()
    assert (slice_root / "scripts" / "player_controller.gd").exists()
    assert (slice_root / "scripts" / "enemy_dummy.gd").exists()
    assert (slice_root / "scripts" / "enemy_projectile.gd").exists()
    assert (slice_root / "scripts" / "combat_feedback.gd").exists()
    assert (slice_root / "scripts" / "npc_anchor.gd").exists()
    assert (slice_root / "scripts" / "region_gateway.gd").exists()
    assert (slice_root / "scripts" / "reward_cache.gd").exists()
    assert (slice_root / "scripts" / "region_objective_site.gd").exists()
    assert (slice_root / "scripts" / "encounter_director.gd").exists()
    assert (slice_root / "scripts" / "region_manager.gd").exists()
    assert (slice_root / "autoload" / "game_state.gd").exists()
    assert (slice_root / "autoload" / "save_service.gd").exists()
    assert (slice_root / "data" / "combat.json").exists()
    assert (slice_root / "data" / "quest_flow.json").exists()
    assert (slice_root / "data" / "asset_registry.json").exists()
    assert (slice_root / "data" / "asset_import_profile.json").exists()
    assert (slice_root / "data" / "region_seeds.json").exists()
    assert (slice_root / "data" / "region_layouts.json").exists()
    assert (slice_root / "data" / "region_objectives.json").exists()
    assert (slice_root / "data" / "patrol_routes.json").exists()
    assert (slice_root / "data" / "alert_networks.json").exists()
    assert (slice_root / "data" / "world_graph.json").exists()
    assert (slice_root / "data" / "npc_roster.json").exists()
    assert (slice_root / "data" / "quest_arcs.json").exists()
    assert (slice_root / "data" / "slice_manifest.json").exists()
    assert (slice_root / "data" / "world_slice.json").exists()
    assert (tmp_path / "godot_slice" / "artifacts" / "asset_pipeline.json").exists()
    assert (tmp_path / "godot_slice" / "data" / "models" / "model_registry.yaml").exists()
    assert (tmp_path / "godot_slice" / "assets" / "models" / "source" / "player_avatar.bbmodel").exists()

    enemy_dummy_script = (slice_root / "scripts" / "enemy_dummy.gd").read_text(encoding="utf-8")
    main_script = (slice_root / "scripts" / "main.gd").read_text(encoding="utf-8")
    combat_payload = json.loads((slice_root / "data" / "combat.json").read_text(encoding="utf-8"))
    quest_flow_payload = json.loads((slice_root / "data" / "quest_flow.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((slice_root / "data" / "slice_manifest.json").read_text(encoding="utf-8"))
    asset_registry_payload = json.loads((slice_root / "data" / "asset_registry.json").read_text(encoding="utf-8"))
    asset_import_profile_payload = json.loads((slice_root / "data" / "asset_import_profile.json").read_text(encoding="utf-8"))
    assert '@export var squad_role: String = "default"' in enemy_dummy_script
    assert "func _run_search_logic(delta: float) -> void:" in enemy_dummy_script
    assert '_alert_search_duration = float(alert_network.get("search_duration_seconds", 3.0))' in enemy_dummy_script
    assert 'enemy.squad_role = str(enemy_spec.get("squad_role", "default"))' in main_script
    assert any(item["combat_role"] == "ranged" for item in combat_payload["enemy_defaults"])
    assert any(item["combat_tier"] == "elite" for item in combat_payload["enemy_defaults"])
    assert any(item["combat_tier"] == "boss" for item in combat_payload["enemy_defaults"])
    assert any(item["id"] == "shrine_guardian_finale" for item in combat_payload["encounter_templates"])
    assert any(item["id"] == "overlook_elite_detour" for item in combat_payload["encounter_templates"])
    assert any(item["id"] == "cloudstep_relay_push" for item in combat_payload["encounter_templates"])
    assert any(item["id"] == "echo_spire_hold" for item in combat_payload["encounter_templates"])
    assert len(combat_payload["pattern_library"]["elite_vanguard"]["phase_profiles"]) >= 2
    assert len(combat_payload["pattern_library"]["shrine_guardian"]["phase_profiles"]) >= 3
    assert len(combat_payload["player_actions"]["combo_chain"]) >= 3
    assert combat_payload["player_actions"]["skill_loadout"]["heavy"]["name"] == "skybreak"
    assert combat_payload["player_actions"]["guard"]["enabled"] is True
    assert combat_payload["player_actions"]["guard"]["perfect_guard_window_seconds"] > 0
    assert combat_payload["player_actions"]["player_hurt_reaction_seconds"] > 0
    assert [item["id"] for item in quest_flow_payload["objectives"]][:2] == ["meet_guide", "reach_ruins"]
    assert any(item["id"] == "defeat_warden" for item in quest_flow_payload["objectives"])
    assert quest_flow_payload["active_arc"]["id"] == "purification_path"
    assert any(item["objective_id"] == "cloudstep_relay" for item in quest_flow_payload["region_handoffs"])
    assert any(item["encounter_id"] == "cloudstep_relay_push" for item in quest_flow_payload["region_handoffs"])
    assert any(item["combat_role"] == "ranged" for item in manifest_payload["enemies"])
    assert any(item["combat_tier"] == "elite" for item in manifest_payload["enemies"])
    assert any(item["combat_tier"] == "boss" for item in manifest_payload["enemies"])
    assert any(item.get("archetype_id") == "sentinel_ranged" for item in manifest_payload["enemies"])
    assert any(item.get("squad_role") == "suppressor" for item in manifest_payload["enemies"])
    assert any(item.get("squad_role") == "anchor" for item in manifest_payload["enemies"])
    assert any(item["region_id"] == "cloudstep_basin" for item in manifest_payload["enemies"])
    assert any(item["region_id"] == "echo_watch" for item in manifest_payload["enemies"])
    assert any(item["pattern_profile_id"] == "shrine_guardian" for item in manifest_payload["enemies"])
    assert any(item["pattern_profile_id"] == "elite_vanguard" for item in manifest_payload["enemies"])
    assert any(item["critical_path"] is False for item in manifest_payload["enemies"])
    assert any(item["max_poise"] > 3.0 for item in manifest_payload["enemies"])
    assert any(item["reward_id"] == "route_sigil" for item in manifest_payload["reward_sites"])
    assert any(item["id"] == "overlook_cache" for item in manifest_payload["reward_sites"])
    assert manifest_payload["active_region_id"] == "starter_ruins"
    assert len(manifest_payload["region_layouts"]) >= 3
    assert len(manifest_payload["region_objectives"]) >= 2
    assert len(manifest_payload["patrol_routes"]) >= 3
    assert any(item["id"] == "cloudstep_relay_arc" for item in manifest_payload["patrol_routes"])
    assert any("cloudstep_basin_sentinel_ranged" in item["assigned_enemy_ids"] for item in manifest_payload["patrol_routes"])
    assert len(manifest_payload["alert_networks"]) >= 3
    assert any(item["id"] == "cloudstep_relay_alert" for item in manifest_payload["alert_networks"])
    assert any("cloudstep_basin_sentinel_melee" in item["assigned_enemy_ids"] for item in manifest_payload["alert_networks"])
    assert any(item.get("search_duration_seconds", 0) > 0 for item in manifest_payload["alert_networks"])
    assert any(item.get("anchor_point") for item in manifest_payload["alert_networks"])
    assert any(item["id"] == "cloudstep_relay" for item in manifest_payload["region_objectives"])
    assert any(item.get("region_objective_id") == "cloudstep_relay" for item in manifest_payload["region_layouts"])
    assert any(item["target_region"] == "cloudstep_basin" for item in manifest_payload["region_gateways"])
    assert any(item["region_id"] == "cloudstep_basin" for item in manifest_payload["region_gateways"])
    assert any(item["id"] == "cloudstep_basin" for item in manifest_payload["world_graph"]["nodes"])
    assert any(item.get("region_objective_id") == "cloudstep_relay" for item in manifest_payload["world_graph"]["nodes"])
    assert any(item["objective_id"] == "cloudstep_relay" for item in manifest_payload["world_graph"]["regional_goals"])
    assert any(item["route_id"] == "cloudstep_relay_arc" for item in manifest_payload["world_graph"]["patrol_lanes"])
    assert any(item["network_id"] == "cloudstep_relay_alert" for item in manifest_payload["world_graph"]["guard_networks"])
    assert any(item.get("search_duration_seconds", 0) > 0 for item in manifest_payload["world_graph"]["guard_networks"])
    assert any(item.get("anchor_point") for item in manifest_payload["world_graph"]["guard_networks"])
    assert any(item["id"] == "shrine_guardian_finale" for item in manifest_payload["encounters"])
    assert any(item["id"] == "overlook_elite_detour" for item in manifest_payload["encounters"])
    assert any(item["id"] == "cloudstep_relay_push" for item in manifest_payload["encounters"])
    assert any(item["id"] == "echo_spire_hold" for item in manifest_payload["encounters"])
    assert any(item["id"] == "player_avatar" for item in asset_registry_payload["modeling_seed"])
    assert asset_import_profile_payload["import_profile"]["runtime"] == "godot"
    assert asset_import_profile_payload["runtime_delivery"]["asset_registry_path"] == "engine/godot/data/asset_registry.json"
    assert len(manifest_payload["region_gateways"]) >= 2
    assert len(manifest_payload["npc_beacons"]) >= 3
    assert manifest_payload["active_arc"]["id"] == "purification_path"
    assert combat_payload["player_actions"]["lock_on_enabled"] is True
    assert combat_payload["player_actions"]["skill_name"] == "focus_burst"
    assert combat_payload["player_actions"]["dash_i_frames_seconds"] > 0

    artifact_root = tmp_path / "godot_slice" / "artifacts"
    assert (artifact_root / "game_program.json").exists()
    assert (artifact_root / "reference_intelligence.json").exists()
    assert (artifact_root / "runtime_capability_graph.json").exists()
    assert (artifact_root / "runtime_delivery_plan.json").exists()
    assert (artifact_root / "system_specs.json").exists()
    assert (artifact_root / "task_graph.json").exists()
    assert (artifact_root / "content_expansion.json").exists()
    assert (artifact_root / "asset_pipeline.json").exists()
    assert (artifact_root / "world_program.json").exists()
    assert (artifact_root / "region_kits.json").exists()
    assert (artifact_root / "faction_graph.json").exists()
    assert (artifact_root / "expansion_backlog.json").exists()
    assert (artifact_root / "resume_state.json").exists()
    assert (tmp_path / "godot_slice" / "playtest" / "quality_gates.json").exists()
    assert (tmp_path / "godot_slice" / "playtest" / "performance_budget.json").exists()
    assert (tmp_path / "godot_slice" / "playtest" / "combat_feel_report.json").exists()
    assert (tmp_path / "godot_slice" / "playtest" / "slice_score.json").exists()
