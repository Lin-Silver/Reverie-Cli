"""First-party Context Engine selection: final 2.5.5 always runs Python."""

from .persistent_indexer import PersistentCodebaseIndexer


def create_indexer(project_root, cache_dir=None, config=None):
    return PersistentCodebaseIndexer(project_root, cache_dir, config)
