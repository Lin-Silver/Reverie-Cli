# Harness Engineering in Reverie CLI

## Framing

This project now treats the agent stack in three nested layers:

- Prompt engineering clarifies the task and the local rules.
- Context engineering supplies the right repository and environment evidence.
- Harness engineering keeps the full execution loop stable across tools, execution rails, memory, evaluation, and recovery.

That framing was derived from two local references:

- `./最近爆火的 Harness Engineering 到底是个啥？一期讲透！.mp4`
- `./references/Claude Code SRC`

The important takeaway is that strong agent behavior does not come only from a better model or a better prompt. It comes from the shell around the model: task tracking, tool gating, execution rails, memory, evaluation, and recovery.

The video also frames the evolution clearly:

- Prompt engineering asks whether the model understood the request.
- Context engineering asks whether the model received the right information at the right time.
- Harness engineering asks whether the system can keep making the right moves across a long execution chain.

Its most practical breakdown is a six-layer harness:

- context boundaries
- tool system
- execution rails
- memory and state
- evaluation and observability
- constraints, checks, and recovery

## Reverie Capability Review

Reverie already had many strong harness components before this upgrade:

- A real task ledger through `task_manager` plus checklist artifacts in `artifacts/`.
- Repository-grounded context tooling through the Context Engine, retrieval, Git integration, and optional LSP.
- Audited workspace execution through `command_exec`.
- Session continuity through `SessionManager`, `MemoryIndexer`, automatic compaction, and handoff packets.
- Recovery surfaces through `OperationHistory` and `RollbackManager`.
- Extensibility through MCP, runtime plugins, and `SKILL.md` discovery.

The main gap was not missing primitives. The gap was that these primitives were not being reflected back into the agent loop in a coherent, runtime-aware harness model. In practice that meant:

- `/doctor` could report useful data, but the layer model was still too static.
- Prompt guidance did not explicitly describe the live harness state for the current workspace.
- Operation history was useful for rollback, but underexposed as part of the harness story.
- Task ledger, verification evidence, and recovery surfaces were more available than they were behavior-shaping.

## Landed Changes

This update makes Reverie more explicitly harness-driven in the same spirit as modern execution-first coding CLIs.

### 1. Runtime Harness Guidance Is Now Injected Into The Agent Prompt

`ReverieInterface` now builds a live harness guidance block and appends it to the system prompt context. The block summarizes:

- active mode
- visible tool roster
- task ledger status and a compact task snapshot
- verification trail from audited commands
- recent run-history trends
- continuity and recovery surfaces
- external capability surface from MCP, runtime plugins, and skills
- recovery-aware execution nudges

This turns the harness from a passive observability layer into an active behavior-shaping layer.

### 2. Harness Audit Layers Now Match The Real Execution Loop Better

`build_harness_capability_report()` evaluates the workspace across seven layers:

- goals
- context
- tools
- execution
- memory
- evaluation
- recovery

This matches the progression described in the video: the system must not only understand the task and get the right context, it must also stay on track, remember state, verify output, and recover from failure.

### 3. `/doctor` Now Surfaces Verification Posture And Run History

The doctor report now includes:

- explicit verification posture inferred from audited commands
- recent prompt-run history with score drift and verification coverage
- operation history in the workspace artifact summary
- updated layer language aligned to harness engineering
- stronger separation between evaluation and recovery

This makes the report more useful for diagnosing why an agent run felt unstable even when the raw tool surface looked strong.

### 4. Prompt Runs Now Leave A Lightweight Harness Trail

Prompt-mode runs now persist a compact harness snapshot into the workspace cache. Each snapshot records:

- mode, duration, and success
- workspace harness score
- active task lane
- explicit verification evidence
- auto-followup count

That gives Reverie a historical stability surface instead of a one-shot inspection view. `/doctor history` can now answer whether the harness is getting healthier or just looks healthy in a single snapshot.

### 5. Task Snapshot Became A First-Class Harness Signal

The harness layer derives a compact task snapshot from `task_list.json` or `Tasks.md`, including:

- active task
- next task
- whether more than one task is marked `IN_PROGRESS`
- compact sample lines for prompt injection and dashboards

This is a small change with large behavioral impact: long-running agent quality often depends on whether the system has a clear execution lane right now.

## Claude Code Patterns Reflected Here

The Claude Code source tree is strong not because of one feature, but because it keeps the execution shell visible and structured. The Reverie upgrade above intentionally follows the same direction:

- keep tool and workflow state visible to the model, not only to the UI
- make progress, evaluation, and recovery separate concerns
- keep verification evidence and prompt-run history visible to the runtime shell
- keep session continuity and handoff infrastructure first-class
- prefer progressive capability exposure over one giant static prompt dump
- treat execution history as part of system reliability, not just debugging metadata

This update does not attempt to clone Claude Code. It adapts the most relevant harness ideas to Reverie's existing architecture.

## Next High-Leverage Follow-Ups

The next meaningful upgrades are now clearer:

1. Add an explicit evaluator path that can validate the executor's output independently, instead of relying mostly on the same loop that produced the result.
2. Add optional isolated execution lanes for risky work, ideally with a worktree-style model for larger coding tasks.
3. Add richer recovery playbooks for common failure classes such as flaky tests, partial edits, or tool-schema mismatch.
4. Add more explicit context-refresh and handoff transitions for very long runs, similar to the clean handoff patterns seen in advanced coding-agent systems.

## Practical Reading

If you want the short version:

- Prompt engineering helps the model understand the ask.
- Context engineering helps the model see the right facts.
- Harness engineering helps the whole system keep working until the job is actually done.

Reverie now reflects that distinction more directly in its doctor surface, prompt guidance, and prompt-run history.
