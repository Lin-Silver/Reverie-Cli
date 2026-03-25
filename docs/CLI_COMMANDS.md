# CLI Command Reference

This reference is aligned with `reverie/cli/help_catalog.py`, which is the source of truth for command names, summaries, and examples.

## Core

| Command | Description |
| --- | --- |
| `/help` | Open the interactive help browser, or show `/help <command>` / `/help all` |
| `/status` | Show active model, provider source, session, and runtime health |
| `/clear` | Clear the terminal output without touching session state |
| `/clean` | Delete the current workspace project cache, backups, and command audit history |
| `/exit` | Exit Reverie with confirmation |
| `/quit` | Alias of `/exit` |

Notes:

- `/clean` removes the active project's cache root under `.reverie/project_caches/<project-key>/`.
- If legacy workspace-local `.reverie/context_cache` or `.reverie/security` folders still exist, `/clean` removes those too.

## Models and Modes

| Command | Description |
| --- | --- |
| `/model` | Open the standard model selector |
| `/model add` | Add a standard model preset |
| `/model delete <number>` | Delete a standard model preset |
| `/mode` | Show current mode and available modes |
| `/mode reverie` | Switch to the general engineering mode |
| `/mode reverie-atlas` | Switch to the deep-research and document-driven mode |
| `/mode reverie-gamer` | Switch to the game-development mode |
| `/mode reverie-ant` | Switch to the planning/execution/verification mode |
| `/mode spec-driven` | Switch to structured spec-driven workflow |
| `/mode spec-vibe` | Switch to lighter spec workflow |
| `/mode writer` | Switch to writing/documentation mode |
| `/mode computer-controller` | Switch to NVIDIA-backed desktop control mode |

## Providers

| Command | Description |
| --- | --- |
| `/iflow` | Show iFlow status |
| `/iflow model` | Select an iFlow model |
| `/iflow endpoint <value>` | Set or clear iFlow endpoint override |
| `/qwencode` | Show Qwen Code status |
| `/qwencode login` | Validate or refresh Qwen Code credentials |
| `/qwencode model <model-id>` | Set the Qwen Code model |
| `/qwencode endpoint <value>` | Set or clear Qwen endpoint override |
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
| `/nvidia endpoint <value>` | Set or clear NVIDIA endpoint override |

Request-based NVIDIA vision models can also consume inline chat attachments like `@image.png`.

## Tools and Context

| Command | Description |
| --- | --- |
| `/tools` | Show tools visible in the current mode |
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
| `/setting status` | Print the settings dashboard |
| `/setting mode <mode>` | Change active mode |
| `/setting model` | Open the standard model selector |
| `/setting theme <theme>` | Change stored theme preset |
| `/setting auto-index on\|off` | Toggle startup indexing |
| `/setting status-line on\|off` | Toggle the live status line |
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
| `/engine health` | Create a health report |
| `/engine benchmark` | Record coarse baseline measurements |
| `/engine package` | Create a portable runtime bundle |
| `/engine test` | Validate then smoke-test |
| `/playtest` or `/pt` | Create a playtest plan |
| `/playtest telemetry` | Generate telemetry schema |
| `/playtest gates` | Generate milestone quality gates |
| `/playtest analyze <session_log_path>` | Analyze a playtest session log |
| `/playtest feedback <feedback_path>` | Synthesize feedback from a file |

## Tips

- Use `/help <command>` for the latest detail and examples.
- When command behavior changes, update this file together with `help_catalog.py`.
- Prefer documenting command groups by user outcome instead of raw internal implementation.
