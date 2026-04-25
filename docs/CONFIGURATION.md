# Configuration Guide

This document describes where Reverie CLI stores configuration and runtime state, and how the major configuration sections are organized.

## Runtime Storage Layout

Reverie stores project runtime data under the app root, not in the directory where the command is launched.

- When running from source, `app_root` is the repository-local `dist/` depot.
- In packaged Windows builds, `app_root` is the folder containing `reverie.exe`.

For each project Reverie creates a cache directory:

```text
<app_root>/
`-- .reverie/
    |-- config.json
    `-- project_caches/
        `-- <project-key>/
            |-- config.json
            |-- rules.txt
            |-- context_cache/
            |-- sessions/
            |-- archives/
            |-- checkpoints/
            |-- specs/
            |-- steering/
            `-- security/
                `-- command_audit.jsonl
```

Additional subdirectories such as `indexes/`, `computer_control/`, `nexus/`, or `runtime_sandbox/` are created on demand under the same project cache root.

`<project-key>` is derived from the absolute project path plus a short hash so different workspaces stay isolated.

## Profile Selection

Reverie keeps two profile files:

- Global profile: `<app_root>/.reverie/config.json`
- Workspace profile: `<app_root>/.reverie/project_caches/<project-key>/config.json`

`<app_root>/.reverie/config.json` is used when workspace mode is off. The project-cache `config.json` is used when workspace mode is on for that specific project.

Use the built-in commands to inspect or switch profile mode:

```text
/workspace
/workspace status
/workspace enable
/workspace disable
/workspace copy-to-workspace
/workspace copy-to-global
```

## Legacy Migration

Older builds stored configuration and some workspace state in `.reverie/`.

- Legacy config files such as `<app_root>/.reverie/project_caches/<project-key>/config.global.json` and `<project_root>/.reverie/config.json` are still read for migration.
- Legacy rules files such as `<app_root>/.reverie/rules.txt` are still read for migration.
- Global writes now go to `<app_root>/.reverie/config.json`.
- Workspace writes go to `<app_root>/.reverie/project_caches/<project-key>/config.json`.
- `/clean` removes the active project's cache and also cleans legacy workspace-local `.reverie/context_cache` or `.reverie/security` folders if they still exist.

## Top-Level Config Structure

Common top-level keys:

```json
{
  "models": [],
  "active_model_index": 0,
  "active_model_source": "standard",
  "mode": "reverie",
  "theme": "default",
  "stream_responses": true,
  "auto_index": true,
  "show_status_line": true,
  "tool_output_style": "compact",
  "thinking_output_style": "full",
  "use_workspace_config": false,
  "text_to_image": {},
  "geminicli": {},
  "codex": {},
  "nvidia": {},
  "modelscope": {},
  "atlas_mode": {},
  "writer_mode": {},
  "gamer_mode": {}
}
```

## Standard Models

`models` stores regular OpenAI-compatible model presets. Each item can include:

- `model`
- `model_display_name`
- `base_url`
- `api_key`
- `max_context_tokens`
- `provider`
- `thinking_mode`
- `endpoint`
- `custom_headers`

When `active_model_source` is `standard`, Reverie uses `active_model_index` to choose from this list.

## Gamer Modeling

`gamer_mode` may include Blender and the built-in Ashfox MCP bridge settings. Useful keys:

- `blender_modeling_enabled`: enables the built-in Blender workflow.
- `blender_path`: optional absolute path to `blender.exe`/`blender`; otherwise Reverie checks `REVERIE_BLENDER_PATH`, `BLENDER_PATH`, PATH, and common install folders.
- `blender_default_export_format`: default runtime export format, normally `glb`.
- `blender_timeout_seconds`: timeout for background Blender script runs.
- `ashfox_server_name` and `ashfox_endpoint`: the built-in Ashfox MCP server entry used when an optional Blockbench session exposes Ashfox locally.

## Runtime Plugins

Open runtime SDKs live under the executable-local `.reverie/plugins/<plugin-id>` depot.

- Godot uses `rc_godot_list_versions`, `rc_godot_install_runtime`, `rc_godot_ensure_runtime`, and `rc_godot_clone_source` for GitHub release discovery, plugin-local downloads, and source checkouts.
- O3DE uses `rc_o3de_list_versions`, `rc_o3de_clone_source`, and `rc_o3de_ensure_runtime` to create a plugin-local source SDK and `runtime/sdk_manifest.json`.
- Do not place cloned engine source or SDK payloads in global user folders; Reverie expects them beside the executable under `.reverie/plugins`.

## External Model Sources

Supported values for `active_model_source`:

- `standard`
- `geminicli`
- `codex`
- `nvidia`
- `modelscope`

### Gemini CLI

The `geminicli` section stores the selected Gemini model and optional endpoint override used by `/Geminicli`.

The endpoint field can point to either a base host or a full reverse-proxy endpoint. Reverie normalizes the URL so both layouts work.

### Codex

The `codex` section stores:

- `selected_model_id`
- `selected_model_display_name`
- `api_url`
- `endpoint`
- `reasoning_effort`
- `max_context_tokens`
- `timeout`

Reverie normalizes ChatGPT and Codex URLs automatically, so these all work:

- `https://chatgpt.com`
- `https://chatgpt.com/backend-api`
- `https://chatgpt.com/backend-api/codex`
- A full reverse-proxy `/responses` endpoint

