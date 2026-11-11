"""Keep actual package observations independent of slow diagnostic-log writes."""
import ast
import json
from pathlib import Path
import queue
import threading
import time
import traceback
import types

import psutil


SOURCE = Path(__file__).with_name('conversation_package.py')


def environment(output, monkeypatch, *, blocked=False, fail_flush=False):
    observed = []
    entered = threading.Event()
    released = threading.Event()
    original_open = Path.open
    sample_stop = threading.Event()
    writer_stop = threading.Event()
    rows = [{'pid': 42, 'parent': 0, 'created_at': 1.0, 'rss': 1024,
             'write_bytes': 2048, 'name': 'reverie.exe', 'label': '中文\n完整'}]

    class Stream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.stream.close()

        def write(self, value):
            if blocked:
                entered.set()
                assert released.wait(5), 'Test must release the diagnostic writer.'
            return self.stream.write(value)

        def flush(self):
            if fail_flush:
                raise OSError('Synthetic diagnostic flush failure')
            self.stream.flush()

    def open_log(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return Stream(stream) if path == output / 'resources.jsonl' and mode == 'a' else stream

    monkeypatch.setattr(Path, 'open', open_log)

    def collect(_pid, _errors):
        observed.append(time.monotonic())
        if len(observed) == 3:
            sample_stop.set()
        return rows

    namespace = {'output': output, 'time': time, 'json': json, 'psutil': psutil, 'traceback': traceback,
                 'queue': queue, 'sampling_stop': sample_stop,
                 'resource_writer_stop': writer_stop, 'resource_queue': queue.Queue(128),
                 'process': types.SimpleNamespace(pid=42), 'started': time.monotonic(),
                 'resources': collect, 'tracked': {}, 'io_peaks': {},
                 'sampling_gaps': [], 'last_resource_sample': [None],
                 'report': {'resource_access_errors': [], 'resource_writer_errors': [],
                            'resource_samples_collected': 0, 'resource_samples_written': 0,
                            'peak_tree_rss': 0, 'peak_process_count': 0,
                            'peak_kernel_tree_rss': 0}}
    main = next(node for node in ast.parse(SOURCE.read_text(encoding='utf-8')).body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    functions = [node for node in main.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('sample_resources', 'write_resources')]
    module = ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[]))
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    return namespace, observed, entered, released, rows


def start(namespace):
    errors = []

    def invoke(name):
        try:
            namespace[name]()
        except Exception as error:
            errors.append(error)

    threads = []
    for name in ('write_resources', 'sample_resources'):
        if name in namespace:
            thread = threading.Thread(target=invoke, args=(name,))
            thread.start()
            threads.append(thread)
    return threads, errors


def finish(namespace, threads, released):
    released.set()
    namespace['sampling_stop'].set()
    # Collection must finish before the writer stops accepting records.
    threads[-1].join(5)
    namespace['resource_writer_stop'].set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()


def test_sampling_continues_while_log_write_is_blocked(tmp_path, monkeypatch):
    namespace, observed, entered, released, rows = environment(tmp_path, monkeypatch, blocked=True)
    threads, errors = start(namespace)
    try:
        assert entered.wait(2)
        deadline = time.monotonic() + 2
        while len(observed) < 3 and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(observed) == 3, 'Log I/O must not interrupt process observations.'
    finally:
        finish(namespace, threads, released)
    assert not errors
    saved = [json.loads(line) for line in (tmp_path / 'resources.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(saved) == 3
    assert [row['processes'] for row in saved] == [rows, rows, rows]
    assert [row['elapsed_seconds'] for row in saved] == sorted(row['elapsed_seconds'] for row in saved)
    assert namespace['report']['resource_samples_collected'] == namespace['report']['resource_samples_written'] == 3
    assert max(namespace['sampling_gaps']) <= 5
    assert namespace['report']['peak_tree_rss'] == 1024
    assert namespace['tracked'] == {42: 1.0}


def test_log_flush_failure_is_reported_and_stops_sampling(tmp_path, monkeypatch):
    namespace, _observed, _entered, released, _rows = environment(tmp_path, monkeypatch, fail_flush=True)
    threads, errors = start(namespace)
    try:
        deadline = time.monotonic() + 2
        while not namespace['report']['resource_writer_errors'] and time.monotonic() < deadline:
            time.sleep(.01)
        assert namespace['report']['resource_writer_errors']
        assert namespace['sampling_stop'].is_set()
    finally:
        finish(namespace, threads, released)
    assert not errors
    assert namespace['report']['resource_samples_written'] == 0


def test_full_queue_fails_visibly_without_waiting_or_discarding(tmp_path, monkeypatch):
    namespace, _observed, _entered, _released, _rows = environment(tmp_path, monkeypatch)
    namespace['resource_queue'] = queue.Queue(1)
    namespace['resource_queue'].put_nowait({'retained': True})
    namespace['sample_resources']()
    assert namespace['sampling_stop'].is_set()
    assert namespace['report']['resource_writer_errors']
    assert namespace['resource_queue'].get_nowait() == {'retained': True}


def test_slow_resource_collection_remains_visible_in_gap_evidence(tmp_path, monkeypatch):
    namespace, _observed, _entered, _released, rows = environment(tmp_path, monkeypatch)
    clock = [100.0]

    class Stop:
        def is_set(self):
            return namespace['report']['resource_samples_collected'] >= 3

        def wait(self, seconds):
            clock[0] += seconds

    def slow_collection(_pid, _errors):
        clock[0] += 6
        return rows

    namespace.update(time=types.SimpleNamespace(monotonic=lambda: clock[0], time=lambda: clock[0]),
                     sampling_stop=Stop(), resources=slow_collection, started=100.0)
    namespace['sample_resources']()
    assert namespace['sampling_gaps'] == [6.5, 6.5]
    assert max(namespace['sampling_gaps']) > 5
    saved = [namespace['resource_queue'].get_nowait() for _ in range(3)]
    assert [row['elapsed_seconds'] for row in saved] == [6, 12.5, 19]
