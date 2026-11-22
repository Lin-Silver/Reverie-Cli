"""Pure Python manifest, lexical index and durable Context Engine snapshots."""

from pathlib import Path
from threading import RLock
import time

from .cache import CacheManager
from .indexer import CodebaseIndexer, IndexProgress, IndexResult
from .legacy_backup import backup_legacy_index
from .storage import PythonContext
from .storage_errors import ContextStorageError
from ..diagnostics import report_suppressed_exception


class PersistentCodebaseIndexer(CodebaseIndexer):
    def __init__(self, project_root, cache_dir=None, config=None, *, database=None):
        super().__init__(project_root, cache_dir, config)
        self.cache_dir = Path(self.cache_dir)
        self._store = PythonContext(self.project_root, self.cache_dir, database=database, scanner=self)
        if not self._store.database.is_file():
            backup_legacy_index(self.cache_dir)
        self._update_lock = RLock()
        self._scan_entries = {}
        self._snapshots = self.cache_dir / "python-snapshots"
        self._full_scan_revision = 0

    def close(self):
        self._store.close()
        # A writer that was already finishing its Python snapshot must finish
        # before workspace cleanup can remove the cache directory.
        with self._update_lock:
            pass

    def _cache_metadata(self):
        return {**super()._cache_metadata(), "index_backend": "python"}

    def save_cache(self):
        revision = self._store.revision
        if revision is None:
            return False
        manager = CacheManager(self._snapshots / str(revision))
        metadata = {**self._cache_metadata(), "python_revision": revision}
        saved = manager.is_valid(metadata) or manager.save(
            self.symbol_table, self.dependency_graph, self._file_info,
            metadata=metadata,
        )
        if saved:
            self._cache_manager = manager
            self._prune_snapshots(revision)
        return saved

    def _prune_snapshots(self, revision):
        snapshots = self._snapshots.resolve()
        try:
            for entry in snapshots.iterdir():
                if (entry.name.isascii() and entry.name.isdecimal() and int(entry.name) < revision - 1
                        and entry.is_dir() and entry.resolve() == entry):
                    CacheManager(entry).clear()
                    entry.rmdir()
        except OSError:
            report_suppressed_exception("prune old Context Engine snapshots")

    def load_cache(self):
        with self._update_lock:
            if not self._store.database.is_file():
                return False
            try:
                state = self._store.request("state")
                revision = state["revision"]
                directory = self._snapshots / str(revision)
                if not revision or state["root"] != self._store.identity or not directory.is_dir():
                    return False
                manager = CacheManager(directory)
                cached = manager.load(expected_metadata={**self._cache_metadata(), "python_revision": revision})
                if cached is None or not self._store.attach(revision):
                    return False
                self._restore_cached_index(cached)
                self._cache_manager = manager
                self._reset_content_frequency_cache()
                return True
            except ContextStorageError:
                report_suppressed_exception("validate Python Context Engine index revision")
                return False

    def get_index_status(self):
        return {**super().get_index_status(), "backend": "python", "revision": self._store.revision}

    def _scan(self, *, incremental):
        extensions = self.SUPPORTED_EXTENSIONS | self.GAME_ASSET_EXTENSIONS | self.GAME_CONFIG_EXTENSIONS
        files, removed = self._store.scan(self._ignore_patterns, extensions, incremental=incremental)
        self._scan_entries = {self.project_root / file["path"]: file for file in files}
        return [self.project_root / path for path in removed]

    def scan_files(self, progress_callback=None):
        self._scan(incremental=False)
        files = []
        large = []
        for path, entry in self._scan_entries.items():
            if entry["size"] > self.config.max_file_size_kb * 1024:
                large.append(path)
                self._large_files.add(str(path))
            else:
                files.append(path)
        files.extend(large)
        self._emit_progress(
            progress_callback, stage="scan", files_scanned=len(files), completed=len(files),
            message=f"Scan complete: {len(files)} candidate files",
        )
        return files

    def _record_index_document(self, path, result, info):
        if info is not None and info.mtime_ns is not None:
            size, modified_ns = info.size, info.mtime_ns
        elif path in self._scan_entries:
            entry = self._scan_entries[path]
            size, modified_ns = entry["size"], entry["modified_ns"]
        else:
            try:
                stat = path.stat()
            except FileNotFoundError:
                return False
            size, modified_ns = stat.st_size, stat.st_mtime_ns
        body = getattr(info, "_content_search_body", None)
        self._store.document(path, size, modified_ns, body, result.symbols if result is not None else ())
        return True

    def _begin_content_index_rebuild(self):
        self._store.begin(replace=True, expected_revision=self._full_scan_revision)

    def _finish_content_index_rebuild(self):
        self._store.commit()
        self._reset_content_frequency_cache()
        return True

    def _abort_content_index_rebuild(self):
        self._store.rollback()

    def _failed_update(self, result, error):
        try:
            self._store.rollback()
        except ContextStorageError:
            report_suppressed_exception("roll back Python Context Engine index")
        result.fatal_errors.append(str(error))
        result.errors.append(str(error))
        return result

    def full_index(self, show_progress=True, progress_callback=None):
        with self._update_lock:
            before_large = self._large_files.copy()
            started = time.perf_counter()
            try:
                self._full_scan_revision = self._store.request("state")["revision"]
                return super().full_index(show_progress, progress_callback)
            except (ContextStorageError, OSError) as error:
                result = self._failed_update(IndexResult(), error)
                result.total_time_ms = (time.perf_counter() - started) * 1000
                self._last_index_result = result
                self._large_files = before_large
                self._emit_progress(progress_callback, stage="complete", message="Indexing failed")
                return result
            finally:
                self._scan_entries.clear()

    def incremental_index(self, changed_files=None):
        with self._update_lock:
            try:
                current = self._store.request("state")["revision"]
            except ContextStorageError as error:
                result = self._failed_update(IndexResult(), error)
                self._last_index_result = result
                return result
            if self._store.revision != current and not self.load_cache():
                return self.full_index(show_progress=False)
            return self._refresh_index(changed_files)

    def _refresh_index(self, changed_files):
        started = time.perf_counter()
        self._index_progress = IndexProgress(stage="incremental", message="Checking for changes")
        result = IndexResult()
        removed = []
        parsed = []
        try:
            if changed_files is None:
                removed = self._scan(incremental=True)
                changed_files = list(self._scan_entries)
            else:
                changed_files = list(dict.fromkeys(Path(path).resolve() for path in changed_files))
            result.files_scanned = len(changed_files) + len(removed)
            if result.files_scanned:
                self._store.begin(replace=False, expected_revision=self._store.revision)
                for path in removed:
                    self._store.remove(path)
                for path in changed_files:
                    path.relative_to(self.project_root)
                    parse_result, info = self._parse_file_safe(path)
                    if parse_result is None:
                        result.files_skipped += 1
                        if not self._record_index_document(path, None, None):
                            self._store.remove(path)
                    elif not parse_result.success:
                        result.files_failed += 1
                        result.errors.extend(parse_result.errors)
                        self._record_index_document(path, None, None)
                    else:
                        result.files_parsed += 1
                        result.symbols_extracted += parse_result.symbol_count
                        result.dependencies_extracted += len(parse_result.dependencies)
                        self._record_index_document(path, parse_result, info)
                        parsed.append((path, parse_result, info))
                self._store.commit()
                self._reset_content_frequency_cache()
                self._publish_incremental(removed, changed_files, parsed)
                if not self.save_cache():
                    result.warnings.append("Failed to persist incremental cache update")
        except (ContextStorageError, OSError, ValueError) as error:
            self._failed_update(result, error)
        finally:
            self._scan_entries.clear()
        result.total_time_ms = (time.perf_counter() - started) * 1000
        result.parse_time_ms = result.total_time_ms
        self._last_index_result = result
        self._emit_progress(
            None, stage="complete", total=result.files_scanned, completed=result.files_scanned,
            message="index finished" if result.success else "Indexing failed",
            files_scanned=result.files_scanned, files_parsed=result.files_parsed,
            files_failed=result.files_failed, files_skipped=result.files_skipped,
        )
        return result

    def _publish_incremental(self, removed, updated, parsed):
        with self._index_lock:
            for path in [*removed, *updated]:
                key = str(path)
                self.symbol_table.remove_file(key)
                self.dependency_graph.remove_file(key)
                self._file_info.pop(key, None)
                self._large_files.discard(key)
            for path, result, info in parsed:
                self._apply_parse_result(
                    self.symbol_table, self.dependency_graph, self._file_info,
                    path, result, info, remove_existing=False, record_content=False,
                )
            for path, entry in self._scan_entries.items():
                if entry["size"] > self.config.max_file_size_kb * 1024:
                    self._large_files.add(str(path))
            self.dependency_graph.resolve_targets(self.symbol_table)
            self.generation += 1

    def _search(self, weighted_terms, limit, *, chunks):
        weights = [(str(term or "").strip(), float(weight or 0.0)) for term, weight in weighted_terms if str(term or "").strip()]
        if not weights:
            return None
        try:
            return self._store.hits(weights, limit, chunks=chunks)
        except ContextStorageError:
            report_suppressed_exception("query Python Context Engine search index")
            return None

    def search_content_terms(self, weighted_terms, *, limit=80):
        return self._search(weighted_terms, int(limit or 80), chunks=False)

    def search_code_chunks(self, weighted_terms, *, limit=120):
        return self._search(weighted_terms, int(limit or 120), chunks=True)

    def content_document_frequencies(self, terms):
        normalized = list(dict.fromkeys(str(term or "").strip().lower() for term in terms))
        normalized = [term for term in normalized if term]
        if not normalized:
            return {}
        if not self._store.revision:
            return None
        missing = [term for term in normalized if term not in self._content_df_cache]
        if missing:
            try:
                response = self._store.request("frequencies", terms=missing, expected_revision=self._store.revision)
            except ContextStorageError:
                report_suppressed_exception("read Python Context Engine document frequencies")
                return None
            self._content_document_total = response["total"]
            self._content_df_cache.update(response["terms"])
        return {term: self._content_df_cache.get(term, 0) for term in normalized}

    def content_document_total(self):
        if self._content_document_total is None and self._store.revision:
            try:
                self._content_document_total = self._store.request("total", expected_revision=self._store.revision)
            except ContextStorageError:
                report_suppressed_exception("read Python Context Engine document total")
        return self._content_document_total or 0
