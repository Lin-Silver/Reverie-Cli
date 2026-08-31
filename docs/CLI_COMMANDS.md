# CLI Command Reference

This reference is aligned with `reverie/cli/help_catalog.py`, which is the source of truth for command names, summaries, and examples.

## Core

| Command | Description |
| --- | --- |
| `/help` | Open the interactive help browser, or show `/help <command>` / `/help all` |
| `/status` | Show active model, provider source, session, and runtime health |
| `/doctor` | Audit the current workspace harness across goals, context, tools, execution, memory, evaluation, and recovery, including a closure gate, recovery playbooks, and run-history trends |
| `/total` | Show aggregate workspace usage, activity, regression, and runtime statistics |
| `/clear` | Clear the terminal output without touching session state |
| `/clean` | Delete the current workspace project cache, checkpoints, and command audit history |
| `/exit` | Exit Reverie with confirmation |
| `/quit` | Alias of `/exit` |

Notes:

- `/clean` removes the active project's cache root under `<app_root>/.reverie/projects/<project-path-key>/`.
- If legacy workspace-local `.reverie/context_cache` or `.reverie/security` folders still exist, `/clean` removes those too.

## Models and Modes

| Command | Description |
| --- | --- |
| `/model` | Open the standard model selector |
| `/model add` | Add a standard model preset |
| `/model delete <number>` | Delete a standard model preset |
| `/subagent` | Open the managed SubAgent roster TUI |
| `/subagent create` | Select a model and create a Subagent identified by ID |
| `/subagent list` | Show configured Subagents, model sources, colors, and status |
| `/subagent model <id>` | Change a Subagent's default model |
| `/subagent run <id> <task>` | Run a direct delegated task through a Subagent |
| `/subagent delete <id>` | Delete a configured Subagent |
| `/mode` | Show current mode and available modes. All modes share Context Engine; the selected mode changes the workflow and specialized tools. |
| `/mode reverie` | Switch to the general-purpose coding, automation, and long-running execution mode |
| `/mode reverie-atlas` | Switch to the document-driven spec development and spec-authoring mode |
| `/mode reverie-gamer` | Switch to the work-in-progress game-development mode |
| `/mode writer` | Switch to the writing and narrative continuity mode |
| `/mode computer-controller` | Switch to the pinned NVIDIA desktop orchestrator with an embedded Open Computer Use-compatible desktop runtime |

SubAgents are enabled in `reverie` and `computer-controller` modes, including NVIDIA-backed Controller sessions. Children have isolated sessions and selective context; the main Computer Controller remains the only desktop actor. Computer Controller is entered explicitly, but once active it may hand off to another mode with `switch_mode` when desktop control is no longer the primary job.

## Providers

| Command | Description |
| --- | --- |
| `/Geminicli` | Show Gemini CLI status |
| `/Geminicli login` | Validate or refresh Gemini CLI credentials |
| `/Geminicli model <model-id>` | Set the Gemini model |
| `/Geminicli endpoint <value>` | Set or clear Gemini endpoint override |
| `/codex` | Activate Codex and show the active setup |
| `/codex login` | Validate or refresh Codex credentials |
| `/codex model` | Open the Codex model selector |
| `/codex model <model-id>` | Set a Codex model directly |
| `/codex thinking` | Open the Codex reasoning selector |
| `/codex thinking <low\|medium\|high\|extra high>` | Set Codex reasoning depth |
| `/codex low\|medium\|high\|extra high` | Shortcut for reasoning depth |
| `/codex endpoint <value>` | Set or clear Codex endpoint override |
| `/codex auth <auto\|codex\|api_key\|none> [ENV_NAME]` | Select official/proxy authentication without putting a secret in command history |
| `/nvidia` | Show NVIDIA configuration |
| `/nvidia key` | Save the NVIDIA API key from build.nvidia.com/settings/api-keys |
| `/nvidia activate` | Switch active source to NVIDIA |
| `/nvidia model` | Open the NVIDIA model selector |
| `/nvidia model <model-id>` | Set the NVIDIA model, then choose model-specific thinking options when supported |
| `/nvidia thinking` | Reopen the thinking-option selector for the active NVIDIA model |
| `/nvidia endpoint <value>` | Set or clear NVIDIA endpoint override |
| `/modelscope` | Show ModelScope configuration |
| `/modelscope key` | Save the ModelScope token from modelscope.cn/my/access/token |
| `/modelscope activate` | Switch active source to ModelScope |
| `/modelscope model <model-id>` | Set the ModelScope model id |
| `/modelscope endpoint <value>` | Set or clear the OpenAI-compatible base URL |
| `/provider list` | List every source with its API-key flag and probe each one in parallel |
| `/provider list --no-probe` | Show the same table without any network calls |
| `/provider add` | Add a custom provider: name, base URL, API key, API request format |
| `/provider <name>` | Show one provider's endpoint, key state, format, and selected model |
| `/provider <name> models [model-id]` | Refresh the live model list and select a model |
| `/provider <name> test` | Verify a provider with one real minimal request |
| `/provider <name> use` | Make the provider the active model source |
| `/provider <name> context [limit]` | Set the context limit remembered for the selected model (`128000`, `128k`, `1.2m`) |
| `/provider <name> thinking on\|off\|toggle` | Turn thinking mode on or off for a custom provider (on by default) |
| `/provider <name> key` | Replace the stored API key |
| `/provider <name> url <base-url>` | Change a custom provider's base URL |
| `/provider <name> format` | Change a custom provider's API request format |
| `/provider <name> rename <label>` | Rename a custom provider |
| `/provider <name> enable\|disable` | Keep a custom provider stored but skip it while disabled |
| `/provider <name> remove` | Delete a custom provider and its saved key |