### NVIDIA

The `nvidia` section stores the NVIDIA API key, selected model, transport-specific defaults, and optional endpoint override used by the NVIDIA source.

Get the API key from `https://build.nvidia.com/settings/api-keys`.
Reverie also reads `NVIDIA_API_KEY` from the environment when it is present, and Computer Controller mode pins the runtime to `qwen/qwen3.5-397b-a17b`.

NVIDIA DeepSeek V4 models use `reasoning_effort` for provider-side thinking depth. Reverie normalizes it to:

- `max` - default, maps to NVIDIA Max thinking
- `high` - maps to NVIDIA High thinking
- `none` - non-thinking mode; `/nvidia thinking off`

Use `/nvidia thinking max`, `/nvidia thinking high`, or `/nvidia thinking off` to change this without editing JSON.

For NVIDIA-hosted `z-ai/glm-5.1`, Reverie enables a fast interactive profile by default because the hosted model is very slow when paired with large output budgets and chat-template thinking. The profile uses:

- `glm_fast_mode`: default `true`
- `glm_fast_max_tokens`: default `1024`
- `glm_fast_temperature`: default `0.25`
- `glm_fast_top_p`: default `0.90`

Set `glm_fast_mode` to `false` only for deliberate deep-thinking runs where latency is acceptable.
Use `/nvidia fast on` or `/nvidia fast off` to toggle this without editing JSON by hand.

### ModelScope

The `modelscope` section stores the ModelScope token, selected ModelScope model id, Anthropic SDK base URL, timeout, context limit, and default max output tokens.

ModelScope is called through the Anthropic SDK. Keep `api_url` as the provider root, usually `https://api-inference.modelscope.cn`; Reverie normalizes pasted `/v1` or `/v1/messages` URLs back to the root because the SDK appends the Messages path.

Get the token from `https://www.modelscope.cn/my/access/token`.
Reverie also reads `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` from the environment when present.

Default model:

- `ZhipuAI/GLM-5.1`

Built-in ModelScope catalog:

- `ZhipuAI/GLM-5.1` - GLM-5.1, 202,752 token context
- `deepseek-ai/DeepSeek-V3.2` - DeepSeek V3.2, 128,000 token context
- `ZhipuAI/GLM-5` - GLM-5, 202,752 token context
- `moonshotai/Kimi-K2.5` - Kimi K2.5, 262,144 token context
- `MiniMax/MiniMax-M2.7` - MiniMax M2.7, 204,800 token context
- `Qwen/Qwen3.5-397B-A17B` - Qwen3.5 397B A17B, 262,144 token context

## Plugin SDK Depot

Plugins are the portable SDK/runtime depot under `.reverie/plugins`, not another Skill or MCP-style instruction layer. Use it for heavyweight local applications and binaries that should live beside the packaged executable.

- SDK root: `.reverie/plugins/<plugin-id>/`
- Portable payload root: `.reverie/plugins/<plugin-id>/runtime/`
- SDK manifest: `.reverie/plugins/<plugin-id>/sdk_manifest.json`
- Prepare a depot: `/plugins sdk <plugin-id>`
- Deploy a bundled portable runtime: `/plugins deploy <plugin-id>`
- Launch a deployed runtime: `/plugins run <plugin-id>`
- Select/download game auxiliary models: `/plugins models plan ram=24 vram=8`, then `/plugins models select trellis-text-xlarge profile=low_vram download`

For Blender portable deployment, use:

```text
.reverie/plugins/blender/runtime/blender.exe
```

The official Blender plugin embeds `blender-5.1.1-windows-x64.zip` inside `reverie-blender.exe` at build time. `/plugins deploy blender` or the `rc_blender_ensure_runtime` tool asks that plugin executable to extract the portable runtime into the depot, so the installed `dist/.reverie/plugins/blender/` folder does not need to keep a separate zip file.

The built-in Blender workflow also checks `REVERIE_BLENDER_PATH`, `BLENDER_PATH`, `PATH`, and common system install folders.

