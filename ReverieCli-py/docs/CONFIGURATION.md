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
    `-- projects/
        `-- <project-path-key>/
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

Additional subdirectories such as `indexes/`, `computer_use/`, `nexus/`, or `runtime_sandbox/` are created on demand under the same project cache root.

`<project-path-key>` is derived from the full absolute project path by replacing drive separators, path separators, and invalid filename characters. It does not append a hash. For example, `G:\Reverie\Reverie-Cli` becomes `G_Reverie_Reverie-Cli`.

## Profile Selection

Reverie keeps two profile files:

- Global profile: `<app_root>/.reverie/config.json`
- Workspace profile: `<app_root>/.reverie/projects/<project-path-key>/config.json`

`<app_root>/.reverie/config.json` is used by default. The project `config.json` is used only when workspace mode is explicitly enabled for that specific project.

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

Older builds stored configuration and some workspace state in `.reverie/` and `.reverie/project_caches/`.

- Legacy config files such as `<app_root>/.reverie/project_caches/<project-key>/config.global.json` and `<project_root>/.reverie/config.json` are still read for migration.
- Legacy rules files such as `<app_root>/.reverie/rules.txt` are still read for migration.
- Legacy project cache contents are copied into `<app_root>/.reverie/projects/<project-path-key>/` on first use when the new directory is empty.
- Global writes now go to `<app_root>/.reverie/config.json`.
- Workspace writes go to `<app_root>/.reverie/projects/<project-path-key>/config.json`.
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
  "codex": {},
  "aihubmix": {},
  "agnes": {},
  "sensenova": {},
  "unlimitedsurf": {},
  "nvidia": {},
  "modelscope": {},
  "webgemini": {},
  "atlas_mode": {},
  "subagents": {},
  "writer_mode": {},
  "gamer_mode": {}
}
```

## Custom Compatibility Providers

`models` stores manually configured OpenAI-compatible or Anthropic-compatible model presets. This compatibility layer is for user-provided third-party services; built-in Codex, AIHubMix, Agnes, SenseNova, unlimited.surf, NVIDIA, ModelScope, and WebGemini sources use their own first-party runtime paths instead.

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

Optional heavyweight SDKs live under the executable-local `.reverie/plugins/<plugin-id>` depot.

- Godot and O3DE are no longer plugin runtimes. Reverie Engine consumes their project structures as migration/reference inputs through `inspect_legacy_project` and `migrate_legacy_project`.
- Ren'Py project inspection and parsing are built into Reverie Engine; the optional Ren'Py plugin is only for native SDK lint, compile, and distribution.
- Blender uses `rc_blender_mcp_install`, `rc_blender_mcp_start`, `rc_blender_mcp_stop`, `rc_blender_mcp_status`, and `rc_blender_mcp_info` to deploy and control the plugin-local Blender MCP bridge.
- Do not place optional SDK payloads in global user folders; Reverie expects them beside the executable under `.reverie/plugins`.

## Built-In Model Sources

Supported values for `active_model_source`:

- `standard`
- `codex`
- `aihubmix`
- `agnes`
- `sensenova`
- `unlimitedsurf`
- `nvidia`
- `modelscope`
- `webgemini`

Older configs may still contain a `geminicli` block. That legacy section is not a current `active_model_source`; Gemini Web routing now uses `webgemini`.

### AIHubMix

The `aihubmix` section stores the API key, selected model id/display name, OpenAI-compatible base URL, timeout, and context/output defaults used by the AIHubMix source.

Reverie reads `AIHUBMIX_API_KEY` or `AIHUBMIX_TOKEN` automatically when present.

### Agnes

The `agnes` section stores the shared Agnes API key, selected chat model id/display name, OpenAI-compatible base URL, timeout, context/output defaults, and selected thinking depth.

The same Agnes credential is also reused by Reverie's Agnes text-to-image and text-to-video tools.

### SenseNova

The `sensenova` section stores the SenseNova API key, selected model id/display name, OpenAI-compatible base URL, timeout, context/output defaults, and `reasoning_effort` for models that expose it.

SenseNova text routing uses the OpenAI Chat or Anthropic-compatible transport required by the selected model profile. Reverie reads `SENSENOVA_API_KEY` or `SENSE_API_KEY` automatically when present.

### unlimited.surf

The `unlimitedsurf` section stores the unlimited.surf API key, selected model id/display name, Anthropic-compatible base URL, timeout, context/output defaults, and reasoning depth when the selected gateway model supports it.

Reverie calls unlimited.surf through the Anthropic SDK and can refresh the public model catalog through `/us model`.

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

### WebGemini

The `webgemini` section stores the selected Gemini Web mode, optional proxy override, optional cookie path, timeout, and context/output defaults used by the anonymous WebGemini transport.

It does not require a direct API key for anonymous text routing. When no explicit proxy is configured, Reverie tries the Windows system proxy first and then `HTTPS_PROXY`/`HTTP_PROXY`.

### NVIDIA

The `nvidia` section stores the NVIDIA API key, selected model, transport-specific defaults, and optional endpoint override used by the NVIDIA source.

Get the API key from `https://build.nvidia.com/settings/api-keys`.
Reverie also reads `NVIDIA_API_KEY` from the environment when it is present, and Computer Controller mode pins the runtime to `qwen/qwen3.5-397b-a17b`.

