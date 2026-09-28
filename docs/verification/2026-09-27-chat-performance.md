# Chat performance and real Agnes task verification

Date: 2026-09-27. Windows, Electron 41.2.1, Reverie 2.5.0.

## Conversation loading

The baseline renderer uses `App.tsx` from `21c6fb472e53495b641f62e0848068bc92e2426d`.
Both renderer builds use the same surrounding assets and compiled Python kernel,
an isolated profile and a visible 1480×940 Electron window. The saved conversation
contains 1200 records; half contain Markdown paragraphs and a table. Each timing
includes the UI click, settled session state and two animation frames. This is one
local comparison, rather than a statistical claim about all machines or providers.

| Measurement | Baseline | Optimized |
| --- | ---: | ---: |
| First open of long conversation | 1422 ms | 178 ms |
| Return to cached long conversation | 2216 ms | 119 ms |
| Return to short conversation | 117 ms | 59 ms |
| Composer update | 57 ms | 16 ms |
| Longest observed main-thread task | 1183 ms | 90 ms |
| Initially mounted history records | 1200 | 60 |
| Scroll shift when prepending 60 records | not measured | 0 px |

Raw data: [baseline](chat-performance/before-final.json),
[optimized](chat-performance/after-final.json).

The later timeline/task-bar build was measured again with the same 1200-record
fixture and its newly compiled kernel. Across four local runs, first open ranged
from 287 to 861 ms and cached return from 185 to 777 ms; every run mounted 60
records and preserved a 0-pixel scroll anchor. One five-update typing probe had
a 38 ms median (33–108 ms). The run's longest main-thread task was 685 ms.
The old renderer on that same newly compiled kernel also showed large timing
swings (including a 2606 ms short-session switch), so these later single-machine
measurements do not establish a stable change in responsiveness from the new
timeline. Raw data: [final UI run 1](chat-performance/optimized-ux-final.json),
[run 2](chat-performance/optimized-ux-repeat.json),
[run 3](chat-performance/optimized-ux-third.json),
[run 4 with typing samples](chat-performance/final-ux.json), and
[old renderer control](chat-performance/optimized-old-samples.json).

The implementation renders recent history first and preserves the scroll anchor
when loading earlier records. Stable history/live Markdown is memoized. Unchanged
transcripts retain their cached objects through file revisions. Context statistics
are debounced, deduplicated, cancelled on navigation and read without activating
old sessions or rewriting memory. Repeated selection and pending-load/stream races
have regression coverage. Streaming follows the bottom only while the reader is
already there.

### Reproduce the local loading benchmark

Install the desktop dependencies and Python development environment; install
Playwright in that Python environment for the measurement driver. Build the
renderer/main process and directory kernel:

```powershell
cd ReverieCli-ui
npm ci
npm run build
npm run build:kernel
cd ..
$env:PERF_KERNEL = (Resolve-Path ReverieCli-ui\.kernel\reverie\reverie.exe).Path
& ReverieCli-py\venv\Scripts\python.exe scripts\verification\chat-performance\measure.py optimized
```

Outputs and isolated state are under `.audit/chat-perf/`. `PERF_RENDERER_ROOT`
can select a separately built baseline renderer. Run with no packaging process
competing for CPU/disk. The benchmark does not call an external model or use the
user's account configuration.

## Conversation timeline and task continuation

The desktop now renders assistant progress text and tool groups in transcript
order. Each group is collapsed by default and each tool row can be opened to
read its arguments and result. History preserves the same sequence after a
session reload. The composer task bar uses TaskManager's structured checklist:
its header shows the current item, and its expanded view shows the full list.

The desktop records the active prompt and saves stable history boundaries during
the turn. After an interrupted run, Continue task issues `resumePrompt` against
the existing session, without adding a user message or touching an unsent draft.
If a hard stop left a tool call without a recorded result, the agent records that
its outcome is unknown instead of repeating a possible side effect automatically.
One provider response may contain several tool calls; they are all handled before
the next model request. Execution remains serial so writes and commands retain
their original order.

The real Agnes website exercise below predates these interface controls. The
timeline, task bar, resume protocol and two-call response have separate renderer,
bridge and agent regression tests; the final packaged runtime smoke is reported
in the build section.

## Real Agnes task

The model built a Python standard-library/SQLite task-board website, using the
real Agnes API through the compiled desktop package. The generated application,
prompts and verification artifacts are retained locally under
`.audit/agnes-task/local-example/`; the sample application is excluded from the
GitHub submission at the user's request.

The initial generated tests failed (one failure and 14 errors out of 25).
Diagnostic feedback was supplied to Agnes, which repaired its application and
fixture. Application source was not manually patched. Final verification results
were rerun independently: 29 application tests and 7 HTTP contract tests passed,
including restart persistence and 25 concurrent POSTs. Chromium CRUD, keyboard
submission, counts, hostile-title text rendering and the 390-pixel layout passed.
The 200-request localhost GET probe measured p50 1.29 ms and p95 1.57 ms.

An additional local Agnes 3.0 Flash run exercised interruption and
`resumePrompt` against the frozen kernel. The process was stopped immediately
after its first recorded tool result, then resumed with no new user message.
The resumed session retained exactly one user message and generated
`slugify.py`, `test_slugify.py`, and `README.md`. Some Agnes API requests timed
out and required another `resumePrompt`; the final response succeeded and the
stored task state became `completed`, still with one user message. Independent
verification of the final Python files passed 7 unit tests and `compileall`.
Its workspace, profile, and diagnostic output remain local under
`.audit/agnes-resume/`.

## Runtime issues found by the task

The initial packaged run stalled in shadow Git initialization before writing a
file. A later run wrote the application but stalled while starting Python tests.
The repaired subprocess launch uses closed stdin and `CREATE_NO_WINDOW` on
Windows. Shadow Git now has deadlines
(15 seconds for initialization, 60 seconds for other operations). Pure task progress
updates skip workspace checkpoints. Real file mutations retain their checkpoints.

The command tool previously passed `&&` literally to the executable rather than
running a shell chain. It now rejects shell operators with a request to execute
commands separately, while retaining quoted operator text as data and existing
PowerShell cmdlet pipelines. The tool's description explains this before model
execution.

A successful repair/test run was followed by an automatic generic edge-case
verification turn, extending the run by about 200 seconds and ending in
preparatory prose. That unconditional extra turn was removed. Missing actual
edits or successful verification still trigger continuation. Explicit requirements
remain part of the batch instructions and are independently checked here.

The exact cause of the inherited-console startup wait was not isolated to a
specific Windows API. The launch change is verified by the subsequent packaged
provider run, rather than an assertion that a particular DLL caused the stall.

## Build and regression gates

- The staged renderer/main source passed TypeScript and translation checks.
- Full UI suite: 160 passed, 1 skipped across renderer and Electron. The final
  preference-default change passed its 10 focused tests.
- Python desktop bridge, agent continuation, token accounting, loading,
  workspace guard, command execution, permissions and batch prompt tests:
  193 passed.
- The actual Python directory kernel and desktop production renderer/main process
  were compiled. The packaged ASAR renderer's source map matched staged `App.tsx`.
  A packaged Electron smoke exercised the chronology, collapsible tool details,
  full task list, Continue button and unsent-draft preservation.
- Windows installer and portable executables were built locally; build outputs and
  provider credentials are excluded from the Git commit.