The official `game_models` plugin keeps model snapshots, HuggingFace cache, pip cache, manifests, and its Python venv inside `.reverie/plugins/game_models/`. TRELLIS Text XLarge is selectable on the `low_vram` profile for 24GB RAM / 8GB VRAM systems; HY-Motion remains guarded by `allow_heavy=true`.

## Text-To-Image Configuration

Reverie stores the editable TTI model list directly in `text_to_image.models`.
Older top-level `tti-models` entries are still read for migration, then rewritten into the nested canonical shape.

Minimal example:

```json
{
  "text_to_image": {
    "enabled": true,
    "python_executable": "",
    "script_path": "Comfy/generate_image.py",
    "output_dir": ".",
    "models": [
      {
        "path": "Comfy/models/t2i/bluePencilXL_v700.safetensors",
        "display_name": "blue-pencil-xl",
        "introduction": "General illustration model"
      },
      {
        "path": "F:/Models/T2I/ernie-image",
        "display_name": "ernie-image-turbo-folder",
        "format": "auto",
        "introduction": "ERNIE-Image-Turbo GGUF folder package for local high-quality visual assets",
        "recommended_width": 512,
        "recommended_height": 512,
        "recommended_steps": 8,
        "recommended_cfg": 1.0,
        "recommended_sampler": "euler",
        "recommended_scheduler": "simple"
      }
    ],
    "default_model_display_name": "blue-pencil-xl",
    "default_width": 512,
    "default_height": 512,
    "default_steps": 20,
    "default_cfg": 8.0,
    "default_sampler": "euler",
    "default_scheduler": "normal",
    "default_negative_prompt": "",
    "force_cpu": false,
    "auto_install_missing_deps": false,
    "auto_install_max_missing_deps": 6
  }
}
```

Notes:

- Relative TTI model paths are resolved from the active config or project context.
- A model entry `path` may point to either a single model file or a folder package. For folder packages, Reverie auto-selects the main diffusion model and common auxiliary files such as `ministral-3-3b.safetensors` and `flux2-vae.safetensors`.
- GGUF diffusion models are supported through the bundled `ComfyUI-GGUF` custom node. They usually need separate ComfyUI-compatible text encoder and VAE files; for ERNIE-Image-Turbo, place `ernie-image-turbo-Q4_K_S.gguf`, `ministral-3-3b.safetensors`, and `flux2-vae.safetensors` in the same folder or in standard `text_encoders/` and `vae/` subfolders.
- Advanced entries may still set `model_file`/`diffusion_model`, `clip_model`, `vae_model`, or `prompt_enhancer_model` explicitly. Relative auxiliary paths are resolved from the model package folder first.
- `text_to_image(action="prepare_models", package="ernie-image-turbo-gguf")` reports the app-local depot under `.reverie/plugins/Packages/comfyui/models`; pass `download=true` only when you want Reverie to fetch the large required auxiliary files there, and add `include_optional=true` only if you also want the optional prompt enhancer.
- `output_dir` defaults to the project root when set to `"."`.
- `requirements-tti.txt` is optional and only needed when you plan to run `/tti`.
- In packaged Windows builds, bundled runtime assets are embedded by `build.bat`.

## Atlas Mode Configuration

`atlas_mode` controls the behavior of `Reverie-Atlas`. Important keys include:

- `research_first`
- `master_document_required`
- `appendix_documents_required`
- `minimum_appendix_count`
- `master_document_filename`
- `appendix_filename_pattern`
- `require_document_confirmation`
- `implementation_after_confirmation`
- `slow_and_rigorous_execution`
- `implementation_review_required`
- `documentation_refresh_after_implementation`
- `use_context_engine_memory`
- `verification_depth`

By default, the master document filename is `Master Document.md`, and the appendix filename pattern follows the localized default defined in `reverie/atlas.py`.

## Runtime and UX Settings

Useful non-provider keys:

- `mode`
- `theme`
- `max_context_tokens`
- `stream_responses`
- `auto_index`
- `show_status_line`
- `tool_output_style`
- `thinking_output_style`
- `api_max_retries`
- `api_initial_backoff`
- `api_timeout`
- `api_enable_debug_logging`

These are surfaced in `/setting` and related subcommands.

## Recommended Maintenance Rules

- Keep one stable default source for each workspace.
- Use the workspace profile when one repository needs different models, providers, or runtime defaults.
- Update both README files whenever onboarding or storage behavior changes.
- After modifying command behavior, verify `/help`, `README.md`, and `docs/CLI_COMMANDS.md` still agree.
- After modifying runtime storage paths, also update `reverie/agent/system_prompt.py` so spec and steering workflows continue to point at the correct directories.