Request-based NVIDIA vision models can also consume inline chat attachments like `@image.png`.
Reverie also reads `NVIDIA_API_KEY` automatically when it is present, and Computer Controller mode pins the runtime to `meta/muse-glimmer-30b`.
ModelScope is called through OpenAI Chat Completions and reads `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` automatically when present. Its live-verified default model is `stepfun-ai/Step-3.7-Flash`. Model and reasoning selectors are generated from the core capability catalog.

`/provider` is the one surface over every source. `/provider list` mixes the built-in sources above with the providers you added yourself, shows which ones have an API key, and probes each reachable endpoint in parallel to report online state, latency, and how many models it publishes. Sources without a catalog endpoint (Codex, WebGemini) are marked "not probed"; use `/provider <name> test` for those.

`/provider add` asks for exactly four things - provider name, base URL, API key, and API request format (OpenAI Chat Completions, OpenAI Responses, or Anthropic Messages) - then calls the provider's model-list endpoint and opens the model selector. The provider, its key, its cached catalog, and the model you picked are written to `custom_providers` in the shared `config.json`, so the next session starts on the same model. `/provider <name> models` calls the endpoint again to pick up new models.

The first time you select one of a custom provider's models, Reverie asks for that model's context limit and saves it under that provider's `model_context_limits`. Selecting the same model again reuses the saved limit silently, and models you never select are never asked about; a saved limit outranks whatever window the gateway published. `/provider <name> context 256k` changes it later. Thinking mode is on by default for custom providers and can be turned off per provider with `/provider <name> thinking off`; a gateway that rejects the thinking flags degrades to a plain request for that turn instead of failing it.

Every stored provider also extends command completion, so once `xkiro` exists, `/provider xkiro models`, `/provider xkiro context`, `/provider xkiro thinking`, and the rest of its actions complete like built-in commands.

Raw stream frames (`[[REVERIE_EVENT]]{...}`) are internal protocol details rendered as activity lines; they are echoed verbatim only under `reverie --debug` or `REVERIE_DEBUG=1`.
## Tools and Context

| Command | Description |
| --- | --- |
| `/tools` | Show tools visible to the active model/provider |
| `/tools all` | Show every loaded tool across modes with required fields, parameters, and descriptions |
| `/tools details` | Show detailed tool information for the current or selected mode |
| `/mcp status` | Show configured MCP servers and discovery health |
| `/mcp list` | Alias of `/mcp status` |
| `/plugins` | Inspect the portable SDK/runtime depot and optional RC plugin tools |
| `/plugins sdk <plugin-id>` | Prepare `.reverie/plugins/<plugin-id>/runtime` and write an SDK manifest |
| `/plugins deploy <plugin-id>` | Let a plugin prepare its local SDK/runtime by downloading, extracting, or cloning into `.reverie/plugins/<plugin-id>/` |
| `/plugins models [list|plan|select|download|status]` | Choose and download game auxiliary models such as TRELLIS under `.reverie/plugins/game_models/` |
| `/plugins run <plugin-id>` | Launch the detected portable SDK/runtime entry |
| `/search <query>` | Run a web search |
| `/index` | Rebuild the current workspace index |
| `/CE` | Show Context Engine status |
| `/compact [focus]` | Compact the active conversation now, optionally prioritizing specific details |
| `/CE compress` | Compatibility form of `/compact` |
| `/CE info` | Show context and prompt details |
| `/CE stats` | Show token statistics |
| `/tti models` | Open the TTI model selector |
| `/tti add` | Add a TTI model entry |
| `/tti <prompt>` | Generate an image using the default TTI model |

