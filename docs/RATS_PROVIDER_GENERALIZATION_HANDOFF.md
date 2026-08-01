# Reverie CLI RATS Provider-Generalization Handoff

This document is a ready-to-use task brief for the next coding agent. It asks
for a structural cleanup of Reverie CLI's RATS client without inventing support
for applications that do not exist yet.

## Canonical product statement

Use this wording consistently in architecture, UI, help text, and code comments:

> RATS is the Reverie ecosystem's multi-provider agentic-tool runtime and
> service layer. RTP is its versioned tool protocol. Explicitly supported
> Reverie/Rilance applications can be RATS providers, while Reverie CLI is the
> client, management center, active-provider selector, and AI scheduling
> environment. Reverie Engine is currently the only implemented and verified
> provider in the user-selectable production list; it is not the only provider
> permitted by the RATS architecture.

Preserve the distinction between these two facts:

1. **Architecture:** RATS supports multiple explicitly allowlisted
   Reverie/Rilance provider products.
2. **Current availability:** the production registry and active selector
   currently contain only `reverie.engine`.

Do not describe Reverie Engine as the unique, permanent, or protocol-defined
RATS provider. Do not add fictional future providers to the production list to
demonstrate extensibility.

## Repository and current verified baseline

Work in the local repository:

```text
G:\Reverie\Reverie-Cli
```

At the time this handoff was written, the recent RATS commits were:

```text
1077522 Document fixed-provider RADE contract
b41f6df Harden RATS presence discovery and diagnostics
b238a39 Add RATS Engine integration
```

The recorded verification baseline is:

- focused RATS provider tests: 5/5;
- Python suite: 827/827;
- desktop suite: 53/53;
- TypeScript typecheck: pass;
- desktop production build: pass;
- real Reverie CLI to Reverie Engine RTP E2E: pass.

Re-check the actual HEAD, worktree, dependencies, and test counts before making
changes. These numbers are evidence from the previous slice, not permanent
expectations.

## Non-negotiable constraints

- Read `docs/RATS_RTP.md`, `docs/DEVELOPMENT.md`, `docs/ROADMAP.md`, and the
  existing RATS tests before editing.
- Preserve unrelated local changes. Stop and report overlap instead of
  overwriting user work.
- Work locally only. Do not push, publish, open a pull request, or modify the
  GitHub remote.
- Keep provider discovery explicit and allowlisted. Do not add port scanning,
  network broadcast, arbitrary MCP discovery, or a third-party service market.
- A provider appears only after its executable-local descriptor passes a live
  RTP identity handshake.
- A discovered provider remains unavailable to AI tools until the user
  explicitly enables it and chooses permissions.
- Never expose or persist control/session tokens in Electron, renderer state,
  settings, logs, diagnostics, or model prompts.
- Keep fast-fail deadlines and bounded diagnostics.
- Make the minimum coherent refactor. Do not rewrite unrelated CLI, provider,
  model, plugin, MCP, or desktop systems.
- Use one clean local commit for this provider-generalization system. Commit
  messages must not contain AI/model attribution or `Co-Authored-By` lines.

## Current Engine-specific coupling to audit

The implementation correctly validates a fixed production allowlist, but many
client names assume that every provider is an Engine. Inspect at least:

### Python runtime

- `ReverieCli-py/reverie/rats.py`
  - `RATS_SUPPORTED_PROVIDERS` already behaves like a registry but contains
    Engine-specific dictionary conventions.
  - settings key `enabledEngines`;
  - `add_engine()` and `set_engine_enabled()`;
  - selection lookup keyed only by executable;
  - discovery-root derivation assumes the Engine layout;
  - state payload and error messages use Engine terminology.
- `ReverieCli-py/reverie/sdk_bridge.py`
  - actions such as `ratsAddEngine` and Engine-specific enable operations.
- `ReverieCli-py/reverie/tools/rats_catalog.py`
  - aliases, tags, descriptions, and parameter help say Engine rather than
    provider.
- `ReverieCli-py/reverie/tools/rats_dynamic.py`
  - `engine_tool_name`, Engine-only tags, and fallback descriptions.
- `ReverieCli-py/tests/test_rats_runtime.py`
  - existing Engine fixtures must remain valid while provider-neutral behavior
    gains focused coverage.

### Desktop and protocol types

- `ReverieCli-ui/src/types.ts`
  - `RatsEngineSelection` and `enabledEngines`.
- `ReverieCli-ui/src/core-protocol.ts`
  - `ratsAddEngine` and other Engine-specific payload names.
- Electron preload/main bridge definitions for `selectRatsEngine()` and the
  matching request actions.
- `ReverieCli-ui/src/App.tsx`
  - `addEngine`, buttons such as `登记 Engine`, path labels, empty state,
    offline selection text, and discovery descriptions.
- `ReverieCli-ui/src/i18n.tsx`
  - English translations that still define every provider as an Engine.
- `ReverieCli-ui/src/App.interaction.test.tsx`
  - Engine-specific state and picker mocks.

Historical changelog entries may continue to say that Engine was the first or
only provider supported at that release. Do not rewrite accurate history as if
multiple providers were already shipped.

## Required target design

### 1. Provider registry

Replace ad hoc Engine assumptions with a small typed provider specification,
for example a Python dataclass or equivalent immutable record containing:

- `provider_id`;
- expected product identity;
- allowed service kinds;
- discovery-layout strategy;
- executable validation policy;
- supported permission classes or capability constraints;
- user-facing product label.

