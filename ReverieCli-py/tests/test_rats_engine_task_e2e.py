from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from _engine_pairing import (
    ENGINE_BIN_ENV,
    RETRY_SEMANTICS_FEATURE,
    assert_response_schema,
    assert_retry_contract,
    discover_engine_binary,
    engine_pairing_skip_reason,
)
from reverie.rats import RATS_PROTOCOL, RatsRuntime
from reverie.rats_contract import parse_capabilities
from reverie.agent.tool_executor import ToolExecutor


ENGINE_BIN = os.fspath(discover_engine_binary() or "")
DISCOVERY_SCHEMA = "reverie.rats.discovery/1"
PROVIDER_ID = "reverie.engine"
OWNER_MARKER_NAME = ".reverie-rats-e2e-owner"


@dataclass(frozen=True)
class _OwnedDescriptor:
    descriptor_path: Path
    schema: str
    provider_id: str
    service_id: str
    provider_pid: int
    executable: Path


def _path_key(path: Path) -> str:
    return os.path.normcase(os.fspath(path.resolve(strict=False)))


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        raise ValueError(f"Invalid provider PID: {pid}")
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    wait_failed = 0xFFFFFFFF
    error_access_denied = 5
    error_invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == error_access_denied:
            return True
        if error == error_invalid_parameter:
            return False
        raise ctypes.WinError(error)
    try:
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result == wait_timeout:
            return True
        if wait_result == wait_object_0:
            return False
        if wait_result == wait_failed:
            raise ctypes.WinError(ctypes.get_last_error())
        raise OSError(f"Unexpected WaitForSingleObject result for PID {pid}: {wait_result}")
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_pid_exit(
    pid: int,
    timeout: float,
    *,
    pid_is_running: Callable[[int], bool] = _pid_is_running,
) -> bool:
    deadline = time.monotonic() + timeout
    while pid_is_running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def _validated_test_descriptor_path(descriptor_path: Path, binary: Path, service_id: str) -> Path:
    candidate = descriptor_path.resolve(strict=False)
    expected_parent = (
        binary.resolve(strict=False).parent / "ReverieLocal" / "RATS" / "Services"
    ).resolve(strict=False)
    if _path_key(candidate.parent) != _path_key(expected_parent):
        raise AssertionError(f"Refusing to remove descriptor outside the provider root: {candidate}")
    if candidate.name != f"{service_id}.json":
        raise AssertionError(f"Refusing to remove a descriptor not owned by this test service: {candidate}")
    return candidate


def _load_descriptor_identity(descriptor_path: Path) -> _OwnedDescriptor:
    candidate = descriptor_path.resolve(strict=False)
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AssertionError(f"Refusing cleanup of an unreadable descriptor: {candidate}") from error
    if not isinstance(value, dict):
        raise AssertionError(f"Refusing cleanup of a non-object descriptor: {candidate}")

    schema = value.get("schema")
    provider_id = value.get("provider_id")
    service_id = value.get("service_id")
    provider_pid = value.get("pid")
    executable = value.get("executable")
    if not isinstance(schema, str):
        raise AssertionError(f"Descriptor schema is not a string: {candidate}")
    if not isinstance(provider_id, str):
        raise AssertionError(f"Descriptor provider_id is not a string: {candidate}")
    if not isinstance(service_id, str) or not service_id:
        raise AssertionError(f"Descriptor service_id is invalid: {candidate}")
    if not isinstance(provider_pid, int) or isinstance(provider_pid, bool) or provider_pid <= 0:
        raise AssertionError(f"Descriptor pid is invalid: {candidate}")
    if not isinstance(executable, str) or not executable:
        raise AssertionError(f"Descriptor executable is invalid: {candidate}")

    return _OwnedDescriptor(
        descriptor_path=candidate,
        schema=schema,
        provider_id=provider_id,
        service_id=service_id,
        provider_pid=provider_pid,
        executable=Path(executable).resolve(strict=False),
    )


def _validate_owned_descriptor(identity: _OwnedDescriptor, binary: Path, provider_pid: int) -> None:
    _validated_test_descriptor_path(identity.descriptor_path, binary, identity.service_id)
    if identity.schema != DISCOVERY_SCHEMA:
        raise AssertionError(f"Descriptor schema is not owned by this test: {identity.descriptor_path}")
    if identity.provider_id != PROVIDER_ID:
        raise AssertionError(f"Descriptor provider_id is not owned by this test: {identity.descriptor_path}")
    if identity.provider_pid != provider_pid:
        raise AssertionError(f"Descriptor pid is not owned by this test: {identity.descriptor_path}")
    if _path_key(identity.executable) != _path_key(binary):
        raise AssertionError(f"Descriptor executable is not owned by this test: {identity.descriptor_path}")


def _find_owned_descriptors(
    descriptor_root: Path,
    descriptors_before_launch: set[str],
    binary: Path,
    provider_pid: int,
) -> list[_OwnedDescriptor]:
    owned = []
    for descriptor_path in descriptor_root.glob("rats-*.json"):
        if not descriptor_path.is_file() or _path_key(descriptor_path) in descriptors_before_launch:
            continue
        try:
            identity = _load_descriptor_identity(descriptor_path)
            _validate_owned_descriptor(identity, binary, provider_pid)
        except (AssertionError, FileNotFoundError, OSError):
            continue
        owned.append(identity)
    return sorted(owned, key=lambda item: _path_key(item.descriptor_path))


def _remove_test_descriptor(
    owned_descriptor: _OwnedDescriptor,
    *,
    binary: Path,
    pid_is_running: Callable[[int], bool] = _pid_is_running,
) -> None:
    _validate_owned_descriptor(owned_descriptor, binary, owned_descriptor.provider_pid)
    candidate = owned_descriptor.descriptor_path
    deadline = time.monotonic() + 5.0
    while True:
        if pid_is_running(owned_descriptor.provider_pid):
            raise AssertionError(
                f"Refusing descriptor cleanup while provider PID {owned_descriptor.provider_pid} is still running"
            )
        try:
            current = _load_descriptor_identity(candidate)
        except FileNotFoundError:
            return
        if current != owned_descriptor:
            raise AssertionError(f"Refusing cleanup because descriptor ownership fields changed: {candidate}")
        _validate_owned_descriptor(current, binary, owned_descriptor.provider_pid)
        if pid_is_running(owned_descriptor.provider_pid):
            raise AssertionError(
                f"Refusing descriptor cleanup while provider PID {owned_descriptor.provider_pid} is still running"
            )
        try:
            candidate.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def _stop_engine_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.wait(timeout=20)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired as error:
            raise AssertionError(f"Engine process tree did not exit after taskkill: PID {process.pid}") from error
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _remove_test_directory(path: Path, owner_marker: str) -> None:
    marker_path = path / OWNER_MARKER_NAME
    try:
        actual_owner = marker_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AssertionError(f"Refusing to remove an unmarked test directory: {path}")
    if actual_owner != owner_marker:
        raise AssertionError(f"Refusing to remove a test directory owned by another run: {path}")
    deadline = time.monotonic() + 15.0
    while path.exists():
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def _write_test_descriptor(
    descriptor_path: Path,
    *,
    binary: Path,
    service_id: str = "rats-test-service",
    provider_pid: int = 4242,
) -> _OwnedDescriptor:
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_path.write_text(
        json.dumps(
            {
                "schema": DISCOVERY_SCHEMA,
                "provider_id": PROVIDER_ID,
                "service_id": service_id,
                "pid": provider_pid,
                "executable": str(binary.resolve()),
            }
        ),
        encoding="utf-8",
    )
    return _load_descriptor_identity(descriptor_path)