MCP discovery runs silently in the background. A server's tools, resource access, prompt guidance, and tool descriptions become visible to the model only after that server passes discovery; pending and failed servers remain excluded. `/mcp status` and its refresh UI read the cached health snapshot without blocking the terminal on network checks.

`/CE` is case-sensitive.

Most slash commands can also be called directly from the executable without
entering the TUI. Drop the leading slash and pass the same arguments:

```bash
reverie setting status
reverie setting mode reverie
reverie tools search context
reverie compact "preserve failed tests and uncommitted files"
reverie --path C:\work\project setting workspace on
```

## Skills

| Command | Description |
| --- | --- |
| `/skills` | Show the detected skill summary and table |
| `/skills status` | Explicit status view |
| `/skills rescan` | Rescan repository, user, bundled, plugin, and legacy skill roots |
| `/skills path` | Show the scanned skill roots |
| `/skills inspect <skill-name>` | Show one skill's metadata and its on-demand `SKILL.md` body |
| `/skill` | Show which skills are pinned |
| `/skill <skill-name>` | Pin a skill so every following turn must load and follow it |
| `/skill unpin <skill-name>` | Release one pinned skill |
| `/skill clear` | Release every pinned skill |
| `/skill list` | Browse every detected skill and its pin state |

Skills are discovered from repository `.agents/skills` roots between the project root and the current workspace, `~/.agents/skills`, bundled skills, plugin-owned skills, and the legacy `.reverie/Skills` / `.reverie/skills` locations. The model initially receives only each skill's name, description, and path, then reads a body on demand through `skill_lookup`. Write `$skill-name` in a prompt to request one explicitly.

Pinning removes model-side selection for that entry: the skill is promoted into a mandatory system-prompt block, marked `[PINNED]` in the metadata list and in `skill_lookup` output, and drawn as a coloured tag in the input prompt and the live footer. A pin applies even when the skill's `agents/openai.yaml` sets `policy.allow_implicit_invocation: false`, since an explicit pin is a user instruction. Up to 4 skills can be pinned at once. Pins are session state and are never written to the configuration file, so restarting Reverie clears them.

In Reverie Desktop, typing `/skill <skill-name>` in the composer and pressing Enter converts the text into a pinned-skill chip above the input instead of sending a message; the Skills page lists every skill with its pin controls.

## Project and Rules

| Command | Description |
| --- | --- |
| `/setting` | Open the settings UI |
| `/settings` | Alias of `/setting` |
| `/setting status` | Print the settings dashboard |
| `/setting mode <mode>` | Change active mode |
| `/setting model` | Open the standard model selector |
| `/setting theme <theme>` | Change stored theme preset |
| `/setting auto-index on\|off` | Toggle startup indexing |
| `/setting status-line on\|off` | Toggle the live status line |
| `/setting tool-output compact\|condensed\|full` | Change how completed tool output is collapsed |
| `/setting thinking full\|compact\|hidden` | Change how streamed reasoning is displayed |
| `/setting stream on\|off` | Toggle streaming responses |
| `/setting timeout <seconds>` | Set API timeout |
| `/setting retries <count>` | Set retry budget |
| `/setting debug on\|off` | Toggle debug logging |
| `/setting workspace on\|off` | Toggle workspace config mode |
| `/setting rules` | Open the rules editor |
| `/rules` | List current custom rules |
| `/rules edit` | Open `rules.txt` in the default editor |
| `/rules add <text>` | Add a rule |
| `/rules remove <number>` | Remove a rule |
| `/permission` | Show the current approval policy and subcommand list |
| `/permission mode default\|auto_check\|strict` | Switch how tool calls are approved |
| `/permission threshold <none\|low\|medium\|high\|critical>` | Auto Check pauses at this reviewed risk and above |
| `/permission model follow` | Review tool calls with the main model |
| `/permission model <source> <name>` | Pin a dedicated reviewer model |
| `/permission readonly on\|off` | Strict mode: auto-allow provably read-only tools |
| `/permission review-read-only on\|off` | Auto Check: also review read-only tools |
| `/permission timeout <5-600>` | Reviewer request timeout in seconds |
| `/permission max-tokens <200-8192>` | Reviewer response token budget |
| `/permission fail-open on\|off` | Allow calls through when the reviewer itself fails |
| `/permission level <read_only\|workspace_write\|developer\|full_control>` | Change the hard capability ceiling |
| `/workspace` | Show workspace-config status |
| `/workspace enable` | Enable workspace-local config |
| `/workspace disable` | Return to the default profile |
| `/workspace copy-to-workspace` | Copy the default profile into the workspace profile |
| `/workspace copy-to-global` | Copy the workspace profile into the default profile |

