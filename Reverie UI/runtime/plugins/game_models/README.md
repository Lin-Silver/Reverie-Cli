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
- `cache/`: plugin-local HuggingFace/pip caches so downloads do not spill into `C:\Users`
- `state/model_state.json`: registered/downloaded model state

Supported commands include:

- `rc_game_models_list_models`
- `rc_game_models_deployment_plan`
- `rc_game_models_prepare_environment`
- `rc_game_models_ensure_runtime`
- `rc_game_models_model_status`
- `rc_game_models_select_model`
- `rc_game_models_download_model`
- `rc_game_models_register_model_path`

User-facing CLI shortcuts:

- `/plugins models`
- `/plugins models plan ram=24 vram=8`
- `/plugins models select trellis-text-xlarge profile=low_vram download`
- `/plugins models download trellis-text-xlarge profile=low_vram dry_run`
- `/plugins models status trellis-text-xlarge`

Hardware policy:

- `microsoft/TRELLIS-text-xlarge` is selectable on the `low_vram` profile for 24GB RAM / 8GB VRAM systems.
- `stable-fast-3d`, `hunyuan3d-2mini`, and `tripo-sr` remain 8GB VRAM-friendly image-to-3D fallback/ideation choices.
- `tencent/HY-Motion-1.0` remains guarded and requires `allow_heavy=true`.
