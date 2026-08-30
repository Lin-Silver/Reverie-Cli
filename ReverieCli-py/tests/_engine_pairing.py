"""Locate the paired Reverie Engine editor binary for real RTP pairing tests.

Reverie-Cli and Reverie Engine are separate local repositories, so the tests that
exercise a genuine RTP session need the Engine executable. Gating those tests
behind an environment variable alone made them skip silently on every ordinary
run, which let an Engine tool-contract change (synchronous to bounded async cell
streaming, `reverie.world-streaming/1` to `/2`) drift undetected for a whole
development cycle.

Discovery therefore falls back to the sibling Engine worktree: an explicit
`REVERIE_RATS_ENGINE_BIN` still wins for out-of-tree builds, but a normal
checkout runs the pairing tests by default so contract drift turns the suite red.
"""

from __future__ import annotations

import os
from pathlib import Path

ENGINE_BIN_ENV = "REVERIE_RATS_ENGINE_BIN"

# The provider executable RATS validates. The `.console.exe` wrapper launches it
# but is not itself the process the descriptor identifies.
ENGINE_BINARY_NAME = "reverie.windows.editor.x86_64.exe"
_CONSOLE_SUFFIX = ".console.exe"

# Checked under each ancestor of this repository, nearest first.
_SIBLING_BIN_DIRS = (
    Path("Reverie Engine") / "Reverie Engine" / "bin",
    Path("Reverie Engine") / "bin",
)


def _provider_binary(binary: Path) -> Path:
    """Map a console wrapper onto the provider executable beside it."""
    if binary.name.lower().endswith(_CONSOLE_SUFFIX):
        provider = binary.with_name(binary.name[: -len(_CONSOLE_SUFFIX)] + ".exe")
        if provider.is_file():
            return provider
    return binary


def discover_engine_binary() -> Path | None:
    """Return the Engine editor binary to pair with, or None when unavailable."""
    override = str(os.environ.get(ENGINE_BIN_ENV, "")).strip()
    if override:
        return _provider_binary(Path(override).expanduser().resolve())
    for ancestor in Path(__file__).resolve().parents:
        for relative in _SIBLING_BIN_DIRS:
            candidate = ancestor / relative / ENGINE_BINARY_NAME
            if candidate.is_file():
                return candidate
    return None


def engine_pairing_skip_reason() -> str:
    """Explain how to supply an Engine binary when discovery found none."""
    return (
        "No Reverie Engine editor binary was discovered beside this repository; "
        f"build one or set {ENGINE_BIN_ENV} to run the real Engine/Cli RTP pairing."
    )


# Response `schema` identifiers this repository pins on the live Engine. Each
# entry is a cross-repository contract, so keeping them in one table means an
# Engine bump surfaces as a single reviewed line here instead of an opaque
# assertion failure deep inside the pairing test.
ENGINE_RESPONSE_SCHEMAS = {
    "animation.configure": "reverie.animation-configuration/1",
    "animation.status": "reverie.animation-playback/1",
    "world.create_region": "reverie.world-region/1",
    "world.create_cell": "reverie.world-cell/1",
    "world.streaming_status": "reverie.world-streaming/2",
    "task.events": "reverie.rtp.task/1",
}


def assert_response_schema(tool: str, payload: dict) -> None:
    """Assert one Engine response contract, naming the drift when it breaks."""
    expected = ENGINE_RESPONSE_SCHEMAS[tool]
    actual = payload.get("schema")
    assert actual == expected, (
        f"Engine cross-repository contract drift: {tool} reports schema {actual!r} "
        f"but this repository pins {expected!r}. Review the Engine change, adopt "
        f"the new response contract in the pairing test, and update "
        f"ENGINE_RESPONSE_SCHEMAS in tests/_engine_pairing.py."
    )


# The retry contract, pinned the other way round from the schema table above.
#
# `hello` publishes two columns this client branches on: per-operation `effects`
# (what re-sending does) and per-error `retry` (whether the failure proves the
# request never took effect). Mirroring all 11 operation rows and all 26 error
# rows here would make every benign Engine addition red for no reason, so this
# table names only the rows whose *meaning* the retry loop depends on; the rest
# are held to invariants that need no per-row maintenance.
#
# Each named row is a decision that would silently reverse if the Engine changed
# it, because the client would keep obeying the contract and start doing the
# wrong thing.
ENGINE_PINNED_EFFECTS = {
    # The row that makes `effects` necessary at all: an unsafe failure on a
    # mutating operation is the one case a retry may double-execute.
    "tool.call": "mutating",
    # Opening twice converges on one live session, which is what permits the
    # retry that `descriptor_update_failed` would otherwise forbid.
    "session.open": "idempotent",
    "hello": "none",
    "status": "none",
}

# code -> (retryable, retry)
ENGINE_PINNED_ERROR_RETRY = {
    # The call was queued and may still be running: the wait timed out, it was
    # not cancelled. This is the row `retry` exists for.
    "MAIN_THREAD_TIMEOUT": (True, "unsafe"),
    # Raised before the call is queued, so nothing ran.
    "MAIN_THREAD_UNAVAILABLE": (True, "safe"),
    # The clock is checked before dispatch at both raise sites.
    "deadline_exceeded": (True, "safe"),
    # Retryable *and* unsafe: the previous session's tasks were already
    # cancelled before the descriptor write failed.
    "descriptor_update_failed": (True, "unsafe"),
    # A permanent client mistake. Pinned so a well-meaning "make it retryable"
    # change cannot turn a typo into a backoff loop.
    "unknown_operation": (False, "never"),
    "unauthorized": (False, "never"),
}

