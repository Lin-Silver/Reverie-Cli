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
  "nvidia": {},
  "modelscope": {},
  "webgemini": {},
  "opencode": {},
  "custom_providers": {},
  "atlas_mode": {},
  "subagents": {},
  "writer_mode": {},
  "gamer_mode": {},
  "security": {}
}
```

## Security and Approval Policy

The `security` block holds both the hard capability ceiling and the approval mode layered on top of it:

```json
{
  "security": {
    "permission_level": "full_control",
    "permission_mode": "default",
    "strict_allow_read_only": false,
    "review": {
      "model_mode": "follow",
      "source": "",
      "model": "",
      "model_index": 0,
      "timeout": 45,
      "max_tokens": 900,
      "approve_risk_at": "medium",
      "fail_open": false,
      "review_read_only": false
    }
  }
}
```

`permission_mode` is `default`, `auto_check`, or `strict`; `review` configures the Auto Check reviewer, and `model_mode` is `follow` (reuse the chat model) or `custom` (use `source` plus `model`/`model_index`). Every value is clamped or falls back on load, so a hand-edited or partial block never blocks startup. Manage the whole block from the settings UI or the `/permission` commands rather than by hand. See [SECURITY_PERMISSIONS.md](SECURITY_PERMISSIONS.md) for what each mode actually does.

## Custom Compatibility Providers

`models` stores manually configured OpenAI-compatible or Anthropic-compatible model presets. This compatibility layer is for user-provided third-party services; built-in Codex, AIHubMix, Agnes, SenseNova, NVIDIA, ModelScope, WebGemini, and Opencode sources use their own first-party runtime paths instead.

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

For third-party gateways, prefer `/provider add`: it stores the endpoint under `custom_providers`, reads the provider's own model list, and keeps the model you picked. See [Custom Providers](#custom-providers). The `models` list here remains the manual path for one-off presets you want to edit by hand.

### Prompt Caching

Prompt caching is enabled automatically and does not require a configuration key. Reverie sends stable hashed cache-routing keys through OpenAI Chat Completions and Responses transports, tries `cache_prompt` on raw OpenAI-compatible/local requests, and enables Anthropic's automatic ephemeral cache. The same policy is used for streaming, non-streaming, Context Engine compression, and session-handoff calls.

Third-party compatibility endpoints may not implement their upstream provider's cache fields. Reverie first attempts the cache-enabled request and retries once without only those fields when the endpoint explicitly reports them as unsupported. WebGemini and image/video generation transports are unchanged because they do not expose the same prompt-prefix cache API.

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

## Skills

Skills are files on disk, not configuration keys. Reverie scans these roots in this order:

| Root | Scope |
| --- | --- |
| `reverie/builtin_skills/<name>/SKILL.md` | Bundled with the package |
| plugin-owned skill directories | Contributed by an installed runtime plugin |
| `~/.agents/skills/<name>/SKILL.md` | User-wide |
| `<app_root>/.reverie/Skills` and `.reverie/skills` | Legacy application roots |
| `.agents/skills/<name>/SKILL.md` | Repository, from the project root down to the current workspace |

Two skills may share a name. A lookup by name resolves to the first in the order above, so a bundled skill shadows a repository one. The shadowed file is not silently ignored: `/skills` ends with a **Shadowed Skills** table naming the file and the skill that claimed its name, `/status` counts it in the skills summary, and the desktop skills pane flags the record. Because a name can only resolve to the winner, the shadowed copy is withheld from the model's skill list and from `skill_lookup` — advertising a description whose body can never be loaded is worse than omitting it. Rename or delete the shadowed directory; it stays inspectable by its full `SKILL.md` path in the meantime.

A skill directory holds `SKILL.md` with YAML frontmatter (`name`, `description`), an optional `agents/openai.yaml`, and optional `references/*.md` that the body links to for progressive disclosure. `agents/openai.yaml` may set `interface.display_name`, `interface.short_description`, `interface.default_prompt`, and `policy.allow_implicit_invocation: false` to keep a skill out of automatic selection.

A few bundled skills are gated to one mode — `reverie-engine` only appears in `reverie-gamer`. The rest, including `browser-controler` and `photo-to-3d`, are available in every mode that allows skill discovery.

Pinned skills (`/skill <name>`) are session state held in memory only. They are never written to `config.json`, so restarting Reverie releases every pin. A pin overrides `allow_implicit_invocation: false` because it is an explicit user instruction. See [CLI_COMMANDS.md](CLI_COMMANDS.md) for the commands.

## Built-In Model Sources

Supported values for `active_model_source`:

- `standard`
- `codex`
- `aihubmix`
- `agnes`
- `sensenova`
- `nvidia`
- `modelscope`
- `webgemini`
- `opencode`
- `custom` - one of the providers you added with `/provider add`

Older configs may still contain a `geminicli` block. That legacy section is not a current `active_model_source`; Gemini Web routing now uses `webgemini`.

### AIHubMix

The `aihubmix` section stores the API key, selected model id/display name, OpenAI-compatible base URL, timeout, and context/output defaults used by the AIHubMix source.

Reverie reads `AIHUBMIX_API_KEY` or `AIHUBMIX_TOKEN` automatically when present.

### Agnes

The `agnes` section stores the shared Agnes API key, selected chat model id/display name, OpenAI-compatible base URL, timeout, context/output defaults, and selected thinking depth.

The same Agnes credential is also reused by Reverie's Agnes text-to-image and text-to-video tools. With `live_model_list` enabled, one authenticated `/models` query supplies the LLM, TTI, and TTV inventory; Reverie filters media entries to locally supported execution profiles and falls back to the verified built-in catalog when discovery is unavailable.

### SenseNova

The `sensenova` section stores the SenseNova API key, selected model id/display name, OpenAI-compatible base URL, timeout, context/output defaults, and `reasoning_effort` for models that expose it.

SenseNova text routing uses the OpenAI Chat or Anthropic-compatible transport required by the selected model profile. Reverie reads `SENSENOVA_API_KEY` or `SENSE_API_KEY` automatically when present.

### Codex

The `codex` section stores:

- `selected_model_id`
- `selected_model_display_name`
- `api_url`
- `endpoint`
- `auth_mode` (`auto`, `codex`, `api_key`, or `none`)
- `api_key_env` (defaults to `CODEX_PROXY_API_KEY`)
- `api_key` (supported, but an environment variable is preferred)
- `custom_headers`
- `reasoning_effort`
- `max_context_tokens`
- `timeout`

Reverie normalizes ChatGPT and Codex URLs automatically, so these all work:

- `https://chatgpt.com`
- `https://chatgpt.com/backend-api`
- `https://chatgpt.com/backend-api/codex`
- A full reverse-proxy `/responses` endpoint

For a reverse proxy, set `api_url` to its root (for example, `https://proxy.example/v1`) or put a full Responses URL in `endpoint`. Reverie preserves query parameters and avoids appending duplicate `/responses` paths. Custom proxy model ids are accepted even when they do not appear in the local Codex catalog; select one with `/codex model vendor/model-id`.

Authentication modes:

- `auto`: use the proxy key when configured; otherwise fall back to local Codex credentials.
- `codex`: always use `~/.codex/auth.json`.
- `api_key`: read a proxy Bearer key from `api_key` or `api_key_env`.
- `none`: send no Authorization header, for trusted local gateways.

Use `/codex auth api_key MY_PROXY_KEY` to select an environment variable without placing the secret in command history. Third-party proxy requests do not receive `ChatGPT-Account-Id`, `Originator`, or other ChatGPT-only identity headers unless you explicitly add equivalent custom headers.

### WebGemini

The `webgemini` section stores the selected Gemini Web mode, optional proxy override, optional cookie path, timeout, and context/output defaults used by the anonymous WebGemini transport.

It does not require a direct API key for anonymous text routing. When no explicit proxy is configured, Reverie tries the Windows system proxy first and then `HTTPS_PROXY`/`HTTP_PROXY`.

### NVIDIA

The `nvidia` section stores the NVIDIA API key, selected model, transport-specific defaults, and optional endpoint override used by the NVIDIA source.

Get the API key from `https://build.nvidia.com/settings/api-keys`.
Reverie also reads `NVIDIA_API_KEY` from the environment when it is present, and Computer Controller mode pins the runtime to `meta/muse-glimmer-30b`.

Some NVIDIA models expose provider-side thinking controls. These are model-specific fixed choices, not prompt instructions:

- Toggle models, such as Nemotron 3.5 Lightning, store the choice as `enable_thinking`.
- Effort models, such as Kimi K3, DeepSeek V4, Muse Glimmer, Nemotron 3 Super, MiniMax M3, and GPT-OSS, store the choice as `reasoning_effort`.
- Dedicated thinking models, such as Nemotron 3 Ultra and Step-3.7-Flash, expose no extra toggle because the provider always emits reasoning.

Kimi K3 always reasons and accepts only `low`, `high`, or `max`. Reverie sends that value as NVIDIA's top-level `reasoning_effort` field and preserves prior assistant `reasoning_content` alongside tool calls for multi-turn requests.

Use `/nvidia model` or `/nvidia model <model-id>` to select the model. When the selected model has configurable thinking, Reverie immediately opens a fixed choice selector for that model. Use `/nvidia thinking` to reopen the selector for the active NVIDIA model.

NVIDIA request timeouts default to 60 seconds and follow the global `/setting timeout` unless the `nvidia.timeout` value is explicitly set to another value.

NVIDIA's hosted catalog includes `nvidia/nemotron-3-ultra-550b-a55b`; it uses the OpenAI-compatible SDK transport with fixed thinking enabled and a 16,384-token reasoning budget.

### ModelScope

The `modelscope` section stores the ModelScope token, selected ModelScope model id, OpenAI-compatible base URL, timeout, context limit, default max output tokens, and the model-specific reasoning choice.

ModelScope is called through OpenAI Chat Completions. Keep `api_url` at `https://api-inference.modelscope.cn/v1`; Reverie also normalizes pasted `/v1/messages` or `/v1/chat/completions` URLs to that base URL.

Get the token from `https://www.modelscope.cn/my/access/token`.
Reverie also reads `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` from the environment when present.

Default model:

- `stepfun-ai/Step-3.7-Flash`

Built-in ModelScope catalog:

- `stepfun-ai/Step-3.7-Flash` - Step 3.7 Flash, 262,144 token context, `low`/`medium`/`high`
- `stepfun-ai/Step-3.7-Flash` - Step 3.7 Flash, 262,144 token context, vision, `low`/`medium`/`high`
- `ZhipuAI/GLM-5.2` - GLM-5.2, 1,048,576 token context, `none`/`high`/`max`
- `deepseek-ai/DeepSeek-V4-Pro` - DeepSeek V4 Pro, 1,048,576 token context, hosted reasoning on/off
- `deepseek-ai/DeepSeek-V4-Flash` - DeepSeek V4 Flash, 1,048,576 token context, hosted reasoning on/off

The desktop GUI consumes this catalog and its reasoning option values from the core, so source-specific capability changes do not require a duplicated frontend model list.

### Custom Providers

The `custom_providers` section stores the providers you added with `/provider add`. It is a pointer plus a list:

```json
{
  "custom_providers": {
    "active_provider_id": "xkiro",
    "providers": [
      {
        "id": "xkiro",
        "name": "xkiro",
        "base_url": "https://api.xkiro.com/v1",
        "api_key": "...",
        "api_key_env": "",
        "format": "openai-chat",
        "enabled": true,
        "selected_model_id": "z-ai/glm-5",
        "selected_model_display_name": "z-ai/glm-5",
        "max_context_tokens": 200000,
        "max_tokens": 16384,
        "timeout": 60,
        "supports_vision": false,
        "thinking": true,
        "reasoning_effort": "max",
        "model_context_limits": {
          "z-ai/glm-5": 200000
        },
        "custom_headers": {},
        "models": [],
        "models_synced_at": 1771459200.0
      }
    ]
  }
}
```

- `id` is derived from the provider name and is what you type in `/provider <name> ...`. Renaming a provider changes `name` only.
- `format` is one of `openai-chat` (POST `/chat/completions`), `openai-responses` (POST `/responses`), or `anthropic` (POST `/messages` with `x-api-key`). It decides both how the model list is read and which transport runs the chat request. Type `base_url` as the gateway documents it, including any `/v1`: Reverie trims a pasted request path and, for `anthropic`, hands the SDK the root URL so the request does not land on `/v1/v1/messages`.
- The thinking trace is read from whichever surface the transport uses: `reasoning_content` (or `reasoning`/`thinking`) on Chat Completions deltas, `thinking` content blocks on `/messages`, and both `response.reasoning_text` and `response.reasoning_summary_text` events on `/responses` — a gateway that streams the raw trace rather than a summary is understood either way. Inline `<think>` tags are parsed as well.
- `api_key_env` names an environment variable to read the key from instead of storing it; a stored `api_key` wins when both are set.
- `models` is the catalog cached from the provider's own model-list endpoint, refreshed by `/provider <name> models`. `models_synced_at` is the epoch seconds of the last successful refresh. Alongside each model's context window, the catalog keeps whatever the gateway published about reasoning: whether the model supports it, the effort names it accepts, and its own default. Refresh the catalog after upgrading Reverie so a provider stored before this metadata existed picks it up.
- `model_context_limits` maps a lowercased model id to the context limit you confirmed for it. Reverie asks once, the first time you select that model, and reuses the saved value on every later selection; models you never select stay absent. A saved limit outranks the window the gateway published for that model and drives `max_context_tokens` at runtime. Edit it with `/provider <name> context 256k` (`128000`, `128k`, and `1.2m` are accepted; values outside 1,000-10,000,000 tokens are rejected, and unparseable entries are dropped on load).
- `reasoning_effort` is the depth to ask for, one of `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`, and defaults to `max`. `thinking` is the same setting seen as a switch, kept in agreement on load: `"thinking": false` reads as `off`, and `"reasoning_effort": "off"` turns the switch off. Set either with `/provider <name> thinking <depth>` (`off` and `toggle` still work); `/provider <name> thinking` with no argument lists the depths the selected model publishes.
- `max` is relative to the model, not a literal wire value. Reverie maps the depth you asked for onto the effort names the catalog published for the selected model, so `max` becomes `xhigh` for a model that lists it and `high` for a model that lists nothing — `high` being the deepest value every OpenAI-compatible gateway is known to accept. A depth below every published rung falls back to the shallowest one rather than dropping thinking. A model whose catalog entry says it cannot reason is believed and gets no reasoning fields at all; a catalog that simply stays silent still gets the full payload.
- Every request carries all the reasoning dialects at once, so a gateway only has to understand one of them: `reasoning_effort`, OpenRouter's `reasoning` object plus `include_reasoning`, Anthropic's `thinking` block, DashScope's `enable_thinking`/`thinking_budget`, Groq's `reasoning_format`, and vLLM/SGLang's `chat_template_kwargs` (with `clear_thinking: false` for GLM models, which otherwise discard the trace). Thinking budgets are sized to leave at least 1,024 tokens for the visible answer and are omitted entirely when the output cap is too small to split.
- A gateway that rejects the reasoning fields does not cost you the turn or the trace. Reverie retries with a narrower payload, dropping the most vendor-specific tier one at a time — `chat_template_kwargs`/`enable_thinking`/`thinking_budget`/`reasoning_format`, then `thinking`/`include_reasoning`, then `reasoning`, leaving plain `reasoning_effort` — and remembers which tier that provider and model accepted so the probe is not repaid on later turns. The memory is per-process and is not persisted, so a gateway that gains support for a field gets the full payload again after a restart. The stored setting is never rewritten.
- Asking for reasoning is not the same as being sent it. Some gateways reason internally — the tokens show up in the bill and the latency — but never forward the trace for certain models, which is a property of that gateway and model rather than a setting. If the thinking panel stays empty on one model while another model on the same provider fills it, the request side is working and the trace is being withheld upstream; trying the same model under a different `format` is the only thing left to check.
- `active_provider_id` selects which provider runs when `active_model_source` is `custom`. A provider needs a base URL, a resolvable key, and a selected model before it becomes usable.
- Up to 64 providers can be stored.

`/provider list` probes each provider's model-list endpoint in parallel and reports online state, latency, and model count. `/provider <name> test` instead sends one minimal chat request, which is the only way to verify sources with no catalog endpoint.

The Desktop app edits the same section under **Settings → 模型与提供商 → Custom Provider**, including the per-model context limit and the reasoning depth. The model list reports, per model, the depths that model publishes and the rung `max` currently resolves to. Stored API keys never leave the core: the desktop payload carries only a masked hint.

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

Theme presets are `default`, `dark`, `light`, `ocean`, `high-contrast`, and `minimal`. The `minimal` preset replaces decorative glyphs with plain terminal-safe markers. `tool_output_style` also accepts `minimal` for single-line, border-free tool results.
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
