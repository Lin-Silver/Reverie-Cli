from pathlib import Path
import json

from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.modes import get_mode_metadata, get_mode_tool_discovery_profile
from reverie.tools.game_design_orchestrator import GameDesignOrchestratorTool
from reverie.tools.game_playtest_lab import GamePlaytestLabTool
from reverie.tools.game_project_scaffolder import GameProjectScaffolderTool


CHINESE_LARGE_ACTION_PROMPT = (
    "\u4e00\u53e5\u63d0\u793a\u8bcd\u751f\u6210\u4e00\u4e2a\u50cf\u539f\u795e\u3001\u9e23\u6f6e\u3001"
    "\u7edd\u533a\u96f6\u90a3\u6837\u7684\u5927\u578b3D\u52a8\u4f5c\u6e38\u620f\uff0c"
    "\u5305\u542b\u5f00\u653e\u4e16\u754c\u63a2\u7d22\u3001\u89d2\u8272\u5207\u6362\u3001"
    "\u5c5e\u6027\u53cd\u5e94\u3001\u652f\u7ebf\u4efb\u52a1\u548c\u591a\u533a\u57df\u6269\u5c55\u3002"
)

CHINESE_CONTINUATION_PROMPT = (
    "\u6269\u5c55\u4e0b\u4e00\u4e2a\u533a\u57df\uff0c\u52a0\u5165\u9996\u4e2a\u591a\u9636\u6bb5Boss\uff0c"
    "\u5e76\u5f3a\u5316\u7a7a\u4e2d\u8fde\u6bb5\u4e0e\u9501\u5b9a\u955c\u5934\u3002"
)


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
    assert "artifacts/design_intelligence.json" in prompt
    assert "artifacts/design_playbook.md" in prompt
    assert "artifacts/campaign_program.json" in prompt
    assert "artifacts/roster_strategy.json" in prompt
    assert "artifacts/live_ops_plan.json" in prompt
    assert "artifacts/production_operating_model.json" in prompt
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
    assert "artifacts/design_intelligence.json" in workflow
    assert "artifacts/campaign_program.json" in workflow
    assert "artifacts/roster_strategy.json" in workflow
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


def test_compile_request_understands_chinese_large_scale_action_prompt(tmp_path: Path) -> None:
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="compile_request",
        prompt=CHINESE_LARGE_ACTION_PROMPT,
        project_name="\u661f\u6d77\u56de\u54cd",
    )

    assert result.success is True
    payload = json.loads((tmp_path / "artifacts" / "game_request.json").read_text(encoding="utf-8"))
    directive = json.loads((tmp_path / "artifacts" / "production_directive.json").read_text(encoding="utf-8"))
    large_scale_profile = payload["production"]["large_scale_profile"]

    assert payload["creative_target"]["references"] == [
        "Genshin Impact",
        "Wuthering Waves",
        "Zenless Zone Zero",
    ]
    assert payload["creative_target"]["reference_profile"]["scale_profile"] == "large_scale_anime_action"
    assert payload["experience"]["dimension"] == "3D"
    assert payload["experience"]["world_structure"] == "open_world_regions"
    assert payload["experience"]["party_model"] == "character_swap_party"
    assert payload["production"]["delivery_scope"] == "vertical_slice"
    assert payload["production"]["continuation_ready"] is True
    assert payload["production"]["target_quality"] == "aaa"
    assert "verified 3d slice" in payload["production"]["one_prompt_goal"]
    assert "multi-region" in payload["production"]["full_game_aspiration"]
    assert payload["production"]["live_service_profile"]["enabled"] is True
    assert "anime_action_service_grammar" in payload["production"]["default_design_capabilities"]
    assert large_scale_profile["project_shape"] == "anime_action_open_world"
    assert large_scale_profile["launch_region_target"] == 3
    assert large_scale_profile["post_launch_region_target"] == 6
    assert large_scale_profile["starter_party_size"] == 4
    assert large_scale_profile["world_cell_strategy"] == "region_cells_with_landmark_routes"
    assert large_scale_profile["content_cadence"] == "six_week_content_cycles"
    assert "party_roster" in large_scale_profile["runtime_contracts"]
    assert "world_streaming" in large_scale_profile["runtime_contracts"]
    assert "commission_board" in large_scale_profile["runtime_contracts"]
    assert "elemental_matrix" in large_scale_profile["runtime_contracts"]
    assert "character_swap" in payload["systems"]["specialized"]
    assert "elemental_reaction" in payload["systems"]["specialized"]
    assert "open_world_exploration" in payload["systems"]["specialized"]
    assert payload["runtime_preferences"]["preferred_runtime"] == "godot"
    assert "PC" in payload["quality_targets"]["target_platforms"]
    assert payload["quality_targets"]["graphics_quality"] == "AAA"
    assert directive["mode"] == "fresh_project"
    assert "expand_region" in directive["operations"]
    assert "refresh_content_expansion" in directive["operations"]


