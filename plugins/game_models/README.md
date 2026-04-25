# Game Auxiliary Models Plugin

This plugin manages optional open model packages for the Reverie-Gamer asset lane.

It is deliberately a deployment/control layer, not a promise that every model can
run on every machine. The plugin creates a Python virtual environment inside its
own plugin folder, downloads HuggingFace snapshots into `models/`, and writes
manifests that game tools can inspect before using a model.

Default installed path:

`dist/.reverie/plugins/game_models/`

Important folders:

- `venv/`: plugin-local Python environment
- `models/`: plugin-local HuggingFace model snapshots
- `state/model_state.json`: registered/downloaded model state

Supported commands include:

- `rc_game_models_list_models`
- `rc_game_models_deployment_plan`
- `rc_game_models_prepare_environment`
- `rc_game_models_ensure_runtime`
- `rc_game_models_model_status`
- `rc_game_models_download_model`
- `rc_game_models_register_model_path`

Hardware policy:

- `stable-fast-3d` and `tripo-sr` are the default 8GB VRAM-friendly asset-ideation choices.
- `microsoft/TRELLIS-text-xlarge` and `tencent/HY-Motion-1.0` are registered as guarded heavy research models.
- Heavy models require `allow_heavy=true` before download and are not treated as default runnable models for 24GB RAM / 8GB VRAM systems.