def test_remove_test_descriptor_only_unlinks_the_captured_dead_service(tmp_path: Path) -> None:
    binary = tmp_path / "Engine" / "reverie.windows.editor.x86_64.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    descriptor = binary.parent / "ReverieLocal" / "RATS" / "Services" / "rats-test-service.json"
    owned_descriptor = _write_test_descriptor(descriptor, binary=binary)

    _remove_test_descriptor(
        owned_descriptor,
        binary=binary,
        pid_is_running=lambda _pid: False,
    )

    assert not descriptor.exists()


def test_remove_test_descriptor_rejects_other_roots_and_live_providers(tmp_path: Path) -> None:
    binary = tmp_path / "Engine" / "reverie.windows.editor.x86_64.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    outside = tmp_path / "OtherServices" / "rats-test-service.json"
    outside_descriptor = _write_test_descriptor(outside, binary=binary)

    with pytest.raises(AssertionError, match="outside the provider root"):
        _remove_test_descriptor(
            outside_descriptor,
            binary=binary,
            pid_is_running=lambda _pid: False,
        )
    assert outside.exists()

    descriptor = binary.parent / "ReverieLocal" / "RATS" / "Services" / "rats-test-service.json"
    owned_descriptor = _write_test_descriptor(descriptor, binary=binary)
    with pytest.raises(AssertionError, match="still running"):
        _remove_test_descriptor(
            owned_descriptor,
            binary=binary,
            pid_is_running=lambda _pid: True,
        )
    assert descriptor.exists()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema", "reverie.rats.discovery/2"),
        ("provider_id", "other.provider"),
        ("service_id", "rats-replaced-service"),
        ("pid", 5252),
        ("executable", "C:/other/reverie.exe"),
    ],
)
def test_remove_test_descriptor_rejects_replaced_ownership_fields(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    binary = tmp_path / "Engine" / "reverie.windows.editor.x86_64.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    descriptor = binary.parent / "ReverieLocal" / "RATS" / "Services" / "rats-test-service.json"
    owned_descriptor = _write_test_descriptor(descriptor, binary=binary)
    current = json.loads(descriptor.read_text(encoding="utf-8"))
    current[field] = replacement
    descriptor.write_text(json.dumps(current), encoding="utf-8")

    with pytest.raises(AssertionError, match="ownership fields changed"):
        _remove_test_descriptor(
            owned_descriptor,
            binary=binary,
            pid_is_running=lambda _pid: False,
        )

    assert descriptor.exists()


def test_find_owned_descriptors_requires_new_path_exact_pid_and_executable(tmp_path: Path) -> None:
    binary = tmp_path / "Engine" / "reverie.windows.editor.x86_64.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    descriptor_root = binary.parent / "ReverieLocal" / "RATS" / "Services"
    preexisting = descriptor_root / "rats-preexisting.json"
    _write_test_descriptor(preexisting, binary=binary, service_id="rats-preexisting", provider_pid=4242)
    descriptors_before_launch = {_path_key(preexisting)}

    exact = descriptor_root / "rats-exact.json"
    _write_test_descriptor(exact, binary=binary, service_id="rats-exact", provider_pid=4242)
    wrong_pid = descriptor_root / "rats-wrong-pid.json"
    _write_test_descriptor(wrong_pid, binary=binary, service_id="rats-wrong-pid", provider_pid=5252)
    wrong_binary = descriptor_root / "rats-wrong-binary.json"
    _write_test_descriptor(
        wrong_binary,
        binary=tmp_path / "Other" / "reverie.windows.editor.x86_64.exe",
        service_id="rats-wrong-binary",
        provider_pid=4242,
    )

    owned = _find_owned_descriptors(descriptor_root, descriptors_before_launch, binary, 4242)

    assert [item.descriptor_path for item in owned] == [exact.resolve()]


def test_remove_test_directory_rejects_missing_or_foreign_owner_marker(tmp_path: Path) -> None:
    unmarked = tmp_path / "RatsCliTaskE2E-unmarked"
    unmarked.mkdir()
    with pytest.raises(AssertionError, match="unmarked"):
        _remove_test_directory(unmarked, "this-run")
    assert unmarked.exists()

    foreign = tmp_path / "RatsCliTaskE2E-foreign"
    foreign.mkdir()
    (foreign / OWNER_MARKER_NAME).write_text("another-run", encoding="utf-8")
    with pytest.raises(AssertionError, match="another run"):
        _remove_test_directory(foreign, "this-run")
    assert foreign.exists()


def test_response_schema_guard_names_the_engine_contract_that_drifted() -> None:
    assert_response_schema("world.streaming_status", {"schema": "reverie.world-streaming/2"})

    with pytest.raises(AssertionError) as drift:
        assert_response_schema("world.streaming_status", {"schema": "reverie.world-streaming/3"})
    message = str(drift.value)
    assert "world.streaming_status" in message
    assert "reverie.world-streaming/3" in message
    assert "reverie.world-streaming/2" in message
    assert "ENGINE_RESPONSE_SCHEMAS" in message

    # A response that omits `schema` entirely is drift, not a silent pass.
    with pytest.raises(AssertionError):
        assert_response_schema("world.streaming_status", {})


def _settle_streaming(
    executor: ToolExecutor,
    refresh_tool: object,
    node_path: str,
    expected_loaded: list[str] | None = None,
    timeout: float = 10.0,
):
    """Drive the Engine's bounded async cell streaming to a settled status.

    Cell streaming is asynchronous and reports `reverie.world-streaming/2`, so
    `world.start_streaming`, `world.rebase_origin` and `world.refresh_streaming`
    return a transitional status whose `loaded_cells` is still converging. Pump
    `world.refresh_streaming` until the queue, in-flight loads and cancellations
    have all drained, then let the caller assert on the settled status.
    """
    deadline = time.monotonic() + timeout
    latest = executor.execute(refresh_tool, {"node_path": node_path})
    while True:
        data = latest.data if latest.success else {}
        settled = (
            latest.success is True
            and not data.get("async_transition_pending", False)
            and not data.get("queued_cells")
            and not data.get("loading_cells")
            and not data.get("cancelling_cells")
        )
        if settled and (expected_loaded is None or data.get("loaded_cells") == expected_loaded):
            return latest
        if time.monotonic() >= deadline:
            return latest
        time.sleep(0.01)
        latest = executor.execute(refresh_tool, {"node_path": node_path})


def _live_capability_contract(endpoint: str):
    """Read the live service's capability contract off the wire.

    `hello` is the one anonymous operation, so this needs no token and no
    session: it is the same request the runtime's discovery probe sends, issued
    directly so the raw contract can be handed to the client's own parser. The
    runtime keeps the parsed object private and publishes a summary of it, which
    is the right shape for a caller but cannot show whether the two repositories
    still agree about the columns a retry decision is made from.
    """
    payload = json.dumps(
        {"id": f"pair-{uuid.uuid4().hex}", "protocol": RATS_PROTOCOL, "op": "hello", "args": {}}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Match the runtime's direct transport to the locally discovered Engine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5.0) as response:
        body = json.loads(response.read().decode("utf-8"))
    assert body.get("ok") is True, body
    return parse_capabilities(body.get("result") or {}, protocol=RATS_PROTOCOL)


@pytest.mark.skipif(not ENGINE_BIN, reason=engine_pairing_skip_reason())
def test_cli_consumes_real_engine_rtp_task_lifecycle() -> None:
    launch_binary = Path(ENGINE_BIN).resolve()
    if not launch_binary.is_file():
        pytest.fail(f"{ENGINE_BIN_ENV} does not point to a file: {launch_binary}")
    binary = launch_binary
    if launch_binary.name.lower().endswith(".console.exe"):
        binary = launch_binary.with_name(launch_binary.name[: -len(".console.exe")] + ".exe")
    if not binary.is_file():
        pytest.fail(f"The Engine provider executable beside the console wrapper is missing: {binary}")
    engine_root = binary.parent
    local_root = engine_root / "ReverieLocal"
    run_id = uuid.uuid4().hex
    owner_marker = f"rats-engine-task-e2e:{run_id}"
    project_root = local_root / "Projects" / f"RatsCliTaskE2E-{run_id}"
    test_temp = local_root / "TestTemp"
    test_run_root = test_temp / f"RatsCliTaskE2E-{run_id}"
    cli_state_root = test_run_root / "cli"
    log_path = test_run_root / "engine.log"
    descriptor_root = binary.parent / "ReverieLocal" / "RATS" / "Services"
    process = None
    log = None
    runtime = None
    descriptors_before_launch: set[str] = set()
    owned_descriptors: list[_OwnedDescriptor] = []
    try:
        project_root.mkdir(parents=True, exist_ok=False)
        (project_root / OWNER_MARKER_NAME).write_text(owner_marker, encoding="utf-8")
        test_run_root.mkdir(parents=True, exist_ok=False)
        (test_run_root / OWNER_MARKER_NAME).write_text(owner_marker, encoding="utf-8")
        (project_root / "project.godot").write_text(
            '; Reverie-Cli RTP task fixture.\nconfig_version=5\n\n[application]\nconfig/name="Rats CLI Task E2E"\nrun/main_scene="res://main.tscn"\nconfig/features=PackedStringArray("4.8", "GL Compatibility")\n',
            encoding="utf-8",
        )
        (project_root / "main.tscn").write_text(
            "[gd_scene format=3]\n\n[node name=\"RatsCliTaskFixture\" type=\"Node2D\"]\n",
            encoding="utf-8",
        )
        (project_root / "animation").mkdir()
        (project_root / "scenes").mkdir()
        (project_root / "world").mkdir()
        (project_root / "animation" / "cli_library.tres").write_text(
            '[gd_resource type="AnimationLibrary" load_steps=2 format=3]\n\n'
            '[sub_resource type="Animation" id="Animation_idle"]\n'
            'resource_name = "Idle"\nlength = 1.0\n\n'
            '[resource]\n_data = {\n&"Idle": SubResource("Animation_idle")\n}\n',
            encoding="utf-8",
        )
        (project_root / "scenes" / "animation_runtime.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="ReverieAnimationConfiguration" path="res://animation/cli_states.tres" id="1_config"]\n\n'
            '[node name="AnimationRuntime" type="Node"]\n\n'
            '[node name="AnimationPlayer" type="AnimationPlayer" parent="."]\nroot_node = NodePath("..")\n\n'
            '[node name="StateMachine" type="ReverieAnimationStateMachine" parent="."]\n'
            'configuration = ExtResource("1_config")\nanimation_player_path = NodePath("../AnimationPlayer")\n',
            encoding="utf-8",
        )
        (project_root / "scenes" / "world_content.tscn").write_text(
            '[gd_scene format=3]\n\n[node name="CliWorldContent" type="Node3D"]\n',
            encoding="utf-8",
        )
        (project_root / "scenes" / "world_runtime.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="ReverieWorldCell" path="res://world/cli_cell.tres" id="1_cell"]\n\n'
            '[node name="WorldRuntime" type="Node3D"]\n\n'
            '[node name="Streamer" type="ReverieWorldStreamer" parent="."]\n'
            'cell_resource_paths = PackedStringArray("res://world/cli_cell.tres")\n'
            'observer_position = Vector3(0, 0, 0)\n'
            'load_distance = 0.0\n'
            'unload_distance = 10.0\n'
            'update_interval = 0.0\n',
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "TEMP": str(test_run_root),
                "TMP": str(test_run_root),
                "REVERIE_RATS": "1",
                "REVERIE_RATS_PORT": "0",
                "REVERIE_AI_BRIDGE": "0",
            }
        )
        descriptors_before_launch = {
            _path_key(path)
            for path in descriptor_root.glob("rats-*.json")
            if path.is_file()
        }
        log = log_path.open("w", encoding="utf-8")
        runtime = RatsRuntime(cli_state_root, request_timeout=2.0, probe_timeout=0.5, tool_timeout=15.0)
        process = subprocess.Popen(
            [str(binary), "--editor", "--headless", "--path", str(project_root), "--quit-after", "7200"],
            cwd=engine_root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        provider_pid = process.pid

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            owned_descriptors = _find_owned_descriptors(
                descriptor_root,
                descriptors_before_launch,
                binary,
                provider_pid,
            )
            if owned_descriptors:
                break
            if process.poll() is not None:
                pytest.fail(
                    f"Engine exited before publishing its owned descriptor with code {process.returncode}; "
                    "the per-run log is withheld from assertion output"
                )
            time.sleep(0.1)
        if len(owned_descriptors) != 1:
            pytest.fail(
                f"Expected exactly one new descriptor for launched PID {provider_pid}; "
                f"found {len(owned_descriptors)}"
            )
        owned_descriptor = owned_descriptors[0]

        runtime.register_provider_executable(PROVIDER_ID, binary)
        state = {}
        discovered_service = None
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            state = runtime.refresh()
            discovered_service = next(
                (
                    item
                    for item in state.get("services", [])
                    if item.get("providerId") == owned_descriptor.provider_id
                    and item.get("serviceId") == owned_descriptor.service_id
                    and int(item.get("pid", 0) or 0) == owned_descriptor.provider_pid
                    and _path_key(Path(str(item.get("executable", "")))) == _path_key(owned_descriptor.executable)
                    and _path_key(Path(str(item.get("descriptorPath", ""))))
                    == _path_key(owned_descriptor.descriptor_path)
                ),
                None,
            )
            if discovered_service is not None:
                break
            if process.poll() is not None:
                pytest.fail(
                    f"Engine exited before runtime discovery with code {process.returncode}; "
                    "the per-run log is withheld from assertion output"
                )
            time.sleep(0.1)
        assert discovered_service is not None, state
        service_id = owned_descriptor.service_id
        state = runtime.set_provider_enabled(PROVIDER_ID, binary, True, ["read", "project", "edit", "run"])
        service = next(
            item
            for item in state["services"]
            if item["providerId"] == PROVIDER_ID
            and item["serviceId"] == service_id
            and int(item["pid"]) == provider_pid
            and _path_key(Path(item["executable"])) == _path_key(binary)
            and _path_key(Path(item["descriptorPath"])) == _path_key(owned_descriptor.descriptor_path)
        )
        assert service["connection"] == "connected", service

        # The retry contract, against the service that actually shipped it. The
        # Engine suite proves its compiled tables are consistent and this
        # repository's unit tests prove the client's decisions are right for a
        # given contract; neither can show the two still agree, which is the
        # failure this asserts. Read raw so the columns a retry turns on are
        # checked, not the summary the runtime republishes.
        live_capabilities, contract_rejections = _live_capability_contract(service["endpoint"])
        assert_retry_contract(live_capabilities, contract_rejections)
        # And the same fact through the runtime's published payload, which is
        # what a caller branching on the feature would read.
        assert RETRY_SEMANTICS_FEATURE in service["features"], service["features"]

        requested_dynamic_tools = [
            "animation.configure",
            "scene.open",
            "scene.duplicate_node",
            "scene.move_node",
            "scene.instantiate",
            "scene.pack",
            "node.add_to_group",
            "node.remove_from_group",
            "node.get_groups",
            "scene.find_in_group",
            "scene.connect_signal",
            "scene.disconnect_signal",
            "node.get_signal_connections",
            "node.list_signals",
            "node.list_properties",
            "node.list_methods",
            "scene.find_nodes",
            "scene.rename_node",
            "scene.reorder_node",
            "project.list_files",
            "project.read_file",
            "animation.play",
            "animation.status",
            "world.create_region",
            "world.create_cell",
            "world.start_streaming",
            "world.refresh_streaming",
            "world.load_cell",
            "world.release_cell",
            "world.rebase_origin",
            "world.set_streaming_budget",
            "world.set_cell_state",
            "world.get_cell_state",
            "world.clear_cell_state",
            "world.save_state_store",
            "world.load_state_store",
            "world.clear_state_store",
            "world.streaming_status",
            "world.stop_streaming",
        ]
        definitions = []
        for offset in range(0, len(requested_dynamic_tools), 16):
            definitions.extend(
                runtime.describe(
                    service_id,
                    requested_dynamic_tools[offset : offset + 16],
                    provider_id=PROVIDER_ID,
                )
            )
        assert {item.get("name") for item in definitions} == set(requested_dynamic_tools)
        executor = ToolExecutor(project_root)
        executor.update_context("rats_runtime", runtime)
        dynamic_tools = {
            native_name: f"rats_reverie_engine_{native_name.replace('.', '_')}"
            for native_name in requested_dynamic_tools
        }
        # Progressive disclosure caps the resident working set at
        # rats._MAX_LOADED_DEFINITIONS_PER_SESSION, so the full catalog described
        # above cannot stay model-visible all at once. Each coherent flow below
        # re-describes exactly the tools it is about to call, immediately before
        # calling them -- which is how a real caller keeps one task's tools loaded
        # without overflowing the cap -- and asserts that working set is resident.
        def _resident_schemas():
            return {
                item["function"]["name"]: item["function"]["parameters"]
                for item in executor.get_tool_schemas(mode="reverie")
            }

        def _load_working_set(names):
            for offset in range(0, len(names), 16):
                runtime.describe(service_id, names[offset : offset + 16], provider_id=PROVIDER_ID)
            schemas = _resident_schemas()
            assert all(dynamic_tools[name] in schemas for name in names), (
                sorted(name for name in names if dynamic_tools[name] not in schemas)
            )
            return schemas

        definitions_by_name = {item["name"]: item for item in definitions}
        assert definitions_by_name["world.get_cell_state"].get("permission") == "read"
        assert definitions_by_name["world.set_cell_state"].get("permission") == "run"
        assert definitions_by_name["scene.duplicate_node"].get("permission") == "edit"
        assert definitions_by_name["scene.move_node"].get("permission") == "edit"
        assert definitions_by_name["scene.instantiate"].get("permission") == "edit"
        assert definitions_by_name["scene.pack"].get("permission") == "edit"
        assert definitions_by_name["node.add_to_group"].get("permission") == "edit"
        assert definitions_by_name["node.remove_from_group"].get("permission") == "edit"
        assert definitions_by_name["node.get_groups"].get("permission") == "read"
        assert definitions_by_name["scene.find_in_group"].get("permission") == "read"
        assert definitions_by_name["scene.connect_signal"].get("permission") == "edit"
        assert definitions_by_name["scene.disconnect_signal"].get("permission") == "edit"
        assert definitions_by_name["node.get_signal_connections"].get("permission") == "read"
        assert definitions_by_name["node.list_signals"].get("permission") == "read"
        assert definitions_by_name["node.list_properties"].get("permission") == "read"
        assert definitions_by_name["node.list_methods"].get("permission") == "read"
        assert definitions_by_name["scene.find_nodes"].get("permission") == "read"
        assert definitions_by_name["scene.rename_node"].get("permission") == "edit"
        assert definitions_by_name["scene.reorder_node"].get("permission") == "edit"
        assert definitions_by_name["project.list_files"].get("permission") == "read"
        assert definitions_by_name["project.read_file"].get("permission") == "read"

        # Scene-editing working set: everything exercised against the
        # animation_runtime scene below (animation, object CRUD, prefab, group and
        # signal tools) is one coherent task, so load it as one working set.
        scene_editing_tools = [
            "animation.configure",
            "scene.open",
            "animation.play",
            "animation.status",
            "scene.duplicate_node",
            "scene.move_node",
            "scene.instantiate",
            "scene.pack",
            "node.add_to_group",
            "node.remove_from_group",
            "node.get_groups",
            "scene.find_in_group",
            "scene.connect_signal",
            "scene.disconnect_signal",
            "node.get_signal_connections",
            "node.list_signals",
            "node.list_properties",
            "node.list_methods",
            "scene.find_nodes",
            "scene.rename_node",
            "scene.reorder_node",
            "project.list_files",
            "project.read_file",
        ]
        schemas = _load_working_set(scene_editing_tools)
        assert schemas[dynamic_tools["animation.status"]].get("additionalProperties") is False

        configured = executor.execute(
            dynamic_tools["animation.configure"],
            {
                "path": "animation/cli_states.tres",
                "configuration_id": "cli-runtime.01",
                "animation_library_path": "animation/cli_library.tres",
                "states": [{"id": "idle", "animation": "Idle"}],
                "initial_state": "idle",
                "transitions": [],
                "playback_speed": 1.0,
                "root_motion_track": "",
            },
        )
        assert configured.success is True
        assert_response_schema("animation.configure", configured.data)
        opened = executor.execute(
            dynamic_tools["scene.open"],
            {"path": "scenes/animation_runtime.tscn"},
        )
        assert opened.success is True and opened.data.get("root_type") == "Node"
        played = executor.execute(
            dynamic_tools["animation.play"],
            {"node_path": "StateMachine"},
        )
        assert played.success is True and played.data.get("current_state") == "idle" and played.data.get("playing") is True
        animation_status = executor.execute(
            dynamic_tools["animation.status"],
            {"node_path": "StateMachine"},
        )
        assert animation_status.success is True
        assert_response_schema("animation.status", animation_status.data)

        # scene.duplicate_node / scene.move_node reach the Cli purely through the
        # shared RATS tool catalog, so exercise them against the live session on
        # the scene opened above: the object-CRUD pair is proven end to end from
        # the client, not merely listed by discovery. Only a copy is created and
        # then reparented, so the originals animation.play acted on are untouched.
        duplicated_node = executor.execute(
            dynamic_tools["scene.duplicate_node"],
            {"node_path": "AnimationPlayer"},
        )
        assert (
            duplicated_node.success is True
            and duplicated_node.data.get("source_path") == "AnimationPlayer"
            and duplicated_node.data.get("node_path") == "AnimationPlayer2"
            and duplicated_node.data.get("type") == "AnimationPlayer"
        ), duplicated_node.error or duplicated_node.data
        moved_node = executor.execute(
            dynamic_tools["scene.move_node"],
            {"node_path": "AnimationPlayer2", "new_parent_path": "StateMachine"},
        )
        assert (
            moved_node.success is True
            and moved_node.data.get("node_path") == "AnimationPlayer2"
            and moved_node.data.get("new_node_path") == "StateMachine/AnimationPlayer2"
            and moved_node.data.get("type") == "AnimationPlayer"
        ), moved_node.error or moved_node.data

        # scene.instantiate is the §9 prefab primitive on the same shared catalog:
        # drop an existing project scene into the live session as a sub-scene
        # reference. world_content.tscn is a distinct file from the open scene, so
        # this is a genuine cross-scene instance (not the self-instance the Engine
        # guards). Nothing is saved, so the prefab source and the open scene files
        # stay byte-for-byte as the world block below reopens the session anyway.
        instantiated = executor.execute(
            dynamic_tools["scene.instantiate"],
            {"path": "scenes/world_content.tscn"},
        )
        assert (
            instantiated.success is True
            and instantiated.data.get("applied") is True
            and instantiated.data.get("node_path") == "CliWorldContent"
            and instantiated.data.get("source_scene") == "scenes/world_content.tscn"
            and instantiated.data.get("type") == "Node3D"
        ), instantiated.error or instantiated.data

        # scene.pack is the §9 prefab produce-side on the same shared catalog: extract
        # an in-scene branch into a new project .tscn without mutating the host scene.
        # AnimationPlayer is a plain branch of the open scene; packing it is a genuine
        # cross-scene write that leaves the open scene untouched (nothing is saved, so
        # the world block below reopens the session regardless).
        packed_branch = executor.execute(
            dynamic_tools["scene.pack"],
            {"node_path": "AnimationPlayer", "path": "scenes/cli_packed_branch.tscn"},
        )
        assert (
            packed_branch.success is True
            and packed_branch.data.get("applied") is True
            and packed_branch.data.get("path") == "scenes/cli_packed_branch.tscn"
            and packed_branch.data.get("node_path") == "AnimationPlayer"
            and packed_branch.data.get("type") == "AnimationPlayer"
        ), packed_branch.error or packed_branch.data

        # node group tools are the §9 entity-tagging family on the same shared
        # catalog: tag a live scene node with a persistent group and query it both
        # per-node (node.get_groups) and scene-wide (scene.find_in_group), then drop
        # the tag again. Nothing is saved, so the membership lives only in the
        # in-memory session the world block reopens away below.
        tagged = executor.execute(
            dynamic_tools["node.add_to_group"],
            {"node_path": "StateMachine", "group": "cli_enemies"},
        )
        assert (
            tagged.success is True
            and tagged.data.get("applied") is True
            and tagged.data.get("node_path") == "StateMachine"
            and tagged.data.get("group") == "cli_enemies"
            and tagged.data.get("groups") == ["cli_enemies"]
        ), tagged.error or tagged.data
        node_groups = executor.execute(
            dynamic_tools["node.get_groups"],
            {"node_path": "StateMachine"},
        )
        assert (
            node_groups.success is True
            and node_groups.data.get("groups") == ["cli_enemies"]
            and node_groups.data.get("count") == 1
        ), node_groups.error or node_groups.data
        found_in_group = executor.execute(
            dynamic_tools["scene.find_in_group"],
            {"group": "cli_enemies"},
        )
        assert (
            found_in_group.success is True
            and found_in_group.data.get("nodes") == ["StateMachine"]
            and found_in_group.data.get("count") == 1
        ), found_in_group.error or found_in_group.data
        untagged = executor.execute(
            dynamic_tools["node.remove_from_group"],
            {"node_path": "StateMachine", "group": "cli_enemies"},
        )
        assert (
            untagged.success is True
            and untagged.data.get("applied") is True
            and untagged.data.get("groups") == []
        ), untagged.error or untagged.data

        # signal-wiring tools are the §9 event-graph family on the same shared
        # catalog: discover a node's signals, wire one to another node's method
        # as a persistent connection, read it back per-node, then unwire it.
        # Nothing is saved, so the edge lives only in the in-memory session the
        # world block reopens away below.
        node_signals = executor.execute(
            dynamic_tools["node.list_signals"],
            {"node_path": "StateMachine"},
        )
        assert (
            node_signals.success is True
            and "renamed" in node_signals.data.get("signals", [])
            and node_signals.data.get("count", 0) > 0
        ), node_signals.error or node_signals.data
        signal_edge = {
            "from_path": "StateMachine",
            "signal": "renamed",
            "to_path": "AnimationPlayer",
            "method": "queue_free",
        }
        expected_signal_conn = [{"signal": "renamed", "to": "AnimationPlayer", "method": "queue_free"}]
        wired = executor.execute(
            dynamic_tools["scene.connect_signal"],
            signal_edge,
        )
        assert (
            wired.success is True
            and wired.data.get("applied") is True
            and wired.data.get("connections") == expected_signal_conn
        ), wired.error or wired.data
        signal_connections = executor.execute(
            dynamic_tools["node.get_signal_connections"],
            {"node_path": "StateMachine"},
        )
        assert (
            signal_connections.success is True
            and signal_connections.data.get("connections") == expected_signal_conn
            and signal_connections.data.get("count") == 1
        ), signal_connections.error or signal_connections.data
        unwired = executor.execute(
            dynamic_tools["scene.disconnect_signal"],
            signal_edge,
        )
        assert (
            unwired.success is True
            and unwired.data.get("applied") is True
            and unwired.data.get("connections") == []
        ), unwired.error or unwired.data

        # node-introspection tools are the §9 discovery family on the same shared
        # catalog: enumerate a live node's inspectable properties (with type and
        # editability) and its callable methods -- which is how an agent finds a
        # valid target for node.set_property and a valid method for
        # scene.connect_signal before calling them. Both are read-only; nothing is
        # mutated or saved. The editability the engine reports must survive the
        # round-trip, so an exported Resource property is asserted non-editable
        # while a plain node property is not.
        node_properties = executor.execute(
            dynamic_tools["node.list_properties"],
            {"node_path": "StateMachine"},
        )
        prop_entries = node_properties.data.get("properties", []) if node_properties.success else []
        prop_names = [entry.get("name") for entry in prop_entries]
        configuration_entry = next(
            (entry for entry in prop_entries if entry.get("name") == "configuration"), None
        )
        assert (
            node_properties.success is True
            and len(prop_entries) > 0
            and node_properties.data.get("count") == len(prop_entries)
            and all(set(entry.keys()) == {"name", "type", "editable"} for entry in prop_entries)
            and prop_names == sorted(prop_names)
            and "process_mode" in prop_names
            and configuration_entry == {"name": "configuration", "type": "Object", "editable": False}
        ), node_properties.error or node_properties.data
        node_methods = executor.execute(
            dynamic_tools["node.list_methods"],
            {"node_path": "StateMachine"},
        )
        method_names = node_methods.data.get("methods", []) if node_methods.success else []
        assert (
            node_methods.success is True
            and all(isinstance(name, str) for name in method_names)
            and method_names == sorted(set(method_names))
            and node_methods.data.get("count") == len(method_names)
            and "queue_free" in method_names
            and "no_such_method" not in method_names
        ), node_methods.error or node_methods.data

        # scene.find_nodes rounds out the §9 discovery family on the same shared
        # catalog: locate live nodes by an is-a class filter and/or a case-sensitive
        # name glob over the whole open scene in one call, so an agent can target a
        # node without walking a full scene.get_tree dump. Read-only; nothing mutated
        # or saved. The AnimationPlayer copy reparented under StateMachine above makes
        # the type filter a genuine cross-branch, multi-hit query, and its result must
        # come back as sorted root-relative paths with a matching count.
        found_by_type = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {"type": "AnimationPlayer"},
        )
        assert (
            found_by_type.success is True
            and found_by_type.data.get("nodes") == ["AnimationPlayer", "StateMachine/AnimationPlayer2"]
            and found_by_type.data.get("count") == 2
            and found_by_type.data.get("type") == "AnimationPlayer"
        ), found_by_type.error or found_by_type.data
        found_by_name = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {"pattern": "StateMachine"},
        )
        assert (
            found_by_name.success is True
            and found_by_name.data.get("nodes") == ["StateMachine"]
            and found_by_name.data.get("count") == 1
            and found_by_name.data.get("pattern") == "StateMachine"
        ), found_by_name.error or found_by_name.data
        found_combined = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {"type": "AnimationPlayer", "pattern": "*2"},
        )
        assert (
            found_combined.success is True
            and found_combined.data.get("nodes") == ["StateMachine/AnimationPlayer2"]
            and found_combined.data.get("count") == 1
        ), found_combined.error or found_combined.data
        rejected_find = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {},
        )
        assert rejected_find.success is False, rejected_find.data
        # scene.rename_node is the edit counterpart on the same shared catalog:
        # rename one live node in place and have it answer to the new path. The
        # AnimationPlayer copy reparented under StateMachine gives a cross-branch,
        # non-root target, so the reported new_node_path must carry the StateMachine
        # prefix rather than being a bare name. find_nodes (read) is used to confirm
        # the move landed and the old name retired -- the two discovery tools
        # cross-checking each other over one session.
        renamed = executor.execute(
            dynamic_tools["scene.rename_node"],
            {"node_path": "StateMachine/AnimationPlayer2", "name": "AnimationPlayerRenamed"},
        )
        assert (
            renamed.success is True
            and renamed.data.get("applied") is True
            and renamed.data.get("node_path") == "StateMachine/AnimationPlayer2"
            and renamed.data.get("new_node_path") == "StateMachine/AnimationPlayerRenamed"
            and renamed.data.get("name") == "AnimationPlayerRenamed"
            and renamed.data.get("execution_thread") == "main"
        ), renamed.error or renamed.data
        confirm_renamed = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {"pattern": "AnimationPlayerRenamed"},
        )
        assert (
            confirm_renamed.success is True
            and confirm_renamed.data.get("nodes") == ["StateMachine/AnimationPlayerRenamed"]
        ), confirm_renamed.error or confirm_renamed.data
        confirm_retired = executor.execute(
            dynamic_tools["scene.find_nodes"],
            {"pattern": "AnimationPlayer2"},
        )
        assert (
            confirm_retired.success is True
            and confirm_retired.data.get("nodes") == []
        ), confirm_retired.error or confirm_retired.data
        # An invalid Node name is refused before any mutation, structure-independent.
        rejected_rename = executor.execute(
            dynamic_tools["scene.rename_node"],
            {"node_path": "StateMachine/AnimationPlayerRenamed", "name": "bad/name"},
        )
        assert rejected_rename.success is False, rejected_rename.data
        # scene.reorder_node lands alongside rename on the same shared edit catalog:
        # move a live node to a chosen slot among its siblings, the gap add_node and
        # move_node leave since both only append. Reordering the renamed
        # AnimationPlayer to the front is always in-bounds -- its own presence
        # guarantees at least one sibling slot -- so the check stays
        # structure-robust while proving the ordering edit reaches the engine.
        reordered = executor.execute(
            dynamic_tools["scene.reorder_node"],
            {"node_path": "StateMachine/AnimationPlayerRenamed", "index": 0},
        )
        assert (
            reordered.success is True
            and reordered.data.get("applied") is True
            and reordered.data.get("index") == 0
            and isinstance(reordered.data.get("old_index"), int)
            and reordered.data.get("name") == "AnimationPlayerRenamed"
            and reordered.data.get("execution_thread") == "main"
        ), reordered.error or reordered.data
        # A target index outside the sibling range is refused before any mutation.
        rejected_reorder = executor.execute(
            dynamic_tools["scene.reorder_node"],
            {"node_path": "StateMachine/AnimationPlayerRenamed", "index": -1},
        )
        assert rejected_reorder.success is False, rejected_reorder.data
        # project.list_files is the read-only discovery primitive on the same
        # shared catalog: enumerate the confined project tree filtered to scenes.
        # The scene opened above (scenes/animation_runtime.tscn) is always present,
        # so the check stays structure-robust while proving the read reaches the
        # engine on the main thread with the bounded, sorted contract.
        listed = executor.execute(
            dynamic_tools["project.list_files"],
            {"extensions": ["tscn"]},
        )
        assert (
            listed.success is True
            and isinstance(listed.data.get("entries"), list)
            and listed.data.get("count") == len(listed.data["entries"])
            and listed.data.get("truncated") is False
            and listed.data.get("execution_thread") == "main"
            and any(
                entry.get("path") == "scenes/animation_runtime.tscn"
                for entry in listed.data["entries"]
            )
            and all(entry.get("extension") == "tscn" for entry in listed.data["entries"])
        ), listed.error or listed.data
        # A directory escaping the project boundary is refused before any read.
        rejected_list = executor.execute(
            dynamic_tools["project.list_files"],
            {"directory": "../escape"},
        )
        assert rejected_list.success is False, rejected_list.data
        # project.read_file is the read-only content primitive beside list_files:
        # pull the scene opened above straight back over RTP. A .tscn is UTF-8 text,
        # so the engine must decode it and report a whole, untruncated read on the
        # main thread rather than base64 bytes.
        read = executor.execute(
            dynamic_tools["project.read_file"],
            {"path": "scenes/animation_runtime.tscn"},
        )
        assert (
            read.success is True
            and read.data.get("is_text") is True
            and read.data.get("encoding") == "utf-8"
            and read.data.get("execution_thread") == "main"
            and read.data.get("truncated") is False
            and read.data.get("bytes_read") == read.data.get("size_bytes")
            and isinstance(read.data.get("content"), str)
            and read.data["content"].startswith("[gd_scene")
        ), read.error or read.data
        # A byte cap truncates and flags the partial read without misstating the size.
        capped = executor.execute(
            dynamic_tools["project.read_file"],
            {"path": "scenes/animation_runtime.tscn", "max_bytes": 16},
        )
        assert (
            capped.success is True
            and capped.data.get("truncated") is True
            and capped.data.get("bytes_read") == 16
            and capped.data.get("size_bytes") == read.data.get("size_bytes")
        ), capped.error or capped.data
        # A path escaping the project boundary is refused before any read.
        rejected_read = executor.execute(
            dynamic_tools["project.read_file"],
            {"path": "../escape"},
        )
        assert rejected_read.success is False, rejected_read.data
        # World-streaming working set: the largest single-task tool group the
        # engine publishes. Re-describe it here (plus scene.open, which this flow
        # reuses to swap in the streaming scene) as its own coherent set, proving
        # it loads within the cap after the scene-editing set is done with.
        world_streaming_tools = [
            "scene.open",
            "world.create_region",
            "world.create_cell",
            "world.start_streaming",
            "world.refresh_streaming",
            "world.load_cell",
            "world.release_cell",
            "world.rebase_origin",
            "world.set_streaming_budget",
            "world.set_cell_state",
            "world.get_cell_state",
            "world.clear_cell_state",
            "world.save_state_store",
            "world.load_state_store",
            "world.clear_state_store",
            "world.streaming_status",
            "world.stop_streaming",
        ]
        schemas = _load_working_set(world_streaming_tools)
        assert schemas[dynamic_tools["world.streaming_status"]].get("additionalProperties") is False
        assert schemas[dynamic_tools["world.set_cell_state"]]["properties"]["state"].get("additionalProperties") is True

        region = executor.execute(
            dynamic_tools["world.create_region"],
            {
                "path": "world/cli_region.tres",
                "region_id": "cli-region",
                "realm_id": "cli-realm",
                "origin_cell": [0, 0, 0],
                "cell_count": [2, 1, 1],
                "cell_size": [100.0, 50.0, 100.0],
                "persistence_key": "cli-region-state",
            },
        )
        assert region.success is True
        assert_response_schema("world.create_region", region.data)
        cell = executor.execute(
            dynamic_tools["world.create_cell"],
            {
                "path": "world/cli_cell.tres",
                "region_path": "world/cli_region.tres",
                "cell_id": "cli-cell",
                "coordinate": [0, 0, 0],
                "declared_resident_bytes": 1024,
                "content_scenes": ["scenes/world_content.tscn"],
                "persistence_key": "cli-cell-state",
            },
        )
        assert cell.success is True
        assert_response_schema("world.create_cell", cell.data)
        opened_world = executor.execute(
            dynamic_tools["scene.open"],
            {"path": "scenes/world_runtime.tscn"},
        )
        assert opened_world.success is True and opened_world.data.get("root_type") == "Node3D"
        started_world = executor.execute(
            dynamic_tools["world.start_streaming"],
            {"node_path": "Streamer"},
        )
        world_start_failure = {}
        if started_world.success is not True:
            log.flush()
            world_start_failure = {
                "tool_error": started_world.error,
                "process_exit": process.poll(),
                "engine_log": log_path.read_text(encoding="utf-8", errors="replace")[-4000:],
            }
        assert started_world.success is True, world_start_failure
        settled_world = _settle_streaming(
            executor,
            dynamic_tools["world.refresh_streaming"],
            "Streamer",
            ["cli-cell"],
        )
        assert settled_world.success is True and settled_world.data.get("loaded_cells") == ["cli-cell"], (
            world_start_failure or settled_world.data
        )
        world_status = executor.execute(
            dynamic_tools["world.streaming_status"],
            {"node_path": "Streamer"},
        )
        assert world_status.success is True
        assert_response_schema("world.streaming_status", world_status.data)
        rebased_world = executor.execute(
            dynamic_tools["world.rebase_origin"],
            {"node_path": "Streamer", "origin_cell": [1, 0, 0]},
        )
        assert (
            rebased_world.success is True
            and rebased_world.data.get("origin_cell") == [1, 0, 0]
            and rebased_world.data.get("origin_world_position") == [100.0, 0.0, 0.0]
            and rebased_world.data.get("last_rebase_delta") == [100.0, 0.0, 0.0]
            and rebased_world.data.get("rebase_count") == 1
        )
        settled_rebase = _settle_streaming(
            executor,
            dynamic_tools["world.refresh_streaming"],
            "Streamer",
            ["cli-cell"],
        )
        assert settled_rebase.success is True and settled_rebase.data.get("loaded_cells") == ["cli-cell"], (
            settled_rebase.data
        )
        budgeted_world = executor.execute(
            dynamic_tools["world.set_streaming_budget"],
            {"node_path": "Streamer", "max_loaded_cells": 1, "max_declared_resident_bytes": 1024},
        )
        assert (
            budgeted_world.success is True
            and budgeted_world.data.get("budget_limited") is True
            and budgeted_world.data.get("loaded_declared_resident_bytes") == 1024
            and budgeted_world.data.get("deferred_cells") == []
        )
        cleared_store = executor.execute(
            dynamic_tools["world.clear_state_store"],
            {"node_path": "Streamer"},
        )
        assert cleared_store.success is True and cleared_store.data.get("state_count") == 0
        cli_cell_state = {"checkpoint": 9, "flags": ["cli", True], "nested": {"coins": 4}}
        set_state = executor.execute(
            dynamic_tools["world.set_cell_state"],
            {"node_path": "Streamer", "cell_id": "cli-cell", "state": cli_cell_state},
        )
        assert (
            set_state.success is True
            and set_state.data.get("state_cells") == ["cli-cell"]
            and set_state.data.get("state_dirty") is True
            and set_state.data.get("state_handoff_count") == 0
        )
        read_state = executor.execute(
            dynamic_tools["world.get_cell_state"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert read_state.success is True and read_state.data.get("state") == cli_cell_state
        refreshed_world = executor.execute(
            dynamic_tools["world.refresh_streaming"],
            {"node_path": "Streamer", "observer_position": [1000.0, 0.0, 0.0]},
        )
        assert refreshed_world.success is True
        settled_unload = _settle_streaming(
            executor,
            dynamic_tools["world.refresh_streaming"],
            "Streamer",
            [],
        )
        assert (
            settled_unload.success is True
            and settled_unload.data.get("loaded_cells") == []
            and settled_unload.data.get("state_dirty") is False
            and settled_unload.data.get("state_handoff_count") == 1
            and settled_unload.data.get("last_state_handoff_cells") == ["cli-cell"]
        ), settled_unload.data
        cleared_state = executor.execute(
            dynamic_tools["world.clear_cell_state"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert cleared_state.success is True and cleared_state.data.get("state_count") == 0
        loaded_state = executor.execute(
            dynamic_tools["world.load_state_store"],
            {"node_path": "Streamer"},
        )
        assert loaded_state.success is True and loaded_state.data.get("state_cells") == ["cli-cell"]
        read_loaded_state = executor.execute(
            dynamic_tools["world.get_cell_state"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert read_loaded_state.success is True and read_loaded_state.data.get("state") == cli_cell_state
        saved_state = executor.execute(
            dynamic_tools["world.save_state_store"],
            {"node_path": "Streamer"},
        )
        assert saved_state.success is True and saved_state.data.get("state_dirty") is False
        loaded_world = executor.execute(
            dynamic_tools["world.load_cell"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert loaded_world.success is True and loaded_world.data.get("manually_loaded_cells") == ["cli-cell"]
        released_world = executor.execute(
            dynamic_tools["world.release_cell"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert released_world.success is True and released_world.data.get("loaded_cells") == []
        cleared_store = executor.execute(
            dynamic_tools["world.clear_state_store"],
            {"node_path": "Streamer"},
        )
        assert cleared_store.success is True and cleared_store.data.get("state_count") == 0
        stopped_world = executor.execute(
            dynamic_tools["world.stop_streaming"],
            {"node_path": "Streamer"},
        )
        assert stopped_world.success is True and stopped_world.data.get("active") is False

        started = runtime.call_tool(
            service_id,
            "run.play",
            {"mode": "headless", "timeout_ms": 5_000},
            provider_id=PROVIDER_ID,
            deadline_ms=30_000,
            idempotency_key=f"cli-engine-task-e2e-{run_id}",
        )
        task = started.get("task", {})
        task_id = task.get("task_id", "")
        assert started.get("output", {}).get("running") is True and task_id

        events = runtime.task_events(service_id, task_id, provider_id=PROVIDER_ID)
        assert_response_schema("task.events", events)
        assert events.get("events", [])[0].get("type") == "task.started"
        status = runtime.task_status(service_id, task_id, provider_id=PROVIDER_ID)
        assert status.get("task_id") == task_id
        cancelled = runtime.cancel_task(service_id, task_id, provider_id=PROVIDER_ID)
        assert cancelled.get("cancelled") is True and cancelled.get("output", {}).get("running") is False
        logs = runtime.task_logs(service_id, task_id, provider_id=PROVIDER_ID)
        assert logs.get("task_id") == task_id and "started" in str(logs.get("text", ""))

        tasks = runtime.sync_tasks(service_id=service_id, provider_id=PROVIDER_ID)
        tracked = next(item for item in tasks if item.get("task_id") == task_id)
        assert tracked.get("status", {}).get("running") is False
        diagnostics = [
            json.loads(line)
            for line in runtime.diagnostics_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        task_diagnostics = [entry for entry in diagnostics if entry.get("taskId") == task_id]
        assert task_diagnostics and all(
            entry.get("auditId") and entry.get("resultSha256") for entry in task_diagnostics
        )
        assert runtime._tasks
    finally:
        try:
            if runtime is not None:
                runtime.shutdown()
        finally:
            try:
                if process is not None:
                    try:
                        _stop_engine_process(process)
                    finally:
                        if not _wait_for_pid_exit(process.pid, 10.0):
                            raise AssertionError(
                                f"Engine provider PID {process.pid} is still running after process cleanup"
                            )
                        late_descriptors = _find_owned_descriptors(
                            descriptor_root,
                            descriptors_before_launch,
                            binary,
                            process.pid,
                        )
                        descriptors_to_remove = {
                            _path_key(item.descriptor_path): item
                            for item in [*owned_descriptors, *late_descriptors]
                        }
                        for owned_descriptor in descriptors_to_remove.values():
                            _remove_test_descriptor(owned_descriptor, binary=binary)
            finally:
                if log is not None:
                    log.close()
                try:
                    if project_root.exists():
                        _remove_test_directory(project_root, owner_marker)
                finally:
                    if test_run_root.exists():
                        _remove_test_directory(test_run_root, owner_marker)