def test_compile_request_understands_hub_service_action_prompt(tmp_path: Path) -> None:
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="compile_request",
        prompt="Build a Zenless Zone Zero inspired 3D hub action RPG with district commissions, fast squad swaps, and long-term live updates.",
        project_name="District Echo",
    )

    assert result.success is True
    payload = json.loads((tmp_path / "artifacts" / "game_request.json").read_text(encoding="utf-8"))

    assert payload["creative_target"]["references"] == ["Zenless Zone Zero"]
    assert payload["creative_target"]["reference_profile"]["scale_profile"] == "large_scale_anime_action"
    assert payload["experience"]["world_structure"] == "hub_and_districts"
    assert payload["experience"]["party_model"] == "small_squad_fast_swap"
    assert payload["production"]["live_service_profile"]["enabled"] is True
    assert "reference_implied_live_service" in payload["production"]["live_service_profile"]["signals"]
    assert "world_route_onboarding" in payload["production"]["default_design_capabilities"]
    assert "party_synergy_role_matrix" in payload["production"]["default_design_capabilities"]
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
    design_intelligence_path = tmp_path / "artifacts" / "design_intelligence.json"
    campaign_program_path = tmp_path / "artifacts" / "campaign_program.json"
    roster_strategy_path = tmp_path / "artifacts" / "roster_strategy.json"
    live_ops_plan_path = tmp_path / "artifacts" / "live_ops_plan.json"
    production_operating_model_path = tmp_path / "artifacts" / "production_operating_model.json"
    milestone_board_path = tmp_path / "artifacts" / "milestone_board.json"
    reference_intelligence_path = tmp_path / "artifacts" / "reference_intelligence.json"
    runtime_capability_graph_path = tmp_path / "artifacts" / "runtime_capability_graph.json"
    runtime_delivery_plan_path = tmp_path / "artifacts" / "runtime_delivery_plan.json"
    system_specs_path = tmp_path / "artifacts" / "system_specs.json"
    task_graph_path = tmp_path / "artifacts" / "task_graph.json"
    content_matrix_path = tmp_path / "artifacts" / "content_matrix.json"
    content_expansion_path = tmp_path / "artifacts" / "content_expansion.json"
    asset_pipeline_path = tmp_path / "artifacts" / "asset_pipeline.json"
    character_kits_path = tmp_path / "artifacts" / "character_kits.json"
    gameplay_factory_path = tmp_path / "artifacts" / "gameplay_factory.json"
    world_program_path = tmp_path / "artifacts" / "world_program.json"
    region_kits_path = tmp_path / "artifacts" / "region_kits.json"
    faction_graph_path = tmp_path / "artifacts" / "faction_graph.json"
    expansion_backlog_path = tmp_path / "artifacts" / "expansion_backlog.json"
    resume_state_path = tmp_path / "artifacts" / "resume_state.json"
    assert game_program_path.exists()
    assert design_intelligence_path.exists()
    assert campaign_program_path.exists()
    assert roster_strategy_path.exists()
    assert live_ops_plan_path.exists()
    assert production_operating_model_path.exists()
    assert milestone_board_path.exists()
    assert reference_intelligence_path.exists()
    assert runtime_capability_graph_path.exists()
    assert runtime_delivery_plan_path.exists()
    assert system_specs_path.exists()
    assert task_graph_path.exists()
    assert content_matrix_path.exists()
    assert content_expansion_path.exists()
    assert asset_pipeline_path.exists()
    assert character_kits_path.exists()
    assert gameplay_factory_path.exists()
    assert world_program_path.exists()
    assert region_kits_path.exists()
    assert faction_graph_path.exists()
    assert expansion_backlog_path.exists()
    assert resume_state_path.exists()

    game_program = json.loads(game_program_path.read_text(encoding="utf-8"))
    design_intelligence = json.loads(design_intelligence_path.read_text(encoding="utf-8"))
    campaign_program = json.loads(campaign_program_path.read_text(encoding="utf-8"))
    roster_strategy = json.loads(roster_strategy_path.read_text(encoding="utf-8"))
    live_ops_plan = json.loads(live_ops_plan_path.read_text(encoding="utf-8"))
    production_operating_model = json.loads(production_operating_model_path.read_text(encoding="utf-8"))
    reference_intelligence = json.loads(reference_intelligence_path.read_text(encoding="utf-8"))
    runtime_capability_graph = json.loads(runtime_capability_graph_path.read_text(encoding="utf-8"))
    runtime_delivery_plan = json.loads(runtime_delivery_plan_path.read_text(encoding="utf-8"))
    system_specs = json.loads(system_specs_path.read_text(encoding="utf-8"))
    task_graph = json.loads(task_graph_path.read_text(encoding="utf-8"))
    content_matrix = json.loads(content_matrix_path.read_text(encoding="utf-8"))
    content_expansion = json.loads(content_expansion_path.read_text(encoding="utf-8"))
    asset_pipeline = json.loads(asset_pipeline_path.read_text(encoding="utf-8"))
    character_kits = json.loads(character_kits_path.read_text(encoding="utf-8"))
    gameplay_factory = json.loads(gameplay_factory_path.read_text(encoding="utf-8"))
    world_program = json.loads(world_program_path.read_text(encoding="utf-8"))
    resume_state = json.loads(resume_state_path.read_text(encoding="utf-8"))
    assert game_program["target_class"] == "large_scale_3d_action_rpg_base"
    assert game_program["large_scale_blueprint"]["project_shape"] == "regional_action_rpg"
    assert game_program["large_scale_blueprint"]["launch_region_target"] >= 1
    assert game_program["large_scale_blueprint"]["starter_party_size"] >= 4
    assert game_program["production_scale"]["project_scale"] == "large_scale"
    assert "PC" in game_program["platform_strategy"]["target_platforms"]
    assert game_program["product_strategy"]["target_quality"] == "aaa"
    assert game_program["product_strategy"]["vision_statement"]
    assert game_program["product_strategy"]["unique_selling_points"]
    assert game_program["world_fantasy"]["world_design"]
    assert game_program["aaa_product_profile"]["feature_targets"]["total_count"] >= 1
    assert "runtime_and_systems" in game_program["content_operating_model"]["authoring_lanes"]
    assert game_program["technical_guardrails"]["reference_adoption"]
    assert game_program["continuation_contract"]["continuation_ready"] is True
    assert "party_roster" in game_program["vertical_slice_contract"]["runtime_contracts"]
    assert "world_streaming" in game_program["vertical_slice_contract"]["runtime_contracts"]
    assert game_program["design_operating_system"]["feedback_model"] == "telegraph_confirm_payoff"
    assert "dynamic_difficulty_adjustment" in [item["id"] for item in design_intelligence["default_capabilities"]]
    assert len(design_intelligence["player_personas"]) >= 3
    assert len(design_intelligence["balance_lab"]["doubling_halving_probes"]) >= 4
    assert any("remappable controls" in item for item in design_intelligence["accessibility_baseline"]["required_features"])
    assert any(item["id"] == "godot_navigation_3d" for item in design_intelligence["source_library"])
    assert len(gameplay_factory["experience_design"]["balance_probe_ids"]) >= 4
    assert "safe tutorial beat" in gameplay_factory["encounter_grammar"]
    assert campaign_program["chapter_order"][0]["region_id"] == "starter_ruins"
    assert roster_strategy["party_model"] == "character_swap_party"
    assert live_ops_plan["service_model"] == "live_service"
    assert any(item["id"] == "character_roster" for item in production_operating_model["workstreams"])
    assert any(item["id"] == "godot-tps-demo" for item in reference_intelligence["detected_repositories"])
    assert any(item["runtime_id"] == "godot" for item in reference_intelligence["runtime_alignment"])
    assert reference_intelligence["toolchain_matrix"]
    assert any(item["id"] == "slice_bootstrap" for item in reference_intelligence["adoption_plan"])
    assert runtime_capability_graph["selected_runtime"] == "godot"
    assert runtime_capability_graph["selected_summary"]["scale_fit"]["score"] >= 0
    assert runtime_delivery_plan["delivery_tracks"]["world_scale_track"] == "single_slice_lane"
    assert runtime_delivery_plan["delivery_tracks"]["launch_region_target"] >= 1
    assert runtime_delivery_plan["delivery_tracks"]["starter_party_size"] >= 4
    assert runtime_delivery_plan["reference_inputs"]["adoption_plan"]
    assert runtime_delivery_plan["optimization_backlog"]
    assert any(item["id"] == "party_roster" for item in runtime_delivery_plan["runtime_data_contracts"])
    assert any(item["id"] == "world_streaming" for item in runtime_delivery_plan["runtime_data_contracts"])
    assert any(item["id"] == "commission_board" for item in runtime_delivery_plan["runtime_data_contracts"])
    assert "character_controller" in system_specs["packets"]
    assert "combat" in system_specs["packets"]
    assert "world_structure" in system_specs["packets"]
    assert "compile_program" in task_graph["resume_order"]
    assert "asset_pipeline_seed" in task_graph["resume_order"]
    assert "verification_loop" in task_graph["resume_order"]
    assert "continuity_snapshot" in task_graph["resume_order"]
    assert content_matrix["release_forecast"]["project_shape"] == "regional_action_rpg"
    assert content_matrix["release_forecast"]["launch_region_count"] >= 1
    assert content_matrix["release_forecast"]["starter_party_size"] >= 4
    assert content_matrix["release_forecast"]["target_quality"] == "aaa"
    assert "PC" in content_matrix["release_forecast"]["target_platforms"]
    assert len(content_expansion["region_seeds"]) >= 3
    assert len(asset_pipeline["production_queue"]) >= 6
    assert asset_pipeline["modeling_workspace"]["registry_path"] == "data/models/model_registry.yaml"
    assert any(item["id"] == "player_avatar" for item in asset_pipeline["modeling_seed"])
    assert any(item["id"] == "starter_support" for item in asset_pipeline["modeling_seed"])
    assert len(character_kits["hero_kits"]) >= 4
    assert asset_pipeline["import_profile"]["runtime"] == "godot"
    assert world_program["world_topology"]["nodes"]
    assert world_program["streaming_plan"]["streaming_model"]
    assert world_program["live_ops_surfaces"]
    assert gameplay_factory["character_archetypes"]
    assert "starter_affinities" in gameplay_factory["elemental_matrix"]
    assert gameplay_factory["boss_phase_templates"]
    assert "artifacts/game_program.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/design_intelligence.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/campaign_program.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/roster_strategy.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/reference_intelligence.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/asset_pipeline.json" in resume_state["artifacts_to_open_first"]
    assert "artifacts/resume_state.json" in resume_state["artifacts_to_open_first"]


