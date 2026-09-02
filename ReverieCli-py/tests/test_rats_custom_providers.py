"""User-declared RATS providers: validation, storage, discovery, and removal.

The built-in allowlist is compiled in and stays that way — it is how this client
claims a descriptor came from a build it recognises. This suite covers the second
layer: definitions read from the RATS settings file, which let someone run their
own RTP service without waiting for a client release.

Two properties matter more than the rest, and each has a test that fails loudly
if it regresses:

* a definition can name a discovery root only *relative to its own executable's
  directory*, because that root is the boundary ``_parse_rats_descriptor`` uses to
  decide a descriptor is trustworthy at all; and
* a definition can never displace a built-in provider, because the meaning of
  ``reverie.engine`` is the one fact this client has to hold on its own.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

import reverie.rats as rats_module
from reverie.rats import (
    RATS_CUSTOM_PROVIDER_SCHEMA,
    RATS_PROTOCOL,
    RATS_SETTINGS_VERSION,
    RATS_SUPPORTED_PROVIDERS,
    RatsProviderRegistry,
    RatsProviderSpec,
    RatsRuntime,
    discover_rats_descriptors,
    normalize_rats_custom_provider,
    rats_custom_provider_spec,
)


CONTROL_TOKEN = "c" * 64


def _allow_test_process(_pid: int, _executable: Path) -> bool:
    return True


def _test_provider_registry() -> RatsProviderRegistry:
    """The same additive fixture shape the other RATS suites use."""
    return RatsProviderRegistry(
        {
            "reverie.engine": RatsProviderSpec(
                provider_id="reverie.engine",
                product="Reverie Engine",
                service_kinds=("builtin",),
                executable_validator=lambda executable: executable.is_file(),
                process_validator=_allow_test_process,
                discovery_root_resolver=lambda executable: executable.parent
                / "ReverieLocal"
                / "RATS"
                / "Services",
                permission_classes=RATS_SUPPORTED_PROVIDERS["reverie.engine"].permission_classes,
                label="Reverie Engine Test Fixture",
                tool_tags=("reverie-engine", "test-fixture"),
            ),
        }
    )


TEST_PROVIDER_REGISTRY = _test_provider_registry()


def _test_root(name: str) -> Path:
    root = (
        Path(__file__).resolve().parents[2]
        / "dist"
        / ".reverie"
        / "test-temp"
        / f"rats-custom-{name}-{uuid.uuid4().hex}"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _definition(**overrides) -> dict:
    definition = {
        "providerId": "acme.toolhost",
        "product": "Acme Tool Host",
        "label": "Acme Tool Host",
        "serviceKinds": ["builtin"],
        "permissionClasses": ["read", "run"],
        "toolTags": ["acme"],
    }
    definition.update(overrides)
    return definition


def _write_settings(cli_root: Path, **keys) -> Path:
    path = cli_root / ".reverie" / "rats" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": RATS_SETTINGS_VERSION, "discoveryRoots": [], "enabledProviders": []}
    payload.update(keys)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_a_definition_normalizes_to_data_only_with_defaults_filled() -> None:
    record, reason = normalize_rats_custom_provider(_definition(), ["reverie.engine"])

    assert reason == ""
    assert record == {
        "schema": RATS_CUSTOM_PROVIDER_SCHEMA,
        "providerId": "acme.toolhost",
        "product": "Acme Tool Host",
        "label": "Acme Tool Host",
        "serviceKinds": ["builtin"],
        "permissionClasses": ["read", "run"],
        "toolTags": ["acme"],
        "discoveryRoot": ["ReverieLocal", "RATS", "Services"],
        "executableIdentity": "path",
        "executableProductNames": [],
        "executableError": "Select an existing executable for Acme Tool Host.",
    }
    # Every value is JSON, so nothing a settings file holds can be executed.
    json.dumps(record)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"providerId": "toolhost"}, "invalid_provider_id"),
        ({"providerId": "a.b"}, "invalid_provider_id"),
        ({"providerId": "ACME.HOST!"}, "invalid_provider_id"),
        ({"providerId": "one.two.three.four.five"}, "invalid_provider_id"),
        ({"product": ""}, "invalid_product"),
        ({"product": "x" * 129}, "invalid_product"),
        ({"serviceKinds": []}, "invalid_service_kinds"),
        ({"serviceKinds": ["Not A Kind"]}, "invalid_service_kinds"),
        ({"permissionClasses": []}, "invalid_permission_classes"),
        ({"toolTags": ["not a tag"]}, "invalid_tool_tags"),
        ({"toolTags": [f"t{index}" for index in range(9)]}, "invalid_tool_tags"),
        ({"executableIdentity": "signature"}, "invalid_executable_identity"),
        ({"executableIdentity": "product_name"}, "missing_executable_product_names"),
        ({"executableProductNames": "Acme"}, None),
    ],
)
def test_a_malformed_definition_is_refused_with_a_named_reason(overrides, reason) -> None:
    record, refusal = normalize_rats_custom_provider(_definition(**overrides), ["reverie.engine"])

    if reason is None:
        # A bare string is accepted as a one-item list; only a non-sequence is not.
        assert refusal == ""
        assert record["executableProductNames"] == ["Acme"]
        return
    assert refusal == reason
    assert record == {}
    # Every refusal a person can trigger has a sentence explaining it.
    assert refusal in rats_module._CUSTOM_PROVIDER_ERRORS


@pytest.mark.parametrize(
    "root",
    [
        "C:/anywhere",
        "/etc/rats",
        "\\\\server\\share",
        "~/rats",
        "../sibling",
        ["..", "sibling"],
        ["."],
        ["a:b"],
        ["seg/ment"],
        ["x"] * 9,
        [],
        123,
    ],
)
def test_a_discovery_root_that_is_not_relative_to_the_executable_is_refused(root) -> None:
    """The root is the descriptor trust boundary, so a definition cannot move it.

    ``_parse_rats_descriptor`` refuses a descriptor that does not sit in the root
    its own declared executable resolves to. If a definition could name an
    absolute root, it would hand that trust to an arbitrary directory — so
    anything that is not a short list of plain relative segments is refused.
    """
    _record, reason = normalize_rats_custom_provider(
        _definition(discoveryRoot=root), ["reverie.engine"]
    )

    assert reason == "invalid_discovery_root"


def test_a_relative_discovery_root_resolves_under_the_executables_own_directory() -> None:
    record, reason = normalize_rats_custom_provider(
        _definition(discoveryRoot="Local/RTP/Services"), ["reverie.engine"]
    )
    assert reason == ""
    assert record["discoveryRoot"] == ["Local", "RTP", "Services"]

    spec = rats_custom_provider_spec(record)
    resolved = spec.discovery_root_for_executable(Path("G:/vendor/bin/host.exe"))

    assert resolved == Path("G:/vendor/bin/Local/RTP/Services").resolve(strict=False)


def test_a_definition_cannot_claim_a_built_in_provider_id() -> None:
    _record, reason = normalize_rats_custom_provider(
        _definition(providerId="reverie.engine", product="Not The Engine"),
        RATS_SUPPORTED_PROVIDERS,
    )

    assert reason == "reserved_provider_id"


def test_the_default_discovery_root_matches_the_built_in_layout() -> None:
    record, _reason = normalize_rats_custom_provider(_definition(), [])
    spec = rats_custom_provider_spec(record)

    assert spec.discovery_root_for_executable(Path("G:/vendor/host.exe")) == (
        RATS_SUPPORTED_PROVIDERS["reverie.engine"].discovery_root_for_executable(
            Path("G:/vendor/host.exe")
        )
    )


def test_product_name_identity_checks_the_declared_names(tmp_path: Path) -> None:
    record, reason = normalize_rats_custom_provider(
        _definition(executableIdentity="product-name", executableProductNames=["Acme Tool Host"]),
        [],
    )
    assert reason == ""
    assert record["executableIdentity"] == "product_name"

    spec = rats_custom_provider_spec(record)
    executable = tmp_path / "host.exe"
    executable.write_bytes(b"not a real pe file")

    if os.name == "nt":
        # No VERSIONINFO resource to read, so identity cannot be proven.
        assert spec.validate_executable(executable) is False
    else:
        # Nothing equivalent to read off Windows: degrade to the existence check
        # rather than refuse every executable on the platform.
        assert spec.validate_executable(executable) is True
    assert spec.validate_executable(tmp_path / "missing.exe") is False


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


def test_defining_a_provider_persists_it_and_puts_it_in_the_effective_registry() -> None:
    root = _test_root("define")
    try:
        cli_root = root / "cli"
        settings_path = _write_settings(cli_root)
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)

        state = runtime.define_custom_provider(_definition())

        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["schemaVersion"] == RATS_SETTINGS_VERSION
        assert [item["providerId"] for item in persisted["customProviders"]] == ["acme.toolhost"]
        assert "acme.toolhost" in runtime.registry
        # The base registry is untouched, so an injected fixture stays additive.
        assert "acme.toolhost" not in runtime.provider_registry

        ids = [item["providerId"] for item in state["supportedProviders"]]
        assert ids == ["acme.toolhost", "reverie.engine"]
        by_id = {item["providerId"]: item for item in state["supportedProviders"]}
        assert by_id["acme.toolhost"]["custom"] is True
        assert by_id["reverie.engine"]["custom"] is False
        assert by_id["acme.toolhost"]["permissions"] == ["read", "run"]
        assert by_id["acme.toolhost"]["toolTags"] == ["acme"]
        assert state["customProviderSchema"] == RATS_CUSTOM_PROVIDER_SCHEMA
        assert [item["providerId"] for item in state["customProviders"]] == ["acme.toolhost"]
        assert runtime.list_custom_providers() == persisted["customProviders"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_definition_survives_a_restart_and_is_not_rewritten_on_reread() -> None:
    root = _test_root("restart")
    try:
        cli_root = root / "cli"
        settings_path = _write_settings(cli_root)
        first = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        first.define_custom_provider(_definition())
        after_define = settings_path.read_text(encoding="utf-8")
        first.shutdown()

        second = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        second.refresh()

        assert settings_path.read_text(encoding="utf-8") == after_define
        assert "acme.toolhost" in second.registry
        assert second.registry["acme.toolhost"].product == "Acme Tool Host"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_defining_the_same_id_twice_replaces_rather_than_duplicates() -> None:
    root = _test_root("replace")
    try:
        cli_root = root / "cli"
        settings_path = _write_settings(cli_root)
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.define_custom_provider(_definition())

        runtime.define_custom_provider(_definition(product="Acme Tool Host 2", label="Acme 2"))

        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert len(persisted["customProviders"]) == 1
        assert persisted["customProviders"][0]["product"] == "Acme Tool Host 2"
        assert runtime.registry["acme.toolhost"].label == "Acme 2"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_defining_a_malformed_provider_raises_and_changes_nothing() -> None:
    root = _test_root("define-invalid")
    try:
        cli_root = root / "cli"
        settings_path = _write_settings(cli_root)
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.refresh()
        before = settings_path.read_text(encoding="utf-8")

        with pytest.raises(ValueError) as error:
            runtime.define_custom_provider(_definition(discoveryRoot="C:/somewhere/else"))

        assert "relative to the executable" in str(error.value)
        assert settings_path.read_text(encoding="utf-8") == before
        assert list(runtime.registry) == ["reverie.engine"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_definition_cannot_displace_a_built_in_through_storage() -> None:
    """Even a hand-edited settings file cannot redefine a compiled-in provider."""
    root = _test_root("shadow")
    try:
        cli_root = root / "cli"
        _write_settings(
            cli_root,
            customProviders=[
                {
                    "schema": RATS_CUSTOM_PROVIDER_SCHEMA,
                    "providerId": "reverie.engine",
                    "product": "Impostor",
                    "label": "Impostor",
                    "serviceKinds": ["builtin"],
                    "permissionClasses": ["read"],
                    "toolTags": [],
                    "discoveryRoot": ["Services"],
                    "executableIdentity": "path",
                    "executableProductNames": [],
                    "executableError": "no",
                }
            ],
        )
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        state = runtime.refresh()

        assert runtime.registry["reverie.engine"].product == "Reverie Engine"
        assert state["customProviders"] == []
        assert any(
            item.get("event") == "settings.custom_provider_rejected"
            and item.get("reason") == "reserved_provider_id"
            for item in state["diagnostics"]
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_one_unusable_definition_does_not_cost_the_others() -> None:
    root = _test_root("partial")
    try:
        cli_root = root / "cli"
        good, _reason = normalize_rats_custom_provider(_definition(providerId="acme.good"), [])
        _write_settings(
            cli_root,
            customProviders=[
                {"providerId": "nope", "product": "Broken"},
                good,
                dict(good, label="Second Claim"),
            ],
        )
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        state = runtime.refresh()

        assert [item["providerId"] for item in state["customProviders"]] == ["acme.good"]
        # First definition wins; the later claim on the same id is refused rather
        # than overwriting it.
        assert state["customProviders"][0]["label"] == good["label"]
        reasons = {
            item.get("reason")
            for item in state["diagnostics"]
            if item.get("event") == "settings.custom_provider_rejected"
        }
        assert reasons == {"invalid_provider_id", "duplicate_provider_id"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_more_definitions_than_the_limit_are_refused_not_silently_truncated() -> None:
    root = _test_root("limit")
    try:
        cli_root = root / "cli"
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        for index in range(rats_module._MAX_CUSTOM_PROVIDERS):
            runtime.define_custom_provider(_definition(providerId=f"acme.host{index:02d}"))

        with pytest.raises(ValueError) as error:
            runtime.define_custom_provider(_definition(providerId="acme.overflow"))

        assert str(rats_module._MAX_CUSTOM_PROVIDERS) in str(error.value)
        assert len(runtime.list_custom_providers()) == rats_module._MAX_CUSTOM_PROVIDERS
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_schema_three_file_migrates_without_inventing_a_provider() -> None:
    root = _test_root("migrate")
    try:
        cli_root = root / "cli"
        settings_path = cli_root / ".reverie" / "rats" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 3,
                    "discoveryRoots": [],
                    "enabledProviders": [],
                    "providerPermissionClasses": {},
                }
            ),
            encoding="utf-8",
        )
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.refresh()

        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["schemaVersion"] == RATS_SETTINGS_VERSION
        assert persisted["customProviders"] == []
        assert list(runtime.registry) == ["reverie.engine"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_a_custom_provider_descriptor_is_accepted_only_inside_its_own_root() -> None:
    """The end-to-end point of the whole layer, and its boundary.

    A descriptor from a user-declared provider parses, and the same descriptor
    moved outside the root its executable resolves to does not.
    """
    root = _test_root("discovery")
    try:
        executable = root / "vendor" / "host.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        record, reason = normalize_rats_custom_provider(
            _definition(discoveryRoot="Local/RTP"), []
        )
        assert reason == ""
        built = rats_custom_provider_spec(record)
        # A definition cannot weaken the "this pid is running this image" check:
        # the compiled spec always gets the real one. The fixture below swaps it
        # out only because the descriptor names this test process, whose image is
        # the interpreter rather than the executable under test.
        assert built.process_validator is rats_module._reverie_engine_process
        spec = dataclasses.replace(built, process_validator=_allow_test_process)
        registry = RatsProviderRegistry({**dict(TEST_PROVIDER_REGISTRY.items()), "acme.toolhost": spec})

        services = spec.discovery_root_for_executable(executable)
        services.mkdir(parents=True, exist_ok=True)
        descriptor_value = {
            "schema": "reverie.rats.discovery/1",
            "protocol": RATS_PROTOCOL,
            "service_id": "rats-4545-acme",
            "provider_id": "acme.toolhost",
            "service_kind": "builtin",
            "product": "Acme Tool Host",
            "product_version": "test",
            "executable": str(executable.resolve()),
            "pid": os.getpid(),
            "port": 4545,
            "endpoint": "http://127.0.0.1:4545/rtp",
            "bind_address": "127.0.0.1",
            "catalog_revision": "catalog-test",
            "native_tool_count": 3,
            "started_utc": "2026-08-30T00:00:00Z",
            "control_token": CONTROL_TOKEN,
        }
        inside = services / "rats-4545-acme.json"
        inside.write_text(json.dumps(descriptor_value), encoding="utf-8")

        rejections: list[dict] = []
        discovered = discover_rats_descriptors([services], rejections, registry)

        assert rejections == []
        assert [item.provider_id for item in discovered] == ["acme.toolhost"]
        assert discovered[0].product == "Acme Tool Host"
        assert discovered[0].service_id == "rats-4545-acme"

        outside = root / "elsewhere" / "rats-4545-acme.json"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text(json.dumps(descriptor_value), encoding="utf-8")

        moved: list[dict] = []
        assert discover_rats_descriptors([outside.parent], moved, registry) == []
        assert [item["reason"] for item in moved] == ["descriptor_outside_provider_root"]
        # And the same fact stated at the gate itself, so a refactor that stops
        # reporting the reason still fails here.
        _descriptor, reason = rats_module._parse_rats_descriptor(
            descriptor_value, outside, registry
        )
        assert reason == "descriptor_outside_provider_root"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_descriptor_whose_product_disagrees_with_its_definition_is_refused() -> None:
    root = _test_root("mismatch")
    try:
        executable = root / "vendor" / "host.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        record, _reason = normalize_rats_custom_provider(_definition(), [])
        spec = dataclasses.replace(
            rats_custom_provider_spec(record), process_validator=_allow_test_process
        )
        registry = RatsProviderRegistry({"acme.toolhost": spec})
        services = spec.discovery_root_for_executable(executable)
        services.mkdir(parents=True, exist_ok=True)
        path = services / "rats-4545-acme.json"
        base = {
            "schema": "reverie.rats.discovery/1",
            "protocol": RATS_PROTOCOL,
            "service_id": "rats-4545-acme",
            "provider_id": "acme.toolhost",
            "service_kind": "builtin",
            "product": "Acme Tool Host",
            "executable": str(executable.resolve()),
            "pid": os.getpid(),
            "port": 4545,
            "endpoint": "http://127.0.0.1:4545/rtp",
            "bind_address": "127.0.0.1",
            "control_token": CONTROL_TOKEN,
        }

        for overrides, expected in [
            ({"product": "Something Else"}, "provider_product_mismatch"),
            ({"service_kind": "sidecar"}, "unsupported_service_kind"),
            ({"provider_id": "acme.other"}, "unsupported_provider"),
            (
                {"endpoint": "http://10.0.0.5:4545/rtp", "bind_address": "10.0.0.5"},
                "non_loopback_endpoint",
            ),
            ({"control_token": "short"}, "invalid_control_token"),
        ]:
            _descriptor, reason = rats_module._parse_rats_descriptor(
                dict(base, **overrides), path, registry
            )
            assert reason == expected, overrides

        _descriptor, reason = rats_module._parse_rats_descriptor(base, path, registry)
        assert reason == ""
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_enabling_a_custom_provider_stores_its_root_and_permissions() -> None:
    root = _test_root("enable")
    try:
        cli_root = root / "cli"
        executable = root / "vendor" / "host.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.define_custom_provider(_definition())

        state = runtime.set_provider_enabled("acme.toolhost", executable, True, ["read"])

        expected_root = str(
            (executable.parent / "ReverieLocal" / "RATS" / "Services").resolve(strict=False)
        )
        assert state["enabledProviders"] == [
            {
                "providerId": "acme.toolhost",
                "executable": str(executable.resolve()),
                "permissions": ["read"],
                "discoveryRoot": expected_root,
            }
        ]
        assert expected_root in state["configuredDiscoveryRoots"]
        # The deprecated engine-only view must not claim a custom provider.
        assert state["enabledEngines"] == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_registering_an_executable_for_an_undefined_provider_is_refused() -> None:
    root = _test_root("undefined")
    try:
        cli_root = root / "cli"
        executable = root / "vendor" / "host.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)

        with pytest.raises(ValueError) as error:
            runtime.register_provider_executable("acme.toolhost", executable)

        assert "acme.toolhost" in str(error.value)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# removal
# ---------------------------------------------------------------------------


def test_removing_a_provider_takes_its_selections_root_and_classes_with_it() -> None:
    root = _test_root("remove")
    try:
        cli_root = root / "cli"
        settings_path = cli_root / ".reverie" / "rats" / "settings.json"
        executable = root / "vendor" / "host.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"test")
        unrelated = str((root / "kept-by-hand").resolve())
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.define_custom_provider(_definition())
        runtime.set_provider_enabled("acme.toolhost", executable, True, ["read"])
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        settings["discoveryRoots"] = [*settings["discoveryRoots"], unrelated]
        settings["providerPermissionClasses"] = {"acme.toolhost": ["read", "run"]}
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        runtime.refresh()
        custom_root = str(
            (executable.parent / "ReverieLocal" / "RATS" / "Services").resolve(strict=False)
        )
        assert custom_root in json.loads(settings_path.read_text(encoding="utf-8"))["discoveryRoots"]

        state = runtime.remove_custom_provider("acme.toolhost")

        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert persisted["customProviders"] == []
        assert persisted["enabledProviders"] == []
        assert "acme.toolhost" not in persisted["providerPermissionClasses"]
        assert custom_root not in persisted["discoveryRoots"]
        # A root nobody's selection explains was not this call's to drop.
        assert unrelated in persisted["discoveryRoots"]
        assert "acme.toolhost" not in runtime.registry
        assert [item["providerId"] for item in state["supportedProviders"]] == ["reverie.engine"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_removing_a_provider_keeps_a_root_another_selection_still_needs() -> None:
    root = _test_root("shared-root")
    try:
        cli_root = root / "cli"
        settings_path = cli_root / ".reverie" / "rats" / "settings.json"
        shared = root / "vendor"
        shared.mkdir(parents=True, exist_ok=True)
        first = shared / "host.exe"
        second = shared / "other.exe"
        first.write_bytes(b"test")
        second.write_bytes(b"test")
        runtime = RatsRuntime(cli_root, provider_registry=TEST_PROVIDER_REGISTRY)
        runtime.define_custom_provider(_definition())
        runtime.define_custom_provider(_definition(providerId="acme.second"))
        runtime.set_provider_enabled("acme.toolhost", first, True, ["read"])
        runtime.set_provider_enabled("acme.second", second, True, ["read"])
        shared_root = str((shared / "ReverieLocal" / "RATS" / "Services").resolve(strict=False))

        runtime.remove_custom_provider("acme.toolhost")

        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        assert [item["providerId"] for item in persisted["enabledProviders"]] == ["acme.second"]
        assert shared_root in persisted["discoveryRoots"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_built_in_provider_cannot_be_removed() -> None:
    root = _test_root("remove-builtin")
    try:
        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY)

        with pytest.raises(ValueError) as error:
            runtime.remove_custom_provider("reverie.engine")

        assert "built-in" in str(error.value)
        assert "reverie.engine" in runtime.registry
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_removing_an_unknown_provider_says_so() -> None:
    root = _test_root("remove-unknown")
    try:
        runtime = RatsRuntime(root / "cli", provider_registry=TEST_PROVIDER_REGISTRY)

        with pytest.raises(ValueError) as error:
            runtime.remove_custom_provider("acme.nothere")

        assert "acme.nothere" in str(error.value)

        with pytest.raises(ValueError):
            runtime.remove_custom_provider("   ")
    finally:
        shutil.rmtree(root, ignore_errors=True)
