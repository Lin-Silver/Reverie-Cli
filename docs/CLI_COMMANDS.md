# CLI Command Reference

This reference is aligned with `reverie/cli/help_catalog.py`, which is the source of truth for command names, summaries, and examples.

## Core

| Command | Description |
| --- | --- |
| `/help` | Open the interactive help browser, or show `/help <command>` / `/help all` |
| `/status` | Show active model, provider source, session, and runtime health |
| `/doctor` | Audit the current workspace harness across goals, context, tools, execution, memory, evaluation, and recovery, including a closure gate, recovery playbooks, and run-history trends |
| `/clear` | Clear the terminal output without touching session state |
| `/clean` | Delete the current workspace project cache, checkpoints, and command audit history |
| `/exit` | Exit Reverie with confirmation |
| `/quit` | Alias of `/exit` |

Notes:

- `/clean` removes the active project's cache root under `<app_root>/.reverie/project_caches/<project-key>/`.
- If legacy workspace-local `.reverie/context_cache` or `.reverie/security` folders still exist, `/clean` removes those too.

## Models and Modes

| Command | Description |
| --- | --- |
| `/model` | Open the standard model selector |
| `/model add` | Add a standard model preset |
| `/model delete <number>` | Delete a standard model preset |
| `/subagent` | Open the base-Reverie Subagent roster TUI |
| `/subagent create` | Select a model and create a Subagent identified by ID |
| `/subagent list` | Show configured Subagents, model sources, colors, and status |
| `/subagent model <id>` | Change a Subagent's default model |
| `/subagent run <id> <task>` | Run a direct delegated task through a Subagent |
| `/subagent delete <id>` | Delete a configured Subagent |
| `/mode` | Show current mode and available modes. All modes share Context Engine; the selected mode changes the workflow and specialized tools. |
| `/mode reverie` | Switch to the general-purpose coding mode |
| `/mode reverie-atlas` | Switch to the document-driven spec development mode |
| `/mode reverie-gamer` | Switch to the game-development mode |
| `/mode reverie-ant` | Switch to the long-running execution and verification mode |
| `/mode spec-driven` | Switch to the spec authoring mode |
| `/mode spec-vibe` | Switch to the lighter spec implementation mode |
| `/mode writer` | Switch to the writing and narrative continuity mode |
| `/mode computer-controller` | Switch to the pinned NVIDIA desktop-autopilot mode |

Subagents are enabled only in base `reverie` mode. They inherit the active Reverie system prompt, tool/plugin/MCP/skill surface, and workspace context, but each configured Subagent stores only its ID, color, and selected default model.

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
| `/nvidia` | Show NVIDIA configuration |
| `/nvidia key` | Save the NVIDIA API key from build.nvidia.com/settings/api-keys |
| `/nvidia activate` | Switch active source to NVIDIA |
| `/nvidia model <model-id>` | Set the NVIDIA model |
| `/nvidia fast on\|off` | Toggle the GLM-5.1 fast interactive profile |
| `/nvidia endpoint <value>` | Set or clear NVIDIA endpoint override |
| `/modelscope` | Show ModelScope configuration |
| `/modelscope key` | Save the ModelScope token from modelscope.cn/my/access/token |
| `/modelscope activate` | Switch active source to ModelScope |
| `/modelscope model <model-id>` | Set the ModelScope model id |
| `/modelscope endpoint <value>` | Set or clear the Anthropic SDK base URL |

Request-based NVIDIA vision models can also consume inline chat attachments like `@image.png`.
Reverie also reads `NVIDIA_API_KEY` automatically when it is present, and Computer Controller mode pins the runtime to `qwen/qwen3.5-397b-a17b`.
ModelScope is called through the Anthropic SDK and reads `MODELSCOPE_API_KEY`, `MODELSCOPE_TOKEN`, or `MODELSCOPE_ACCESS_TOKEN` automatically when present. Its default model is `ZhipuAI/GLM-5.1`.

## Tools and Context

| Command | Description |
| --- | --- |
| `/tools` | Show tools visible to the active model/provider |
| `/tools all` | Show every loaded tool across modes with required fields, parameters, and descriptions |
| `/tools details` | Show detailed tool information for the current or selected mode |
| `/plugins` | Inspect the portable SDK/runtime depot and optional RC plugin tools |
| `/plugins sdk <plugin-id>` | Prepare `.reverie/plugins/<plugin-id>/runtime` and write an SDK manifest |
| `/plugins deploy <plugin-id>` | Let a plugin prepare its local SDK/runtime by downloading, extracting, or cloning into `.reverie/plugins/<plugin-id>/` |
| `/plugins run <plugin-id>` | Launch the detected portable SDK/runtime entry |
| `/search <query>` | Run a web search |
| `/index` | Rebuild the current workspace index |
| `/CE` | Show Context Engine status |
| `/CE compress` | Compress current conversation context |
| `/CE info` | Show context and prompt details |
| `/CE stats` | Show token statistics |
| `/tti models` | Open the TTI model selector |
| `/tti add` | Add a TTI model entry |
| `/tti <prompt>` | Generate an image using the default TTI model |

`/CE` is case-sensitive.

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
| `/engine create` | Create a Reverie Engine project skeleton |
| `/engine sample <name>` | Materialize a bundled engine sample |
| `/engine run` | Run the entry scene |
| `/engine validate` | Validate project layout and schemas |
| `/engine smoke` | Run deterministic smoke flow |
| `/engine video` | Export a playblast-style frame sequence or encoded video |
| `/engine renpy <script_path> [conversation_id] [entry_label]` | Import a Ren'Py `.rpy` dialogue script into Reverie's `dialogue.yaml` |
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

## Tips

- Use `/help <command>` for the latest detail and examples.
- When command behavior changes, update this file together with `help_catalog.py`.
- Prefer documenting command groups by user outcome instead of raw internal implementation.