def test_plan_production_reuses_artifacts_for_chinese_followup_expansion_prompt(tmp_path: Path) -> None:
    _seed_reference_workspace(tmp_path)
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    initial = tool.execute(
        action="plan_production",
        prompt="Build a Genshin Impact and Wuthering Waves inspired 3D open world action RPG vertical slice with traversal, elemental combat, and regional progression.",
        project_name="Star Echo",
    )
    follow_up = tool.execute(
        action="plan_production",
        prompt=CHINESE_CONTINUATION_PROMPT,
        project_name="Star Echo",
    )

    assert initial.success is True
    assert follow_up.success is True

    directive = json.loads((tmp_path / "artifacts" / "production_directive.json").read_text(encoding="utf-8"))
    request = json.loads((tmp_path / "artifacts" / "game_request.json").read_text(encoding="utf-8"))
    content_expansion = json.loads((tmp_path / "artifacts" / "content_expansion.json").read_text(encoding="utf-8"))
    world_program = json.loads((tmp_path / "artifacts" / "world_program.json").read_text(encoding="utf-8"))
    gameplay_factory = json.loads((tmp_path / "artifacts" / "gameplay_factory.json").read_text(encoding="utf-8"))
    boss_arc = json.loads((tmp_path / "artifacts" / "boss_arc.json").read_text(encoding="utf-8"))
    resume_state = json.loads((tmp_path / "artifacts" / "resume_state.json").read_text(encoding="utf-8"))

    assert directive["mode"] == "continue_project"
    assert "expand_region" in directive["operations"]
    assert "plan_boss_arc" in directive["operations"]
    assert "upgrade_gameplay_factory" in directive["operations"]
    assert request["continuity"]["latest_operations"] == directive["operations"]
    assert content_expansion["active_region_id"]
    assert content_expansion["active_region_id"] != "starter_ruins"
    assert content_expansion["active_region_id"] == directive["focus"]["requested_region_id"]
    assert world_program["active_region_id"] == content_expansion["active_region_id"]
    assert world_program["boss_priority_region_id"] == content_expansion["active_region_id"]
    assert "boss_duel" in [item["id"] for item in gameplay_factory["camera_presets"]]
    assert "frontier_chase" in [item["id"] for item in gameplay_factory["camera_presets"]]
    assert boss_arc["target_region"] == content_expansion["active_region_id"]
    assert boss_arc["arc_status"] == "priority"
    assert boss_arc["latest_operations"] == directive["operations"]
    assert "artifacts/production_directive.json" in resume_state["artifacts_to_open_first"]
    assert resume_state["continuity_memory"]["latest_operations"] == directive["operations"]


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
    assert (tmp_path / "artifacts" / "design_intelligence.json").exists()
    assert (tmp_path / "artifacts" / "design_playbook.md").exists()
    assert (tmp_path / "artifacts" / "campaign_program.json").exists()
    assert (tmp_path / "artifacts" / "roster_strategy.json").exists()
    assert (tmp_path / "artifacts" / "live_ops_plan.json").exists()
    assert (tmp_path / "artifacts" / "production_operating_model.json").exists()
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
    assert any(item["id"] == "asset_interchange" for item in reference_intelligence["toolchain_matrix"])
    assert any(item["id"] == "scale_architecture" for item in reference_intelligence["adoption_plan"])
    assert runtime_delivery_plan["reference_inputs"]["recommended_stack"]
    assert runtime_delivery_plan["reference_inputs"]["toolchain_matrix"]
    assert len(runtime_delivery_plan["scale_up_stages"]) >= 3
    assert runtime_delivery_plan["optimization_backlog"]
    assert runtime_registry["reference_alignment"]["godot"]["reference_fit_score"] >= 0


