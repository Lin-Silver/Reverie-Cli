from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from reverie.rats import RatsRuntime
from reverie.agent.tool_executor import ToolExecutor


ENGINE_BIN = str(os.environ.get("REVERIE_RATS_ENGINE_BIN", "")).strip()
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


@pytest.mark.skipif(not ENGINE_BIN, reason="Set REVERIE_RATS_ENGINE_BIN to run the real Engine/Cli RTP E2E.")
def test_cli_consumes_real_engine_rtp_task_lifecycle() -> None:
    launch_binary = Path(ENGINE_BIN).resolve()
    if not launch_binary.is_file():
        pytest.fail(f"REVERIE_RATS_ENGINE_BIN does not point to a file: {launch_binary}")
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

        requested_dynamic_tools = [
            "animation.configure",
            "scene.open",
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
        schemas = {
            item["function"]["name"]: item["function"]["parameters"]
            for item in executor.get_tool_schemas(mode="reverie")
        }
        dynamic_tools = {
            native_name: f"rats_reverie_engine_{native_name.replace('.', '_')}"
            for native_name in requested_dynamic_tools
        }
        assert all(name in schemas for name in dynamic_tools.values())
        assert schemas[dynamic_tools["animation.status"]].get("additionalProperties") is False
        assert schemas[dynamic_tools["world.streaming_status"]].get("additionalProperties") is False
        assert schemas[dynamic_tools["world.set_cell_state"]]["properties"]["state"].get("additionalProperties") is True
        definitions_by_name = {item["name"]: item for item in definitions}
        assert definitions_by_name["world.get_cell_state"].get("permission") == "read"
        assert definitions_by_name["world.set_cell_state"].get("permission") == "run"

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
        assert configured.success is True and configured.data.get("schema") == "reverie.animation-configuration/1"
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
        assert animation_status.success is True and animation_status.data.get("schema") == "reverie.animation-playback/1"

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
        assert region.success is True and region.data.get("schema") == "reverie.world-region/1"
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
        assert cell.success is True and cell.data.get("schema") == "reverie.world-cell/1"
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
        assert started_world.success is True and started_world.data.get("loaded_cells") == ["cli-cell"], world_start_failure
        world_status = executor.execute(
            dynamic_tools["world.streaming_status"],
            {"node_path": "Streamer"},
        )
        assert world_status.success is True and world_status.data.get("schema") == "reverie.world-streaming/1"
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
            and rebased_world.data.get("loaded_cells") == ["cli-cell"]
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
        )
        read_state = executor.execute(
            dynamic_tools["world.get_cell_state"],
            {"node_path": "Streamer", "cell_id": "cli-cell"},
        )
        assert read_state.success is True and read_state.data.get("state") == cli_cell_state
        saved_state = executor.execute(
            dynamic_tools["world.save_state_store"],
            {"node_path": "Streamer"},
        )
        assert saved_state.success is True and saved_state.data.get("state_dirty") is False
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
        refreshed_world = executor.execute(
            dynamic_tools["world.refresh_streaming"],
            {"node_path": "Streamer", "observer_position": [1000.0, 0.0, 0.0]},
        )
        assert refreshed_world.success is True and refreshed_world.data.get("loaded_cells") == []
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
        assert events.get("schema") == "reverie.rtp.task/1"
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
