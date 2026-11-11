import json
import threading

import pytest

from reverie.session.memory_indexer import MemoryFragment, MemoryIndexer, ProjectIndex


@pytest.mark.parametrize('cache', ['index', 'fragments'])
def test_reader_keeps_complete_index_while_another_kernel_serializes(tmp_path, monkeypatch, cache):
    indexer = MemoryIndexer(tmp_path)
    indexer.index = ProjectIndex(last_updated='2026-11-10T11:00:00', total_sessions=1, total_messages=1)
    indexer.fragments = {'old': MemoryFragment('owner', 0, 'user', '已保存的原文', '2026-11-10T11:00:00')}
    indexer._save_index()
    indexer._save_fragments()
    target = indexer.index_path if cache == 'index' else indexer.fragments_path
    save_cache = indexer._save_index if cache == 'index' else indexer._save_fragments
    previous = target.read_bytes()
    indexer.index = ProjectIndex(last_updated='2026-11-10T11:01:00', total_sessions=2, total_messages=2)
    indexer.fragments = {'new': MemoryFragment('owner', 1, 'user', '完整的新原文', '2026-11-10T11:01:00')}
    entered = threading.Event()
    release = threading.Event()
    errors = []
    original = json.JSONEncoder.iterencode

    def paused_encode(encoder, value, _one_shot=False):
        entered.set()
        if not release.wait(5):
            raise TimeoutError('Reader did not complete.')
        yield from original(encoder, value, _one_shot)

    monkeypatch.setattr(json.JSONEncoder, 'iterencode', paused_encode)

    def save():
        try:
            save_cache()
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=save)
    worker.start()
    try:
        assert entered.wait(5)
        reader = MemoryIndexer(tmp_path)
        assert reader.load_index()
        assert reader.index.total_messages == 1
        assert next(iter(reader.fragments.values())).content == '已保存的原文'
        assert target.read_bytes() == previous
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not errors
    saved = json.loads(target.read_text(encoding='utf-8'))
    assert saved['total_messages'] == 2 if cache == 'index' else saved['content'] == '完整的新原文'


@pytest.mark.parametrize('cache', ['index', 'fragments'])
def test_interrupted_index_serialization_keeps_the_previous_cache(tmp_path, monkeypatch, cache):
    indexer = MemoryIndexer(tmp_path)
    indexer.index = ProjectIndex(last_updated='2026-11-10T11:00:00', total_sessions=1, total_messages=1)
    indexer.fragments = {'old': MemoryFragment('owner', 0, 'user', '已保存的原文', '2026-11-10T11:00:00')}
    indexer._save_index()
    indexer._save_fragments()
    target = indexer.index_path if cache == 'index' else indexer.fragments_path
    save_cache = indexer._save_index if cache == 'index' else indexer._save_fragments
    previous = target.read_bytes()
    indexer.index = ProjectIndex(last_updated='2026-11-10T11:01:00', total_sessions=2, total_messages=2)
    indexer.fragments = {'new': MemoryFragment('owner', 1, 'user', '完整的新原文', '2026-11-10T11:01:00')}
    original = json.JSONEncoder.iterencode

    def interrupted_encode(encoder, value, _one_shot=False):
        chunks = iter(original(encoder, value, _one_shot))
        yield next(chunks)
        raise OSError('Cache writer interrupted.')

    monkeypatch.setattr(json.JSONEncoder, 'iterencode', interrupted_encode)
    with pytest.raises(OSError, match='Cache writer interrupted'):
        save_cache()
    assert target.read_bytes() == previous
    saved = json.loads(target.read_text(encoding='utf-8'))
    assert saved['total_messages'] == 1 if cache == 'index' else saved['content'] == '已保存的原文'
    assert not list(tmp_path.rglob('*.tmp'))
