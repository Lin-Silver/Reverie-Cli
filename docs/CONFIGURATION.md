# Configuration Guide

This document describes where Reverie CLI stores configuration and runtime state, and how the major configuration sections are organized.

## Runtime Storage Layout

Reverie stores project runtime data under the app root, not in the directory where the command is launched.

- When running from source, `app_root` is the repository root.
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

Additional subdirectories such as `indexes/`, `snapshots/`, `computer_control/`, `nexus/`, or `runtime_sandbox/` are created on demand under the same project cache root.

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
- Workspace writes go to `.reverie/project_caches/<project-key>/config.json`.
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
  "use_workspace_config": false,
  "text_to_image": {},
  "qwencode": {},
  "geminicli": {},
  "codex": {},
  "nvidia": {},
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

## External Model Sources

Supported values for `active_model_source`:

- `standard`
- `qwencode`
- `geminicli`
- `codex`
- `nvidia`

### Qwen Code

The `qwencode` section tracks the selected model and endpoint override for locally detected Qwen Code credentials.

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