RETRY_SEMANTICS_FEATURE = "error.retry_semantics"


def assert_retry_contract(capabilities, rejections=None) -> None:
    """Assert the live service's retry contract against this repository's pins.

    Two kinds of assertion, deliberately: the named rows above, and invariants
    that hold for every row whether or not this repository has heard of it. The
    invariants are what let the Engine add an error code without touching the
    Cli — the property the runtime claims — while still failing if an addition
    is unparseable or self-contradictory.
    """
    from reverie.rats_contract import (
        EFFECTS_VALUES,
        RETRY_NEVER,
        RETRY_VALUES,
    )

    assert capabilities.declared, (
        "The live service published no capability contract; the client fell back "
        "to its built-in guesses, so nothing below would be measuring the Engine."
    )
    assert not (rejections or []), (
        "This client refused part of the live capability contract, which means the "
        f"two repositories disagree about its shape: {rejections}"
    )
    assert capabilities.has_feature(RETRY_SEMANTICS_FEATURE), (
        f"The live service does not announce {RETRY_SEMANTICS_FEATURE!r}, so a "
        "client cannot tell a service that publishes retry semantics from one "
        "that omits them. Engine feature list drift."
    )

    for role, expected in ENGINE_PINNED_EFFECTS.items():
        assert capabilities.declares_role(role), (
            f"The live service no longer declares the {role!r} operation, which "
            "this repository pins the effects of."
        )
        actual = capabilities.effects(role)
        assert actual == expected, (
            f"Engine cross-repository contract drift: {role} declares effects "
            f"{actual!r} but this repository pins {expected!r}. A retry decision "
            "reverses on this; review the Engine change and update "
            "ENGINE_PINNED_EFFECTS in tests/_engine_pairing.py."
        )

    for code, (retryable, retry) in ENGINE_PINNED_ERROR_RETRY.items():
        assert capabilities.describes_error(code), (
            f"The live service no longer declares the {code!r} error row, which "
            "this repository pins the retry semantics of."
        )
        spec = capabilities.error(code)
        assert (spec.retryable, spec.retry) == (retryable, retry), (
            f"Engine cross-repository contract drift: {code} declares "
            f"retryable={spec.retryable!r} retry={spec.retry!r} but this "
            f"repository pins retryable={retryable!r} retry={retry!r}. Review the "
            "Engine change and update ENGINE_PINNED_ERROR_RETRY in "
            "tests/_engine_pairing.py."
        )

    # Invariants over every published row, including ones added since this file
    # was written. Read off `effects_by_role` rather than through `effects()`,
    # which substitutes the conservative default for anything unstated and would
    # therefore pass on a service that declared nothing at all.
    for role in sorted(capabilities.roles):
        declared = capabilities.effects_by_role.get(role)
        assert declared in EFFECTS_VALUES, (
            f"The live service declares effects {declared!r} for {role!r}, which "
            "no client can evaluate; the client would fall back to treating it "
            "as mutating and silently lose every retry on it."
        )
    for code in sorted(capabilities.errors):
        spec = capabilities.error(code)
        assert spec.retry in RETRY_VALUES, (
            f"The live service declares retry {spec.retry!r} for {code!r}, which "
            "no client can evaluate."
        )
        # The two columns answer different questions but cannot disagree: a row
        # that is not retryable has nothing to say about re-sending, and a row
        # that is retryable has to say what re-sending would do.
        assert (spec.retry == RETRY_NEVER) == (not spec.retryable), (
            f"The live service declares retryable={spec.retryable!r} with "
            f"retry={spec.retry!r} for {code!r}; a client obeying one column "
            "would contradict the other."
        )

    # The undeclared-code fallback, which is what makes an unknown code
    # classifiable instead of a guess.
    unheard_of = "a_code_this_repository_has_never_seen"
    assert not capabilities.describes_error(unheard_of)
    fallback = capabilities.error(unheard_of)
    assert (fallback.retryable, fallback.retry) == (False, RETRY_NEVER), (
        "The live service's declared default for undeclared error codes is "
        f"retryable={fallback.retryable!r} retry={fallback.retry!r}; a client "
        "would retry codes it cannot reason about."
    )

    # And the composition, which is the part neither repository can prove alone:
    # the client's decision function driven by the live service's declarations.
    assert capabilities.may_retry("tool.call", "MAIN_THREAD_TIMEOUT") is False, (
        "A mutating operation whose failure may still be running was judged "
        "retryable against the live contract."
    )
    assert capabilities.may_retry("session.open", "descriptor_update_failed") is True, (
        "An idempotent operation was refused a retry on an unsafe-but-retryable "
        "failure, so the two columns are not both being read."
    )
    assert capabilities.may_retry("tool.call", "deadline_exceeded") is True, (
        "A failure that proves nothing ran was refused a retry."
    )
    assert capabilities.may_retry("tool.call", "unauthorized") is False, (
        "A permanent failure was judged retryable against the live contract."
    )

