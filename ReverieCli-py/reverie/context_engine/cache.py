"""
Cache Manager - Persistent storage for Context Engine data

Handles serialization and loading of:
- Symbol table
- Dependency graph
- File tracking information

Uses JSON format for human readability and easy debugging.
Optimized for large codebases with efficient incremental updates.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import json
import time
import gzip
import os
import logging
import tempfile
import threading
from dataclasses import asdict

from .symbol_table import SymbolTable
from .dependency_graph import DependencyGraph
from ..diagnostics import report_suppressed_exception


logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages persistent caching of Context Engine data.
    
    Cache structure:
    .reverie/context_cache/
    ├── index.json          # Metadata and version info
    ├── symbols.json.gz     # Compressed symbol table
    ├── dependencies.json.gz # Compressed dependency graph
    └── files.json          # File tracking info
    """
    
    CACHE_VERSION = "1.5.0"
    COMPRESSION_LEVEL = 3
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._io_lock = threading.RLock()
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def index_path(self) -> Path:
        return self.cache_dir / 'index.json'
    
    @property
    def symbols_path(self) -> Path:
        return self.cache_dir / 'symbols.json.gz'
    
    @property
    def dependencies_path(self) -> Path:
        return self.cache_dir / 'dependencies.json.gz'
    
    @property
    def files_path(self) -> Path:
        return self.cache_dir / 'files.json'

    @property
    def content_search_path(self) -> Path:
        return self.cache_dir / 'content-search.sqlite3'
    
    def save(
        self,
        symbol_table: SymbolTable,
        dependency_graph: DependencyGraph,
        file_info: Dict[str, Any],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Save all context engine data to cache.
        
        Returns True if successful.
        """
        try:
            started_at = time.perf_counter()
            with self._io_lock:
                # A cache is valid only after the final index manifest is replaced.
                self.index_path.unlink(missing_ok=True)

                # Save symbol table (compressed)
                symbol_data = symbol_table.to_dict()
                self._save_compressed(self.symbols_path, symbol_data)

                # Save dependency graph (compressed)
                dep_data = dependency_graph.to_dict()
                self._save_compressed(self.dependencies_path, dep_data)

                # Save file info
                files_data = {}
                for path, info in file_info.items():
                    try:
                        files_data[path] = asdict(info)
                    except TypeError:
                        files_data[path] = {
                            'path': getattr(info, 'path', path),
                            'mtime': getattr(info, 'mtime', 0.0),
                            'size': getattr(info, 'size', 0),
                            'content_hash': getattr(info, 'content_hash', ''),
                        }
                self._atomic_write_json(self.files_path, files_data)

                # Publish the manifest last so an interrupted save is never valid.
                index_data = {
                    'version': self.CACHE_VERSION,
                    'saved_at': time.time(),
                    'symbol_count': len(symbol_table),
                    'dependency_count': len(dependency_graph),
                    'file_count': len(file_info),
                    'metadata': metadata or {},
                    'save_time_ms': round((time.perf_counter() - started_at) * 1000.0, 2),
                }
                self._atomic_write_json(self.index_path, index_data)
            return True
            
        except Exception:
            report_suppressed_exception("save Context Engine cache", logger=logger, level=logging.WARNING)
            return False
    
    def load(self, expected_metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Load all context engine data from cache.
        
        Returns dict with:
        - symbol_table: SymbolTable
        - dependency_graph: DependencyGraph
        - file_info: Dict
        - metadata: Dict
        
        Returns None if cache is invalid or doesn't exist.
        """
        try:
            started_at = time.perf_counter()
            with self._io_lock:
                # Check index
                if not self.index_path.exists():
                    return None

                with open(self.index_path, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)

                # Reject incompatible or stale caches before inflating large payloads.
                if index_data.get('version') != self.CACHE_VERSION:
                    return None
                metadata = index_data.get('metadata', {})
                if expected_metadata and any(metadata.get(key) != value for key, value in expected_metadata.items()):
                    return None

                symbol_data = self._load_compressed(self.symbols_path)
                if symbol_data is None:
                    return None
                symbol_table = SymbolTable.from_dict(symbol_data)

                dep_data = self._load_compressed(self.dependencies_path)
                if dep_data is None:
                    return None
                dependency_graph = DependencyGraph.from_dict(dep_data)

                if not self.files_path.exists():
                    return None
                with open(self.files_path, 'r', encoding='utf-8') as f:
                    files_data = json.load(f)
            
            # Convert to FileInfo objects (importing here to avoid circular imports)
            from .indexer import FileInfo
            file_info = {
                path: FileInfo(
                    path=data['path'],
                    mtime=data['mtime'],
                    size=data['size'],
                    content_hash=data['content_hash'],
                    symbol_count=data.get('symbol_count', 0),
                    language=data.get('language', 'unknown'),
                    line_count=data.get('line_count', 0),
                    imports=data.get('imports', []),
                    import_count=data.get('import_count', 0),
                    symbol_names=data.get('symbol_names', []),
                    top_level_symbols=data.get('top_level_symbols', []),
                    keywords=data.get('keywords', []),
                    tags=data.get('tags', []),
                    dependency_targets=data.get('dependency_targets', []),
                    summary=data.get('summary', ''),
                )
                for path, data in files_data.items()
            }
            
            return {
                'symbol_table': symbol_table,
                'dependency_graph': dependency_graph,
                'file_info': file_info,
                'metadata': index_data.get('metadata', {}),
                'saved_at': index_data.get('saved_at'),
                'load_time_ms': round((time.perf_counter() - started_at) * 1000.0, 2),
            }
            
        except Exception:
            report_suppressed_exception("load Context Engine cache", logger=logger, level=logging.WARNING)
            return None
    
    def is_valid(self, expected_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Check if cache exists and is valid"""
        if not self.index_path.exists():
            return False
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            metadata = index_data.get('metadata', {})
            if index_data.get('version') != self.CACHE_VERSION:
                return False
            return not expected_metadata or all(
                metadata.get(key) == value for key, value in expected_metadata.items()
            )
        except Exception:
            report_suppressed_exception("validate Context Engine cache metadata", logger=logger)
            return False
    
    def clear(self) -> None:
        """Clear all cache files"""
        for path in [self.index_path, self.symbols_path,
                     self.dependencies_path, self.files_path, self.content_search_path]:
            if path.exists():
                path.unlink()
    
    def get_cache_info(self) -> Optional[Dict]:
        """Get cache metadata without loading full data"""
        if not self.index_path.exists():
            return None
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            report_suppressed_exception("read Context Engine cache metadata", logger=logger)
            return None

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        """Write JSON next to its destination and atomically replace it."""
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.cache_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
                json.dump(data, stream, ensure_ascii=False, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    
    def _save_compressed(self, path: Path, data: Dict) -> None:
        """Save data as compressed JSON"""
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.cache_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'wb') as raw:
                with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=self.COMPRESSION_LEVEL, mtime=0) as compressed:
                    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                    compressed.write(encoded)
                raw.flush()
                os.fsync(raw.fileno())
            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    
    def _load_compressed(self, path: Path) -> Optional[Dict]:
        """Load compressed JSON data"""
        if not path.exists():
            return None
        
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as stream:
                return json.load(stream)
        except Exception:
            report_suppressed_exception(f"load compressed Context Engine cache file {path.name}", logger=logger)
            return None