Some NVIDIA models expose provider-side thinking controls. These are model-specific fixed choices, not prompt instructions:

- Toggle models, such as Qwen and GLM, store the choice as `enable_thinking`.
- Effort models, such as DeepSeek V4, Nemotron, Mistral Small, and GPT-OSS, store the choice as `reasoning_effort`.
- Dedicated thinking models expose no extra toggle because the provider always emits reasoning.

Use `/nvidia model` or `/nvidia model <model-id>` to select the model. When the selected model has configurable thinking, Reverie immediately opens a fixed choice selector for that model. Use `/nvidia thinking` to reopen the selector for the active NVIDIA model.

NVIDIA request timeouts default to 60 seconds and follow the global `/setting timeout` unless the `nvidia.timeout` value is explicitly set to another value.

NVIDIA GLM catalog entries include `z-ai/glm-5.2`, `z-ai/glm-5.1`, and `z-ai/glm4.7`. The `z-ai/glm5.2` and `z-ai/glm5.1` spellings are accepted as aliases for selection, and `z-ai/glm-4.7` is accepted as an alias for GLM-4.7, but NVIDIA's hosted chat-completions endpoint reports the canonical GLM ids as `z-ai/glm-5.2`, `z-ai/glm-5.1`, and `z-ai/glm4.7`.

### ModelScope

The `modelscope` section stores the ModelScope token, selected ModelScope model id, Anthropic SDK base URL, timeout, context limit, and default max output tokens.

ModelScope is called through the Anthropic SDK. Keep `api_url` as the provider root, usually `https://api-inference.modelscope.cn`; Reverie normalizes pasted `/v1`, `/v1/messages`, or `/v1/chat/completions` URLs back to the root because the SDK appends the Messages path.

Get the token from `https://www.modelscope.cn/my/access/token`.
Reverie also reads `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` from the environment when present.

Default model:

- `ZhipuAI/GLM-5.1`

Built-in ModelScope catalog:

- `ZhipuAI/GLM-5.1` - GLM-5.1, 202,752 token context
- `deepseek-ai/DeepSeek-V4-Pro` - DeepSeek V4 Pro, 1,048,576 token context
- `deepseek-ai/DeepSeek-V4-Flash` - DeepSeek V4 Flash, 1,048,576 token context
- `ZhipuAI/GLM-5` - GLM-5, 202,752 token context
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

For MMD assets, the same plugin can prepare `blender_mmd_tools` under `.reverie/plugins/blender/addons/blender_mmd_tools/`. Use `rc_blender_ensure_mmd_tools` for a one-time checkout/update or `rc_blender_import_mmd_model` to automatically prepare the add-on while importing `.pmx`/`.pmd` models with optional `.vmd` motion or `.vpd` pose files.

For Blender MCP, the same plugin can deploy the `ahujasid/blender-mcp` runtime under `.reverie/plugins/blender/mcp/blender-mcp/` and install its Blender addon into the plugin-managed Blender user scripts path. `rc_blender_mcp_info` returns the MCP server command, args, cwd, environment, static tool names, and health status. Reverie should only inject Blender MCP prompt/tool metadata after the MCP server is reachable and `tools/list` succeeds.

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
    "script_path": "comfy/generate_image.py",
    "output_dir": ".",
    "models": [
      {
        "path": "comfy/models/t2i/bluePencilXL_v700.safetensors",
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
- Packaged Windows builds embed the immutable `generate_image.py`, ComfyUI core archive, and bundled `ComfyUI-GGUF` node. Model weights and heavy Python packages such as PyTorch/CUDA remain app-local dependencies rather than being duplicated inside the CLI executable; use `text_to_image(action="diagnose", source="local")` to verify them before generation.
- `build.bat`/`build.sh` also embed Reverie's dedicated Chromium distribution. The browser tool copies it into `.reverie/browser/runtime` on first use and only accepts its own runtime/profile/session paths; it does not reuse the user's system-browser profile.

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
