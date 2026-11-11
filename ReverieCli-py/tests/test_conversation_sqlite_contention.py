import multiprocessing
import traceback

import pytest

from reverie.session.aio_store import AiOStore
from reverie.session.sqlite_manager import SQLiteSessionManager
from reverie.session.streams import StreamBuffer


def _persist_conversation_in_process(base_dir, kind, index, session_id, barrier, results):
    try:
        barrier.wait(timeout=30)
        manager = AiOStore(base_dir) if kind == "aio" else SQLiteSessionManager(
            base_dir, project_root=base_dir, navigation=False,
        )
        if kind == "aio":
            manager.task_state(f"task-{index}", "running", revision=1)
        for turn in range(4):
            session = manager.load_session(session_id)
            configuration = session.metadata["runtime_config"]
            run_id = f"run-{index}-{turn}"
            revision = manager.register_run(
                session_id, run_id, configuration, session._storage_revision, str(base_dir),
                request={"prompt": f"user-{index}-{turn}", "runType": "prompt"},
            )
            revision = manager.update_run(session_id, run_id, "running", expected_revision=revision)
            barrier.wait(timeout=30)
            session.messages.append({"role": "user", "content": f"user-{index}-{turn}"})
            manager.save_session(session)
            answer = f"assistant-{index}-{turn} " + "中文🙂" * 1600
            stream = StreamBuffer(manager, session_id, run_id)
            stream.append("reasoning", f"reasoning-{index}-{turn}")
            stream.append("assistant", answer)
            timer = stream.timer
            session.messages.append({"role": "assistant", "content": answer})
            manager.save_session(session)
            if timer is not None:
                timer.join(timeout=15)
                assert not timer.is_alive(), "stream timer did not finish"
            stream.flush()
            assert {item["kind"]: item["content"] for item in manager.read_streams(session_id)} == {
                "reasoning": f"reasoning-{index}-{turn}", "assistant": answer,
            }
            manager.clear_stream(session_id, run_id)
            manager.update_run(session_id, run_id, "completed", expected_revision=revision, result={"verified": True})
            if turn % 2 == 0:
                manager.rotate_session(f"summary-{index}-{turn}")
            barrier.wait(timeout=30)
        if kind == "aio":
            manager.task_state(f"task-{index}", "completed", revision=2, result={"verified": True})
        results.put({"index": index, "error": None})
    except BaseException:
        barrier.abort()
        results.put({"index": index, "error": traceback.format_exc()})


@pytest.mark.parametrize("kind", ["ordinary", "aio"])
def test_four_processes_keep_conversation_history_streams_and_task_snapshots_independent(tmp_path, kind):
    manager = AiOStore(tmp_path) if kind == "aio" else SQLiteSessionManager(tmp_path, project_root=tmp_path)
    if kind == "aio":
        manager.enable({"version": 1})
    configurations = [
        {"version": 1, "model_ref": {"source": "fixture", "model": f"model-{index}"}}
        for index in range(4)
    ]
    session_ids = []
    for index, configuration in enumerate(configurations):
        if kind == "aio":
            session_ids.append(manager.create_task(
                str(tmp_path / f"workspace-{index}"), configuration, f"request-{index}", "save exact output",
                task_id=f"task-{index}",
            )["branch"])
        else:
            session = manager.create_session(str(index))
            session.metadata["runtime_config"] = configuration
            manager.save_session(session)
            session_ids.append(session.id)
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(4), context.Queue()
    processes = [context.Process(target=_persist_conversation_in_process, args=(
        tmp_path, kind, index, session_id, barrier, results,
    )) for index, session_id in enumerate(session_ids)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
        assert [process.exitcode for process in processes] == [0] * 4
        outcomes = [results.get(timeout=5) for _ in processes]
        assert all(outcome["error"] is None for outcome in outcomes), outcomes
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        results.close()
        results.join_thread()
    restored = AiOStore(tmp_path) if kind == "aio" else SQLiteSessionManager(tmp_path, project_root=tmp_path)
    for index, session_id in enumerate(session_ids):
        page = restored.get_page(session_id)
        assert page["total"] == 10 + (kind == "aio")
        assert page["metadata"]["runtime_config"] == configurations[index]
        assert [message["content"] for message in page["messages"] if message["role"] == "user"] == (
            ([f"request-{index}"] if kind == "aio" else []) + [f"user-{index}-{turn}" for turn in range(4)]
        )
        assert [message["content"] for message in page["messages"] if message["role"] == "assistant"] == [
            f"assistant-{index}-{turn} " + "中文🙂" * 1600 for turn in range(4)
        ]
        assert restored.read_streams(session_id) == []
        runs = restored.list_runs(session_id)
        assert len(runs) == 4
        assert all(run["state"] == "completed" and run["configuration"] == configurations[index] for run in runs)
    if kind == "ordinary":
        assert restored.selected_session_id() == session_ids[-1]
    else:
        assert restored.state()["tasks"] == []
