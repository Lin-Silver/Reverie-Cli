# Harness Engineering

Reverie treats its agent stack as three connected layers:

- Prompt engineering states the task and local rules.
- Context engineering supplies repository and environment evidence.
- Harness engineering keeps long execution chains observable, constrained, recoverable, and verifiable.

## Runtime Model

The active harness combines:

- a task ledger and compact active-task snapshot;
- Context Engine retrieval, Git evidence, memory, and optional LSP data;
- audited workspace tools, MCP servers, runtime plugins, and skills;
- sessions, compaction, handoff packets, operation history, and rollback;
- verification evidence from commands and tests;
- prompt-run history and recovery playbooks.

`ReverieInterface` injects a bounded harness summary into the agent context. It includes the active mode, visible tools, task state, verification trail, recent run trends, continuity surfaces, and available external capabilities.

## Capability Report

`build_harness_capability_report()` evaluates seven layers:

1. goals;
2. context;
3. tools;
4. execution;
5. memory;
6. evaluation;
7. recovery.

The report also derives a closure gate:

- `ready`: active work and verification allow the run to close;
- `continue`: meaningful work or evidence is still missing;
- `blocked`: a concrete failure requires recovery or user input.

This gate is independent from model confidence. It uses task state, command failures, verification evidence, tool-call mismatches, checkpoints, and Git workspace state.

## Diagnostics and Recovery

`/doctor` reports the harness layers, verification posture, recent prompt runs, workspace artifacts, operation history, and closure state. Prompt-mode runs persist a compact snapshot containing mode, duration, result, harness score, task lane, verification evidence, and automatic follow-up count.

Recovery playbooks cover common failure classes such as failing verification, schema mismatches, multiple active task lanes, missing checkpoints, and recent harness regression. They provide guidance; only explicitly authorized tools may mutate the workspace.

## Task and History Signals

The harness reads the current task artifact and identifies the active task, next task, multiple in-progress lanes, and a compact checklist sample. Operation history and prompt-run history are reliability inputs rather than transcript decoration.

The source of truth remains the runtime state and its tests. This guide describes implemented behavior only. Planned harness work is maintained in the project [Roadmap](ROADMAP.md).