The production registry must still contain exactly one entry:

```text
reverie.engine / Reverie Engine / builtin
```

The registry must make a future second allowlisted provider an additive entry,
not require copying or renaming Engine-specific runtime logic.

### 2. Provider-neutral settings

Introduce a versioned settings shape using provider-neutral names, such as
`enabledProviders` or `selections`, with at least:

- stable `providerId`;
- executable path;
- requested permissions;
- any provider-specific discovery-root identity required for reconnection.

Implement a deterministic migration from the current `enabledEngines` shape.
Existing users must not lose their saved Engine executable or permissions.
Write migration tests and ensure settings remain executable-local under
`.reverie/rats`.

Do not silently accept unknown provider IDs. Preserve the explicit production
registry and diagnostic reason for unsupported providers.

### 3. Provider-neutral runtime/API names

Generalize new internal APIs and state fields toward names such as:

- `register_provider_executable()`;
- `set_provider_enabled()`;
- `RatsProviderSelection`;
- `enabledProviders`;
- `native_tool_name`;
- `ratsRegisterProvider`.

If compatibility aliases are needed for the existing desktop/core protocol,
keep them as a narrow migration layer with tests and a removal note. Do not
maintain two independent implementations.

Stable on-disk data and desktop-to-core protocol changes need an explicit
schema/version or compatibility strategy. Avoid a flag-day migration that
breaks packaged clients.

### 4. Provider-neutral tool exposure

- Generate model-facing qualified names from `provider_id`, service ID, and
  native tool name without Engine-only constants.
- Prevent collisions when two providers expose the same native tool name.
- Make catalog descriptions and tags say RATS provider/native tool by default.
- Provider-specific metadata may add `reverie-engine` tags for the Engine entry,
  but the base wrapper must not do so unconditionally.
- Continue progressive definition loading; do not inject every schema into the
  system prompt.
- Keep tools with missing request schemas visible in the compact catalog but
  unavailable as direct model functions.

### 5. Desktop active-provider selector

Update the RATS page so the product model is clear even while only one provider
exists:

- page introduction: RATS supports explicitly approved Reverie/Rilance
  providers;
- availability note: currently only Reverie Engine is implemented and appears
  in the selectable list;
- use generic labels such as `Register provider application`, `Provider
  executable`, `Saved but offline`, and `Supported provider` where appropriate;
- keep the displayed provider product and provider ID from live descriptor/
  handshake data;
- retain explicit enable and permission controls;
- retain the diagnostic drawer and rejection reasons;
- do not display placeholder cards or download buttons for products that do not
  exist.

The file picker may initially recognize only Reverie Engine because it is the
only registered product, but that specialization should live in the provider
registry/adapter rather than define the whole RATS UI model.

### 6. Tests proving extensibility without fictional production support

Add a test-only second provider specification through dependency injection or a
temporary registry fixture. Do not place it in the production allowlist.

Tests should prove:

- the production registry contains only `reverie.engine`;
- RATS itself is not hard-coded to one provider;
- settings migrate from `enabledEngines` without data loss;
- two injected allowlisted providers can coexist without selection, session,
  catalog, tool-name, or diagnostic collisions;
- an unknown provider remains rejected immediately;
- descriptor root and live identity validation use the selected provider spec;
- offline entries do not appear as live services;
- explicit enablement is still required;
- tokens and arguments remain absent from persisted/UI/log state;
- Engine-focused behavior and the real Engine RTP E2E remain unchanged.

## Documentation updates

Update current product documentation, UI help, and code comments to distinguish
architecture from availability. The preferred short statement is:

> RATS supports multiple explicitly approved Reverie/Rilance providers. Reverie
> Engine is currently the only implemented provider in the active selection
> list.

Do not claim that a second provider is implemented, downloadable, installed, or
verified until a real application and cross-product E2E exist.

## Verification commands

Use the repository's existing local environments. At minimum run:

```powershell
cd "G:\Reverie\Reverie-Cli\ReverieCli-py"
& ".\venv\Scripts\python.exe" -m pytest -q tests\test_rats_runtime.py
& ".\venv\Scripts\python.exe" -m pytest -q

cd "G:\Reverie\Reverie-Cli\ReverieCli-ui"
npm test
npm run typecheck
npm run build
```

Also run the existing real Engine RTP E2E against the currently verified local
Reverie Engine binary. Discover its exact command from the current tests/docs;
do not invent a replacement or report it passing unless actually executed.

For UI changes, launch the real Windows desktop and inspect the RATS page at
normal and narrow widths. Verify wording, cards, enable controls, permissions,
offline selections, logs, empty state, focus order, overflow, and localization.
Automated interaction tests do not establish visual correctness.

## Commit and handoff acceptance

Before staging:

```powershell
git status --short
git diff
git diff --check
```

The final handoff must report:

- the provider-neutral architecture implemented;
- exact settings/protocol migration behavior;
- why the production active-provider list still contains only Engine;
- focused, full Python, desktop, typecheck, build, E2E, and real-window results;
- the local commit hash;
- any remaining unverified behavior;
- confirmation that no push or remote mutation occurred.

Do not mark this task complete after documentation-only renaming. Completion
requires the Python runtime, settings migration, desktop/core protocol, dynamic
tool wrappers, UI, tests, and current Engine E2E to agree on the provider-neutral
model.
