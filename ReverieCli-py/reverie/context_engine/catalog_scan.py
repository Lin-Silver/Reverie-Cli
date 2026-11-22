"""Python manifest scanning with the existing ignore and file-type contract."""

import os
from pathlib import Path
import stat

from pathspec import GitIgnoreSpec

from .indexer import CodebaseIndexer


def _is_link(path):
    metadata = path.lstat()
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def scan(root, options=None, *, scanner=None, cache_dir=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Workspace must be a directory")
    if scanner is None:
        scanner = CodebaseIndexer(root, cache_dir)
        if options and "rules" in options:
            scanner._ignore_patterns = list(options["rules"])
            scanner._ignore_spec = GitIgnoreSpec.from_lines(scanner._ignore_patterns)
            scanner._negated_ignore_patterns = [line[1:].strip().lstrip("/")
                                                 for line in scanner._ignore_patterns if line.startswith("!")]
    elif scanner.project_root != root:
        raise ValueError("Scanner belongs to a different workspace")
    supported = scanner.SUPPORTED_EXTENSIONS | scanner.GAME_ASSET_EXTENSIONS | scanner.GAME_CONFIG_EXTENSIONS
    extensions = {"." + str(value).lstrip(".").lower() for value in options["extensions"]} if (
        options and "extensions" in options) else supported

    def failed(error):
        raise error

    result = []
    for directory, names, files in os.walk(root, onerror=failed, followlinks=False):
        parent = Path(directory)
        names[:] = sorted(name for name in names if not _is_link(parent / name) and (
            not scanner._should_ignore(parent / name) or scanner._should_descend_ignored_directory(parent / name)))
        for name in sorted(files):
            path = parent / name
            if path.suffix.lower() not in extensions or scanner._should_ignore(path):
                continue
            try:
                if _is_link(path):
                    continue
                metadata = path.stat()
            except FileNotFoundError:
                continue
            result.append({"path": path.relative_to(root).as_posix(),
                           "size": metadata.st_size, "modified_ns": metadata.st_mtime_ns})
    return result


def changes(previous, current):
    previous = {entry["path"]: entry for entry in previous}
    changed = []
    for entry in current:
        if previous.pop(entry["path"], None) != entry:
            changed.append(entry)
    return changed, sorted(previous)