def test_compile_request_sets_aaa_quality_profile_for_large_scale_prompt(tmp_path: Path) -> None:
    tool = GameDesignOrchestratorTool({"project_root": tmp_path})

    result = tool.execute(
        action="compile_request",
        prompt="Build an AAA cross-platform open world 3D action RPG with character swaps, live updates, and a huge exploration map.",
        project_name="AAA Frontier",
    )

    assert result.success is True
    payload = json.loads((tmp_path / "artifacts" / "game_request.json").read_text(encoding="utf-8"))
    assert payload["production"]["target_quality"] == "aaa"
    assert payload["quality_targets"]["target_resolution"] == "4K"
    assert "PC" in payload["quality_targets"]["target_platforms"]
    assert payload["quality_targets"]["content_hours"]


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
    perf_budget = json.loads((tmp_path / "lab_slice" / "playtest" / "performance_budget.json").read_text(encoding="utf-8"))
    assert perf_budget["subsystem_budgets"]["world_streaming"]["active_regions"] >= 1
    assert perf_budget["optimization_passes"]
    continuation_text = (tmp_path / "lab_slice" / "playtest" / "continuation_recommendations.md").read_text(encoding="utf-8")
    assert "Service Model:" in continuation_text
    assert "Design Probes" in continuation_text


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
    assert (slice_root / "artifacts" / "design_intelligence.json").exists()
    assert (slice_root / "artifacts" / "design_playbook.md").exists()
    assert (slice_root / "artifacts" / "campaign_program.json").exists()
    assert (slice_root / "artifacts" / "roster_strategy.json").exists()
    assert (slice_root / "artifacts" / "live_ops_plan.json").exists()
    assert (slice_root / "artifacts" / "production_operating_model.json").exists()
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
    assert (slice_root / "data" / "party_roster.json").exists()
    assert (slice_root / "data" / "elemental_matrix.json").exists()
    assert (slice_root / "data" / "world_streaming.json").exists()
    assert (slice_root / "data" / "commission_board.json").exists()
    assert (slice_root / "data" / "slice_manifest.json").exists()
    assert (slice_root / "data" / "world_slice.json").exists()
    assert (tmp_path / "godot_slice" / "artifacts" / "asset_pipeline.json").exists()
    assert (tmp_path / "godot_slice" / "data" / "models" / "model_registry.yaml").exists()
    assert (tmp_path / "godot_slice" / "assets" / "models" / "source" / "player_avatar.bbmodel").exists()

    enemy_dummy_script = (slice_root / "scripts" / "enemy_dummy.gd").read_text(encoding="utf-8")
    main_script = (slice_root / "scripts" / "main.gd").read_text(encoding="utf-8")
    combat_payload = json.loads((slice_root / "data" / "combat.json").read_text(encoding="utf-8"))
    quest_flow_payload = json.loads((slice_root / "data" / "quest_flow.json").read_text(encoding="utf-8"))
    party_roster_payload = json.loads((slice_root / "data" / "party_roster.json").read_text(encoding="utf-8"))
    elemental_matrix_payload = json.loads((slice_root / "data" / "elemental_matrix.json").read_text(encoding="utf-8"))
    world_streaming_payload = json.loads((slice_root / "data" / "world_streaming.json").read_text(encoding="utf-8"))
    commission_board_payload = json.loads((slice_root / "data" / "commission_board.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((slice_root / "data" / "slice_manifest.json").read_text(encoding="utf-8"))
    asset_registry_payload = json.loads((slice_root / "data" / "asset_registry.json").read_text(encoding="utf-8"))
    asset_import_profile_payload = json.loads((slice_root / "data" / "asset_import_profile.json").read_text(encoding="utf-8"))
    game_state_script = (slice_root / "autoload" / "game_state.gd").read_text(encoding="utf-8")
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
    assert party_roster_payload["party_slots"]
    assert party_roster_payload["active_party_slot_ids"]
    assert party_roster_payload["starter_party_size"] >= 1
    assert elemental_matrix_payload["reaction_rules"]
    assert "starter_affinities" in elemental_matrix_payload
    assert world_streaming_payload["stream_cells"]
    assert world_streaming_payload["loaded_region_ids"]
    assert "runtime_delivery_track" in world_streaming_payload
    assert commission_board_payload["commission_slots"]
    assert commission_board_payload["active_commission_ids"]
    assert manifest_payload["party_roster"]["starter_party_size"] >= 1
    assert "active_party_slot_ids" in manifest_payload["party_roster"]
    assert "starter_affinities" in manifest_payload["elemental_matrix"]
    assert "loaded_region_ids" in manifest_payload["world_streaming"]
    assert manifest_payload["commission_board"]["active_commission_ids"]
    assert 'const PARTY_ROSTER_PATH := "res://data/party_roster.json"' in game_state_script
    assert 'const ELEMENTAL_MATRIX_PATH := "res://data/elemental_matrix.json"' in game_state_script
    assert 'const WORLD_STREAMING_PATH := "res://data/world_streaming.json"' in game_state_script
    assert 'const COMMISSION_BOARD_PATH := "res://data/commission_board.json"' in game_state_script
    assert "func get_party_summary_text() -> String:" in game_state_script
    assert "func get_streaming_summary_text() -> String:" in game_state_script
    assert "func get_commission_summary_text() -> String:" in game_state_script
    assert len(manifest_payload["region_gateways"]) >= 2
    assert len(manifest_payload["npc_beacons"]) >= 3
    assert manifest_payload["active_arc"]["id"] == "purification_path"
    assert combat_payload["player_actions"]["lock_on_enabled"] is True
    assert combat_payload["player_actions"]["skill_name"] == "focus_burst"
    assert combat_payload["player_actions"]["dash_i_frames_seconds"] > 0

    artifact_root = tmp_path / "godot_slice" / "artifacts"
    assert (artifact_root / "game_program.json").exists()
    assert (artifact_root / "design_intelligence.json").exists()
    assert (artifact_root / "design_playbook.md").exists()
    assert (artifact_root / "campaign_program.json").exists()
    assert (artifact_root / "roster_strategy.json").exists()
    assert (artifact_root / "live_ops_plan.json").exists()
    assert (artifact_root / "production_operating_model.json").exists()
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
