"""The ``/rats`` slash command: the client-side surface for configuring RATS.

Before this command existed a RATS service could only be configured by editing
``.reverie/rats/settings.json`` by hand or by driving the desktop bridge. The
tests here hold three things in place:

* every registered command name resolves to a real method, so a registry entry
  can never again name a method that was never written;
* the runtime is reached through the app context rather than constructed here,
  and a session that has no runtime gets a reported error instead of a crash;
* each subcommand reaches the runtime call it claims to, with the arguments the
  user typed — including a provider id that is optional by shape.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.rats import RATS_CUSTOM_PROVIDER_SCHEMA, RATS_PROTOCOL, RATS_SETTINGS_VERSION, RatsRuntime


def _real_diagnostic_entry() -> Dict[str, Any]:
    """One journal entry written by the runtime itself, not a hand-typed shape.

    The renderer reads ``timestampUtc``. Typing that key into a fixture would let
    a rename in ``rats.py`` pass here and show a blank column in the terminal, so
    the fixture is produced by the code that owns the key.
    """
    runtime = RatsRuntime(_test_root("diagnostic-shape"))
    try:
        runtime._log_diagnostic(
            "settings.custom_provider_rejected",
            level="warning",
            provider_id="reverie.engine",
            reason="reserved_provider_id",
        )
        return dict(runtime._diagnostics[-1])
    finally:
        runtime.shutdown()


def _test_root(name: str) -> Path:
    root = (
        Path(__file__).resolve().parents[2]
        / "dist"
        / ".reverie"
        / "test-temp"
        / f"rats-cli-{name}-{uuid.uuid4().hex}"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


_REAL_DIAGNOSTIC_ENTRY = _real_diagnostic_entry()


class _FakeRuntime:
    """Records what the command asked for, and answers with a plausible state."""

    def __init__(self, root: Path, *, services: Optional[List[Dict[str, Any]]] = None) -> None:
        self.settings_path = root / ".reverie" / "rats" / "settings.json"
        self.diagnostics_path = root / ".reverie" / "rats" / "diagnostics.jsonl"
        self.calls: List[Tuple[str, tuple, dict]] = []
        self.raise_on: Dict[str, Exception] = {}
        self._services = services if services is not None else []
        self._custom: List[Dict[str, Any]] = []
        self.describe_result: List[Dict[str, Any]] = []

    # -- bookkeeping --------------------------------------------------------
    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))
        error = self.raise_on.get(name)
        if error is not None:
            raise error

    def names(self) -> List[str]:
        return [name for name, _args, _kwargs in self.calls]

    def args_for(self, name: str) -> Tuple[tuple, dict]:
        for recorded, args, kwargs in self.calls:
            if recorded == name:
                return args, kwargs
        raise AssertionError(f"{name} was never called; saw {self.names()}")

    # -- the surface the command uses --------------------------------------
    def _state(self) -> Dict[str, Any]:
        return {
            "protocol": RATS_PROTOCOL,
            "settingsVersion": RATS_SETTINGS_VERSION,
            "statePath": str(self.settings_path),
            "diagnosticsPath": str(self.diagnostics_path),
            "discoveryRoots": [str(self.settings_path.parent / "Services")],
            "configuredDiscoveryRoots": [str(self.settings_path.parent / "Services")],
            "enabledProviders": [],
            "supportedProviders": [
                {
                    "providerId": "reverie.engine",
                    "product": "Reverie Engine",
                    "serviceKinds": ["builtin"],
                    "label": "Reverie Engine",
                    "permissions": ["read", "run", "write"],
                    "toolTags": ["reverie-engine"],
                    "custom": False,
                },
                *(
                    {
                        "providerId": record["providerId"],
                        "product": record["product"],
                        "serviceKinds": record["serviceKinds"],
                        "label": record["label"],
                        "permissions": record["permissionClasses"],
                        "toolTags": record["toolTags"],
                        "custom": True,
                    }
                    for record in self._custom
                ),
            ],
            "customProviders": list(self._custom),
            "customProviderSchema": RATS_CUSTOM_PROVIDER_SCHEMA,
            "customProviderLimit": 16,
            "services": list(self._services),
            "scanDurationMs": 7,
            "rejectedDescriptorCount": 1,
            "diagnostics": [dict(_REAL_DIAGNOSTIC_ENTRY)],
            "updatedAt": "2026-08-30T00:00:01Z",
        }

    def state(self) -> Dict[str, Any]:
        self._record("state")
        return self._state()

    def refresh(self) -> Dict[str, Any]:
        self._record("refresh")
        return self._state()

    def register_provider_executable(self, provider_id, executable) -> Dict[str, Any]:
        self._record("register_provider_executable", provider_id, executable)
        return self._state()

    def set_provider_enabled(self, provider_id, executable, enabled, permissions) -> Dict[str, Any]:
        self._record("set_provider_enabled", provider_id, executable, enabled, permissions)
        return self._state()

    def remove_discovery_root(self, root) -> Dict[str, Any]:
        self._record("remove_discovery_root", root)
        return self._state()

    def define_custom_provider(self, definition) -> Dict[str, Any]:
        self._record("define_custom_provider", definition)
        record = {
            "schema": RATS_CUSTOM_PROVIDER_SCHEMA,
            "providerId": definition["providerId"],
            "product": definition["product"],
            "label": definition.get("label", definition["product"]),
            "serviceKinds": definition.get("serviceKinds", ["builtin"]),
            "permissionClasses": definition.get("permissionClasses", ["read"]),
            "toolTags": definition.get("toolTags", []),
            "discoveryRoot": ["ReverieLocal", "RATS", "Services"],
            "executableIdentity": "path",
            "executableProductNames": [],
            "executableError": "Select an existing executable.",
        }
        self._custom = [item for item in self._custom if item["providerId"] != record["providerId"]]
        self._custom.append(record)
        return self._state()

    def remove_custom_provider(self, provider_id) -> Dict[str, Any]:
        self._record("remove_custom_provider", provider_id)
        self._custom = [item for item in self._custom if item["providerId"] != provider_id]
        return self._state()

    def describe(self, service_id, names, *, provider_id: str = "") -> List[Dict[str, Any]]:
        self._record("describe", service_id, list(names), provider_id=provider_id)
        return list(self.describe_result)


def _service(**overrides) -> Dict[str, Any]:
    service = {
        "serviceId": "rats-4545-abc",
        "providerId": "reverie.engine",
        "serviceKind": "builtin",
        "product": "Reverie Engine",
        "productVersion": "0.1.dev",
        "executable": r"G:\Reverie\bin\reverie.windows.editor.x86_64.exe",
        "pid": 4545,
        "endpoint": "http://127.0.0.1:51515/rtp",
        "protocol": RATS_PROTOCOL,
        "descriptorPath": r"G:\Reverie\bin\ReverieLocal\RATS\Services\rats-4545-abc.json",
        "catalogRevision": 3,
        "nativeToolCount": 12,
        "probeLatencyMs": 4,
        "enabled": True,
        "connection": "connected",
        "sessionActive": True,
        "permissions": ["read", "run"],
        "tools": [
            {
                "key": "scene.open",
                "name": "scene_open",
                "category": "scene",
                "summary": "Open a scene by resource path.",
                "permission": "read",
                "flags": [],
                "schema": "sha256:abc",
            }
        ],
        "loadedToolNames": [],
        "error": "",
    }
    service.update(overrides)
    return service


def _handler(runtime: Optional[_FakeRuntime], *, via_ensure: bool = True) -> Tuple[CommandHandler, Console]:
    console = Console(record=True, width=140, force_terminal=False, no_color=True)
    context: Dict[str, Any] = {}
    if via_ensure:
        context["ensure_rats_runtime"] = lambda: runtime
    else:
        context["rats_runtime"] = runtime
    return CommandHandler(console, context), console


def _output(console: Console) -> str:
    return console.export_text()


# ---------------------------------------------------------------------------
# registry integrity
# ---------------------------------------------------------------------------


def test_every_registered_command_resolves_to_a_real_method() -> None:
    """A registry entry naming a method that was never written is a startup crash.

    ``CommandHandler.__init__`` builds the registry by taking bound methods, so a
    missing one raises ``AttributeError`` before this assertion is reached. The
    assertion is here to say what went wrong when it does.
    """
    handler, _console = _handler(None)

    for name, callback in handler.commands.items():
        assert callable(callback), f"/{name} is registered but not callable"


def test_rats_is_registered() -> None:
    handler, _console = _handler(None)

    assert handler.commands["rats"] == handler.cmd_rats


# ---------------------------------------------------------------------------
# runtime acquisition
# ---------------------------------------------------------------------------


def test_a_missing_runtime_is_reported_not_raised() -> None:
    handler, console = _handler(None)

    assert handler.cmd_rats("status") is True
    assert "not available" in _output(console)


def test_the_runtime_comes_from_ensure_when_it_is_offered() -> None:
    """Lazy construction is the point: the accessor is preferred over the field."""
    runtime = _FakeRuntime(_test_root("ensure"))
    built: List[int] = []

    def ensure() -> _FakeRuntime:
        built.append(1)
        return runtime

    console = Console(record=True, width=140, force_terminal=False, no_color=True)
    handler = CommandHandler(console, {"ensure_rats_runtime": ensure, "rats_runtime": None})

    assert handler.cmd_rats("status") is True
    assert built == [1]


def test_a_plain_runtime_field_still_works() -> None:
    """Older contexts expose the field only; the command must not require the accessor."""
    runtime = _FakeRuntime(_test_root("field"))
    handler, console = _handler(runtime, via_ensure=False)

    assert handler.cmd_rats("status") is True
    assert "refresh" in runtime.names() or "state" in runtime.names()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_bare_rats_rescans_and_renders_a_discovered_service() -> None:
    runtime = _FakeRuntime(_test_root("status"), services=[_service()])
    handler, console = _handler(runtime)

    assert handler.cmd_rats("") is True

    assert runtime.names() == ["refresh"]
    text = _output(console)
    assert "rats-4545-abc" in text
    assert "reverie.engine" in text
    assert "connected" in text


def test_status_without_an_argument_reuses_the_last_scan() -> None:
    """``/rats status`` after ``/rats refresh`` must not walk the disk again."""
    runtime = _FakeRuntime(_test_root("cached"), services=[_service()])
    handler, _console = _handler(runtime)

    handler.cmd_rats("refresh")
    handler.cmd_rats("status")

    assert runtime.names() == ["refresh", "state"]


def test_an_empty_discovery_result_explains_the_next_step() -> None:
    runtime = _FakeRuntime(_test_root("empty"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("status") is True

    text = _output(console)
    assert "No RATS services" in text
    assert "register" in text


def test_refresh_reports_the_scan_cost_and_the_rejection_count() -> None:
    runtime = _FakeRuntime(_test_root("refresh"), services=[_service()])
    handler, console = _handler(runtime)

    assert handler.cmd_rats("refresh") is True

    text = _output(console)
    assert "7 ms" in text
    assert "1 descriptor" in text


@pytest.mark.parametrize("alias", ["refresh", "detect", "scan", "reload"])
def test_every_rescan_alias_rescans(alias: str) -> None:
    runtime = _FakeRuntime(_test_root(f"alias-{alias}"))
    handler, _console = _handler(runtime)

    handler.cmd_rats(alias)

    assert runtime.names()[0] == "refresh"


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------


def test_providers_separates_built_in_from_custom() -> None:
    runtime = _FakeRuntime(_test_root("providers"))
    runtime.define_custom_provider({"providerId": "acme.toolhost", "product": "Acme Tool Host"})
    runtime.calls.clear()
    handler, console = _handler(runtime)

    assert handler.cmd_rats("providers") is True

    text = _output(console)
    assert "built-in" in text
    assert "custom" in text
    assert "acme.toolhost" in text
    assert "reverie.engine" in text


def test_providers_states_the_limit_and_the_schema() -> None:
    runtime = _FakeRuntime(_test_root("limit"))
    handler, console = _handler(runtime)

    handler.cmd_rats("providers")

    text = _output(console)
    assert "16" in text
    assert RATS_CUSTOM_PROVIDER_SCHEMA in text


# ---------------------------------------------------------------------------
# argument parsing: the provider id is optional by shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "provider_id", "executable", "permissions"),
    [
        (r"C:\bin\reverie.exe", "", r"C:\bin\reverie.exe", []),
        (r"acme.toolhost C:\bin\host.exe", "acme.toolhost", r"C:\bin\host.exe", []),
        (r"C:\bin\reverie.exe read run", "", r"C:\bin\reverie.exe", ["read", "run"]),
        (r"acme.toolhost C:\bin\host.exe READ", "acme.toolhost", r"C:\bin\host.exe", ["read"]),
        # A path is never mistaken for a provider id, even when it has dots.
        (r"C:\bin\my.tool.exe read", "", r"C:\bin\my.tool.exe", ["read"]),
        ("/opt/reverie/reverie read", "", "/opt/reverie/reverie", ["read"]),
    ],
)
def test_the_provider_id_is_recognised_by_shape(
    spec: str, provider_id: str, executable: str, permissions: List[str]
) -> None:
    handler, _console = _handler(None)

    assert handler._parse_rats_target(spec) == (provider_id, executable, permissions)


def test_an_empty_target_parses_to_nothing() -> None:
    handler, _console = _handler(None)

    assert handler._parse_rats_target("") == ("", "", [])


# ---------------------------------------------------------------------------
# register / enable / disable / remove-root
# ---------------------------------------------------------------------------


def test_register_defaults_to_the_engine_provider() -> None:
    runtime = _FakeRuntime(_test_root("register"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats(r'register "C:\bin\reverie.exe"') is True

    args, _kwargs = runtime.args_for("register_provider_executable")
    assert args == ("reverie.engine", r"C:\bin\reverie.exe")
    assert "Registered" in _output(console)


def test_register_honours_an_explicit_provider_id() -> None:
    runtime = _FakeRuntime(_test_root("register-custom"))
    handler, _console = _handler(runtime)

    handler.cmd_rats(r"add acme.toolhost C:\bin\host.exe")

    args, _kwargs = runtime.args_for("register_provider_executable")
    assert args == ("acme.toolhost", r"C:\bin\host.exe")


def test_register_without_an_executable_asks_for_one() -> None:
    runtime = _FakeRuntime(_test_root("register-bare"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("register") is True

    assert "register_provider_executable" not in runtime.names()
    assert "Usage: /rats register" in _output(console)


def test_a_refused_registration_is_reported_with_the_runtime_reason() -> None:
    runtime = _FakeRuntime(_test_root("register-refused"))
    runtime.raise_on["register_provider_executable"] = ValueError("Select an existing Reverie Engine executable.")
    handler, console = _handler(runtime)

    assert handler.cmd_rats(r"register C:\nope.exe") is True

    assert "Select an existing Reverie Engine executable." in _output(console)


def test_enable_passes_the_requested_permission_classes_through() -> None:
    runtime = _FakeRuntime(_test_root("enable"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats(r"enable C:\bin\reverie.exe read run write") is True

    args, _kwargs = runtime.args_for("set_provider_enabled")
    assert args == ("reverie.engine", r"C:\bin\reverie.exe", True, ["read", "run", "write"])
    assert "Enabled" in _output(console)


def test_enable_without_classes_leaves_the_choice_to_the_runtime() -> None:
    runtime = _FakeRuntime(_test_root("enable-default"))
    handler, _console = _handler(runtime)

    handler.cmd_rats(r"enable C:\bin\reverie.exe")

    args, _kwargs = runtime.args_for("set_provider_enabled")
    assert args[3] == []


def test_disable_sends_false() -> None:
    runtime = _FakeRuntime(_test_root("disable"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats(r"disable C:\bin\reverie.exe") is True

    args, _kwargs = runtime.args_for("set_provider_enabled")
    assert args[2] is False
    assert "Disabled" in _output(console)


def test_remove_root_forwards_the_path() -> None:
    runtime = _FakeRuntime(_test_root("remove-root"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats(r'remove-root "C:\bin\ReverieLocal\RATS\Services"') is True

    args, _kwargs = runtime.args_for("remove_discovery_root")
    assert args == (r"C:\bin\ReverieLocal\RATS\Services",)
    assert "Removed the discovery root" in _output(console)


def test_remove_root_without_a_path_asks_for_one() -> None:
    runtime = _FakeRuntime(_test_root("remove-root-bare"))
    handler, console = _handler(runtime)

    handler.cmd_rats("remove-root")

    assert "remove_discovery_root" not in runtime.names()
    assert "Usage: /rats remove-root" in _output(console)


# ---------------------------------------------------------------------------
# define / undefine
# ---------------------------------------------------------------------------


def test_define_forwards_the_parsed_definition() -> None:
    runtime = _FakeRuntime(_test_root("define"))
    handler, console = _handler(runtime)
    payload = json.dumps(
        {
            "providerId": "acme.toolhost",
            "product": "Acme Tool Host",
            "serviceKinds": ["builtin"],
            "permissionClasses": ["read", "run"],
        }
    )

    assert handler.cmd_rats(f"define {payload}") is True

    args, _kwargs = runtime.args_for("define_custom_provider")
    assert args[0]["providerId"] == "acme.toolhost"
    assert "Defined the custom RATS provider" in _output(console)


def test_define_reads_a_definition_from_a_file() -> None:
    root = _test_root("define-file")
    path = root / "acme.json"
    path.write_text(
        json.dumps({"providerId": "acme.toolhost", "product": "Acme Tool Host"}),
        encoding="utf-8",
    )
    runtime = _FakeRuntime(root)
    handler, _console = _handler(runtime)

    assert handler.cmd_rats(f'define @"{path}"') is True

    args, _kwargs = runtime.args_for("define_custom_provider")
    assert args[0]["product"] == "Acme Tool Host"


def test_define_with_broken_json_never_reaches_the_runtime() -> None:
    runtime = _FakeRuntime(_test_root("define-broken"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats('define {"providerId": ') is True

    assert "define_custom_provider" not in runtime.names()
    assert "not valid JSON" in _output(console)


def test_define_without_a_payload_shows_an_example() -> None:
    runtime = _FakeRuntime(_test_root("define-bare"))
    handler, console = _handler(runtime)

    handler.cmd_rats("define")

    assert "define_custom_provider" not in runtime.names()
    assert "providerId" in _output(console)


def test_a_refused_definition_surfaces_the_runtime_sentence() -> None:
    runtime = _FakeRuntime(_test_root("define-refused"))
    runtime.raise_on["define_custom_provider"] = ValueError(
        "That provider id is reserved for a built-in provider."
    )
    handler, console = _handler(runtime)

    assert handler.cmd_rats('define {"providerId": "reverie.engine", "product": "Fake"}') is True

    assert "reserved for a built-in provider" in _output(console)


def test_undefine_forwards_a_lowercased_provider_id() -> None:
    runtime = _FakeRuntime(_test_root("undefine"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("undefine ACME.ToolHost") is True

    args, _kwargs = runtime.args_for("remove_custom_provider")
    assert args == ("acme.toolhost",)
    assert "Removed the custom provider" in _output(console)


def test_undefine_without_an_id_asks_for_one() -> None:
    runtime = _FakeRuntime(_test_root("undefine-bare"))
    handler, console = _handler(runtime)

    handler.cmd_rats("undefine")

    assert "remove_custom_provider" not in runtime.names()
    assert "Usage: /rats undefine" in _output(console)


# ---------------------------------------------------------------------------
# tools / describe
# ---------------------------------------------------------------------------


def test_tools_lists_summaries_and_points_at_describe() -> None:
    runtime = _FakeRuntime(_test_root("tools"), services=[_service()])
    handler, console = _handler(runtime)

    assert handler.cmd_rats("tools") is True

    text = _output(console)
    assert "scene_open" in text
    assert "Open a scene by resource path." in text
    assert "describe" in text


def test_tools_marks_which_definitions_are_already_loaded() -> None:
    runtime = _FakeRuntime(
        _test_root("tools-loaded"), services=[_service(loadedToolNames=["scene_open"])]
    )
    handler, console = _handler(runtime)

    handler.cmd_rats("tools")

    assert "full" in _output(console)


def test_tools_can_be_narrowed_to_one_service() -> None:
    runtime = _FakeRuntime(
        _test_root("tools-filter"),
        services=[_service(), _service(serviceId="rats-9999-zzz", tools=[])],
    )
    handler, console = _handler(runtime)

    handler.cmd_rats("tools rats-9999-zzz")

    text = _output(console)
    assert "rats-9999-zzz" in text
    assert "scene_open" not in text


def test_tools_for_an_unknown_service_says_so() -> None:
    runtime = _FakeRuntime(_test_root("tools-unknown"), services=[_service()])
    handler, console = _handler(runtime)

    handler.cmd_rats("tools rats-does-not-exist")

    assert "No RATS service matches" in _output(console)


def test_describe_requests_the_named_tools_and_prints_the_schema() -> None:
    runtime = _FakeRuntime(_test_root("describe"), services=[_service()])
    runtime.describe_result = [
        {
            "name": "scene_open",
            "description": "Open a scene by resource path.",
            "permission": "read",
            "request_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    ]
    handler, console = _handler(runtime)

    assert handler.cmd_rats("describe rats-4545-abc scene_open") is True

    args, kwargs = runtime.args_for("describe")
    assert args == ("rats-4545-abc", ["scene_open"])
    assert kwargs == {"provider_id": ""}
    text = _output(console)
    assert "scene_open" in text
    assert "request_schema" in text or "properties" in text


def test_describe_needs_a_service_and_a_tool() -> None:
    runtime = _FakeRuntime(_test_root("describe-bare"))
    handler, console = _handler(runtime)

    handler.cmd_rats("describe rats-4545-abc")

    assert "describe" not in runtime.names()
    assert "Usage: /rats describe" in _output(console)


def test_describe_on_a_disabled_service_reports_the_runtime_reason() -> None:
    runtime = _FakeRuntime(_test_root("describe-disabled"))
    runtime.raise_on["describe"] = ValueError("Enable the RATS service before requesting tool definitions.")
    handler, console = _handler(runtime)

    assert handler.cmd_rats("describe rats-4545-abc scene_open") is True

    assert "Enable the RATS service" in _output(console)


def test_describe_with_no_matching_definitions_says_what_was_asked_for() -> None:
    runtime = _FakeRuntime(_test_root("describe-empty"))
    handler, console = _handler(runtime)

    handler.cmd_rats("describe rats-4545-abc ghost_tool")

    assert "ghost_tool" in _output(console)


# ---------------------------------------------------------------------------
# confirm — the "检测、确认" half of the work order
# ---------------------------------------------------------------------------


def test_confirm_rescans_and_passes_every_check_for_a_healthy_service() -> None:
    runtime = _FakeRuntime(_test_root("confirm"), services=[_service()])
    handler, console = _handler(runtime)

    assert handler.cmd_rats("confirm rats-4545-abc") is True

    assert runtime.names() == ["refresh"]
    text = _output(console)
    assert "6/6 checks passed" in text
    assert "descriptor verified" in text
    assert "catalog readable" in text


def test_confirm_names_the_check_that_failed() -> None:
    runtime = _FakeRuntime(
        _test_root("confirm-fail"),
        services=[
            _service(
                enabled=False,
                sessionActive=False,
                connection="available",
                tools=[],
                error="This RATS service is not enabled.",
            )
        ],
    )
    handler, console = _handler(runtime)

    handler.cmd_rats("confirm")

    text = _output(console)
    assert "3/6 checks passed" in text
    assert "This RATS service is not enabled." in text


def test_confirm_flags_a_protocol_mismatch() -> None:
    runtime = _FakeRuntime(
        _test_root("confirm-protocol"), services=[_service(protocol="reverie.rtp/99")]
    )
    handler, console = _handler(runtime)

    handler.cmd_rats("confirm rats-4545-abc")

    text = _output(console)
    assert "reverie.rtp/99" in text
    assert "5/6 checks passed" in text


def test_confirm_without_any_service_says_to_look_at_status() -> None:
    runtime = _FakeRuntime(_test_root("confirm-empty"))
    handler, console = _handler(runtime)

    handler.cmd_rats("confirm")

    assert "No RATS services" in _output(console)


# ---------------------------------------------------------------------------
# diagnostics / path / usage
# ---------------------------------------------------------------------------


def test_diagnostics_renders_the_recorded_rejection() -> None:
    runtime = _FakeRuntime(_test_root("diagnostics"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("diagnostics") is True

    text = _output(console)
    assert "settings.custom_provider_rejected" in text
    assert "reserved_provider_id" in text
    # The timestamp column reads the key the runtime writes, so a rename in
    # ``rats.py`` shows up here rather than as a silently blank column.
    assert _REAL_DIAGNOSTIC_ENTRY["timestampUtc"] in text
    assert "providerId=reverie.engine" in text


def test_diagnostics_accepts_a_limit_and_ignores_a_bad_one() -> None:
    runtime = _FakeRuntime(_test_root("diagnostics-limit"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("diagnostics 5") is True
    assert handler.cmd_rats("diagnostics banana") is True

    assert "settings.custom_provider_rejected" in _output(console)


def test_path_reports_both_state_files() -> None:
    runtime = _FakeRuntime(_test_root("path"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("path") is True

    text = _output(console)
    assert "settings.json" in text
    assert "diagnostics.jsonl" in text


def test_an_unknown_subcommand_shows_the_usage_line() -> None:
    runtime = _FakeRuntime(_test_root("usage"))
    handler, console = _handler(runtime)

    assert handler.cmd_rats("frobnicate") is True

    text = _output(console)
    assert "Usage: /rats" in text
    assert "confirm" in text
    assert runtime.names() == []