Notes:

- `/rules edit` edits `rules.txt` inside the active project's cache directory.
- `/workspace enable` switches Reverie from the shared `.reverie/config.json` profile to the active project's cache `config.json`.

## Sessions and Recovery

| Command | Description |
| --- | --- |
| `/sessions` | Open the interactive session browser |
| `/history` | Show retained conversation history |
| `/history <count>` | Show only the latest `count` messages |
| `/rollback` | Open the rollback UI |
| `/rollback question` | Roll back to the previous user question |
| `/rollback tool` | Roll back to the previous tool call |
| `/rollback <checkpoint-id>` | Roll back to a specific checkpoint |
| `/undo` | Undo the latest rollback |
| `/redo` | Redo the latest undone rollback |
| `/checkpoints` | Open the checkpoint selector |
| `/operations` | Show operation history and rollback stats |

## Prompt editor shortcuts

On Windows, slash commands are suggested while typing. Use Up/Down to select a visible suggestion and Enter to accept it, or press Tab to complete directly. Outside a slash menu, Up/Down recalls prompt history and the recalled text remains editable.

| Shortcut | Action |
| --- | --- |
| `Left` / `Right` | Move one character |
| `Ctrl+Left` / `Ctrl+Right` | Move one word |
| `Ctrl+W` | Delete the previous word |
| `Ctrl+U` / `Ctrl+K` | Delete to the start/end of the current line |
| `Shift+Enter`, `Ctrl+Enter`, or `Ctrl+J` | Insert a newline |

Linux and macOS use the resize-aware prompt editor with live completion, editable history, `Ctrl+R` search, multiline input, and the unified `@` file picker. `Esc+Enter` submits and `Ctrl+J` inserts a newline.

`@` searches Context Engine indexed files and code symbols, not only visual media. Symbol selections insert `@path#Lstart-Lend`; image or video selections keep the existing inline-attachment behavior when the active model supports it. Before the index is ready, Reverie falls back to a workspace file scan.

## Session workflow commands

| Command | Action |
| --- | --- |
| `/export [json] [path]` | Export the active session as Markdown or JSON |
| `/copy-last` | Copy the last assistant response |
| `/rewind <message-count>` | Archive and rewind the active transcript |
| `/fork [message-count]` | Branch the conversation into a new session |
| `/session-search <query>` | Search message text across workspace sessions |

## Game Workflow

| Command | Description |
| --- | --- |
| `/gdd` | View the current game design document |
| `/gdd create` | Create a new GDD |
| `/gdd summary` | Generate a summary view of the GDD |
| `/gdd validate` | Validate structure and completeness of the GDD |
| `/gdd append` | Add a section to the GDD |
| `/gdd metadata` | Update metadata such as owner or status |
| `/gdd version list` | List existing GDD backups |
| `/gdd version create` | Create a timestamped GDD backup |
| `/gdd export html` | Export the GDD to HTML |
| `/assets` | Show grouped assets |
| `/assets analyze` | Summarize asset counts, size, and largest files |
| `/assets manifest` | Generate asset manifest |
| `/assets missing` | Find missing asset references |
| `/assets unused` | Find apparently unused assets |
| `/assets graph` | Analyze asset dependency usage |
| `/assets compress` | Get optimization recommendations |
| `/assets size` | Estimate asset footprint |
| `/assets naming` | Validate asset naming rules |
| `/assets atlas` | Build a sprite atlas plan |
| `/blueprint` or `/bp` | Show the current blueprint overview |
| `/blueprint create` | Create a game blueprint |
| `/blueprint analyze` | Analyze blueprint scope and complexity |
| `/blueprint slice` | Generate a vertical-slice plan |
| `/blueprint export` | Export the blueprint to Markdown |
| `/blueprint expand <system>` | Expand one gameplay system |
| `/scaffold` | Plan the recommended project structure |
| `/scaffold create` | Generate the project foundation |
| `/scaffold modules` | Generate the module-map document |
| `/scaffold pipeline` | Generate the content-pipeline document |
| `/engine` | Show the current Reverie Engine profile |
| `/engine scope [dimension] [genre] [quality] [world_structure]` | Check whether a game brief fits the supported engine scope |
| `/engine create` | Create a Reverie Engine project skeleton |
| `/engine sample <name>` | Materialize a bundled engine sample |
| `/engine run` | Run the entry scene |
| `/engine validate` | Validate project layout and schemas |
| `/engine smoke` | Run deterministic smoke flow |
| `/engine video` | Export a playblast-style frame sequence or encoded video |
| `/engine renpy <script_path> [conversation_id] [entry_label]` | Import a Ren'Py `.rpy` dialogue script into Reverie's `dialogue.yaml` |
| `/engine inspect-legacy <source_dir>` | Inspect a Godot, O3DE, or Ren'Py project before migration |
| `/engine migrate <source_dir> <output_dir>` | Create a Reverie Engine project from a supported legacy source |
| `/engine health` | Create a health report |
| `/engine benchmark` | Record coarse baseline measurements |
| `/engine package` | Create a portable runtime bundle |
| `/engine test` | Validate then smoke-test |
| `/modeling` | Inspect the Reverie-Gamer modeling stack and workspace |
| `/modeling setup` | Create modeling folders, manifests, docs, and pipeline files |
| `/modeling sync` | Regenerate the model registry from source/runtime folders |
| `/modeling stub <model_name>` | Create a starter `.bbmodel` in `assets/models/source/` |
| `/modeling primitive <type> <model_name>` | Generate a built-in primitive `.gltf` plus preview image |
| `/modeling validate-bbmodel <source_bbmodel>` | Validate a Blockbench `.bbmodel` without requiring Blockbench desktop or Ashfox |
| `/modeling export-bbmodel <source_bbmodel> [dest_name]` | Convert a supported cuboid `.bbmodel` into runtime `.gltf`, preview, and registry evidence |
| `/modeling import <runtime_export> [source_bbmodel] [preview_image] [dest_name]` | Import a runtime model plus optional source model and preview |
| `/modeling ashfox tools` | List available Ashfox MCP tools |
| `/modeling ashfox capabilities` | Show Ashfox capability metadata |
| `/modeling ashfox state [summary\|full]` | Read the active Blockbench project state through Ashfox |
| `/modeling ashfox validate` | Run Ashfox validation against the active model project |
| `/modeling ashfox export <format> <dest_path>` | Ask Ashfox to export the active model |
| `/modeling ashfox call <tool_name> <json_arguments>` | Call any Ashfox tool directly |
| `/blender status` | Inspect the built-in Blender modeling stack |
| `/blender setup` | Create Blender source/script/plan folders in the modeling workspace |
| `/blender script <model_name> <brief>` | Generate an auditable Blender Python authoring script without running Blender |
| `/blender script hero "Genshin / ZZZ style anime action character"` | Generate a richer stylized character blockout preset |
| `/blender script hero "AAA final character asset with high poly sculpt, retopo, UV unwrap, texture bake, rigged animation"` | Generate the production character pipeline preset with high-poly, retopo, UV, texture, material tuning, skinning, IK, rig, preview-action scaffolding, and black-box iteration evidence |
| `/blender create <model_name> <brief>` | Run Blender in background mode to save `.blend`, export `.glb`, render a preview, auto-audit the result, and sync the registry |
| `/blender run <script_path>` | Run a workspace-local Blender Python script through the built-in Blender workflow |
| `/blender validate <script_path>` | Validate a Blender script with Reverie's conservative static scan |
| `/blender audit <model_name>` | Audit generated `.blend`, `.glb`, texture set, validation report, production manifest, black-box iteration plan, material/skin/animation manifests, rig, IK, weights, sockets, collision proxies, and LOD gates |
| `/blender repair <model_name> [max_iterations]` | Consume the automatic repair queue, rerun Blender authoring, re-audit, and write repair history |
| `/blender sync` | Regenerate the model registry after Blender authoring work |
| `/playtest` or `/pt` | Create a playtest plan |
| `/playtest telemetry` | Generate telemetry schema |
| `/playtest gates` | Generate milestone quality gates |
| `/playtest analyze <session_log_path>` | Analyze a playtest session log |
| `/playtest feedback <feedback_path>` | Synthesize feedback from a file |

## Project memory tools

Project memory is integrated into Context Engine and normally called by the AI automatically. The underlying tool actions are `memory_manager` (`remember`, `list`, `get`, `correct`, `delete`, `consolidate`, `conflicts`, `status`) and `memory_retrieval` (`recall`, `answer`). See [Context Engine Project Memory](CONTEXT_ENGINE_MEMORY.md).

## Tips

- Use `/help <command>` for the latest detail and examples.
- When command behavior changes, update this file together with `help_catalog.py`.
- Prefer documenting command groups by user outcome instead of raw internal implementation.
