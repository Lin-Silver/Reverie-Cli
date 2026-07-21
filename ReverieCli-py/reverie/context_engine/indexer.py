"""
Codebase Indexer - Scans and indexes the entire project

The indexer is responsible for:
1. Scanning project files (respecting .gitignore)
2. Parsing files using appropriate language parsers
3. Building the symbol table and dependency graph
4. Managing incremental updates

Optimized for large codebases (>5MB source code).
"""

from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Callable, Any, Iterable
from dataclasses import dataclass, field
import time
import os
import fnmatch
import hashlib
import json
import math
import re
import sqlite3
import threading
import queue
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathspec import GitIgnoreSpec

from .symbol_table import Symbol, SymbolTable
from .dependency_graph import DependencyGraph, Dependency, DependencyType
from .parsers.base import BaseParser, ParseResult
from .parsers.document_parser import DocumentParser
from .parsers.python_parser import PythonParser
from .parsers.treesitter_parser import TreeSitterParser, SUPPORTED_LANGUAGES
from .parsers.simple_script_parser import SimpleScriptParser
from .parsers.lua_parser import LuaParser
from .parsers.gdscript_parser import GDScriptParser
from .parsers.config_parser import ConfigParser
from .cache import CacheManager
from ..config import get_project_data_dir
from ..diagnostics import report_suppressed_exception


@dataclass
class IndexProgress:
    """Live progress snapshot for indexing operations."""
    stage: str = "idle"
    message: str = ""
    completed: int = 0
    total: int = 0
    current_file: str = ""
    files_scanned: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    chunk_index: int = 0
    chunk_total: int = 0
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, max(0.0, (self.completed / self.total) * 100.0))

    @property
    def display_percent(self) -> float:
        """A UI-friendly progress percentage that only reaches 100% on completion."""
        if self.stage == "complete":
            return 100.0
        return min(99.0, max(0.0, self.percent))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stage': self.stage,
            'message': self.message,
            'completed': self.completed,
            'total': self.total,
            'percent': self.percent,
            'display_percent': self.display_percent,
            'current_file': self.current_file,
            'files_scanned': self.files_scanned,
            'files_parsed': self.files_parsed,
            'files_failed': self.files_failed,
            'files_skipped': self.files_skipped,
            'chunk_index': self.chunk_index,
            'chunk_total': self.chunk_total,
            'started_at': self.started_at,
            'updated_at': self.updated_at,
            'elapsed_ms': max(0.0, (self.updated_at - self.started_at) * 1000.0),
        }


@dataclass
class IndexResult:
    """Result of indexing operation"""
    files_scanned: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    files_skipped: int = 0  # Newly added: skipped files
    symbols_extracted: int = 0
    dependencies_extracted: int = 0
    parse_time_ms: float = 0.0
    total_time_ms: float = 0.0
    total_bytes: int = 0  # Newly added: total bytes
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)  # Newly added: warnings
    fatal_errors: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return len(self.fatal_errors) == 0
    
    @property
    def total_mb(self) -> float:
        return self.total_bytes / (1024 * 1024)


@dataclass
class FileInfo:
    """Information about a file for caching"""
    path: str
    mtime: float
    size: int
    content_hash: str
    symbol_count: int = 0  # Newly added: symbol count
    language: str = "unknown"
    line_count: int = 0
    imports: List[Dict[str, Any]] = field(default_factory=list)
    import_count: int = 0
    symbol_names: List[str] = field(default_factory=list)
    top_level_symbols: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    dependency_targets: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class IndexConfig:
    """Configuration for indexing behavior"""
    # Large file handling
    max_file_size_kb: int = 20480  # 20MB single-file limit (Increased from 1MB)
    max_file_size_for_full_parse_kb: int = 5120  # 5MB threshold uses lightweight parse (Increased from 500KB)
    
    # Parallel processing
    max_workers: int = 8  # Increased default worker count
    chunk_size: int = 50  # Chunk size: files processed per batch
    
    # Memory optimizations
    lazy_load_source: bool = True  # Lazy-load source
    batch_commit_threshold: int = 100  # Batch commit threshold
    
    # Progress callback
    progress_callback: Optional[Callable[..., None]] = None  # Supports IndexProgress snapshots or legacy tuple callbacks


class CodebaseIndexer:
    """
    High-performance codebase indexer optimized for large codebases (>5MB).
    
    Features:
    - Multi-threaded file parsing with configurable workers
    - Chunked indexing for memory efficiency
    - Lazy loading for symbol source code
    - Incremental updates based on file modification time
    - Content hash verification for accuracy
    - .gitignore respect
    - Large file detection and handling
    - Progress reporting
    """
    
    # Default patterns to ignore
    DEFAULT_IGNORE_PATTERNS = [
        '.git', '.git/**',
        '.reverie', '.reverie/**',
        '.kernel', '**/.kernel/**',
        '.runtime', '**/.runtime/**',
        '.cache', '**/.cache/**',
        '.vite-cache', '**/.vite-cache/**',
        '__pycache__', '**/__pycache__/**',
        'node_modules', '**/node_modules/**',
        '.venv', '**/.venv/**',
        'venv', '**/venv/**',
        '.env', '**/.env/**',
        'env', '**/env/**',
        'dist', '**/dist/**',
        'build', '**/build/**',
        'release', '**/release/**',
        'references', 'references/**', '**/references/**',
        'comfy', 'comfy/**', '**/comfy/**',
        '*.egg-info', '*.egg-info/**', '**/*.egg-info/**',
        'target', '**/target/**',  # Rust
        '.tox', '**/.tox/**',
        '.pytest_cache', '**/.pytest_cache/**',
        '.mypy_cache', '**/.mypy_cache/**',
        '*.pyc', '*.pyo', '*.pyd',
        '*.so', '*.dll', '*.dylib',
        '*.exe', '*.bin', '*.obj', '*.o',
        '*.min.js', '*.min.css',
        '*.map',
        '.DS_Store', 'Thumbs.db',
        '*.log',
        '.idea', '.vscode',
        # More common ignore patterns
        'vendor', '**/vendor/**',
        '.next', '**/.next/**',
        '.nuxt', '**/.nuxt/**',
        'coverage', '**/coverage/**',
        '.coverage', '**/.coverage/**',
        '*.lock', '**/package-lock.json', '**/yarn.lock',
        '*.wasm', '*.woff', '*.woff2', '*.ttf', '*.eot',
        '*.png', '*.jpg', '*.jpeg', '*.gif', '*.ico', '*.svg',
        '*.mp3', '*.mp4', '*.avi', '*.mov',
        '*.pdf', '*.doc', '*.docx', '*.xls', '*.xlsx',
        '*.zip', '*.tar', '*.gz', '*.rar', '*.7z',
        '*.db', '*.sqlite', '*.sqlite3',
        # Large vocabulary/tokenizer files (ML models)
        '**/vocab.json', '**/tokenizer.json', '**/merges.txt',
        '**/sentencepiece.bpe.model', '**/tokenizer.model',
    ]
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.py', '.pyw', '.pyi',  # Python
        '.js', '.mjs', '.cjs', '.jsx',  # JavaScript
        '.ts', '.tsx',  # TypeScript
        '.c', '.h',  # C
        '.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx',  # C++
        '.cs',  # C#
        '.rs',  # Rust
        '.go',  # Go
        '.java',  # Java
        '.zig',  # Zig
        '.html', '.htm',  # HTML
        '.css', '.scss', '.sass', '.less',  # CSS
        '.lua', '.gd',  # Love2D (Lua) and Godot (GDScript)
        '.md', '.mdx', '.rst', '.txt',  # Docs and repository knowledge
    }
    
    # Game asset file extensions
    GAME_ASSET_EXTENSIONS = {
        # Images
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tga', '.webp', '.svg',
        # Audio
        '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a',
        # 3D Models
        '.obj', '.fbx', '.gltf', '.glb', '.dae', '.blend',
        # Animations
        '.anim', '.animation', '.anm',
        # Fonts
        '.ttf', '.otf', '.woff', '.woff2',
        # Shaders
        '.shader', '.glsl', '.hlsl', '.vert', '.frag',
        # Game-specific
        '.tscn', '.tres',  # Godot scenes and resources
        '.tmx', '.tsx',  # Tiled map editor
    }
    
    # Game configuration file extensions
    GAME_CONFIG_EXTENSIONS = {
        '.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.cfg', '.conf'
    }
    
    def __init__(
        self,
        project_root: Path,
        cache_dir: Optional[Path] = None,
        config: Optional[IndexConfig] = None
    ):
        self.project_root = Path(project_root).resolve()
        self.cache_dir = cache_dir or (get_project_data_dir(self.project_root) / 'context_cache')
        self.config = config or IndexConfig()
        self._cache_manager = CacheManager(self.cache_dir)
        self._content_index_connection: Optional[sqlite3.Connection] = None
        self._content_index_temporary_path: Optional[Path] = None
        self._content_document_total: Optional[int] = None
        self._content_df_cache: Dict[str, int] = {}
        
        # Core data structures
        self.symbol_table = SymbolTable()
        self.dependency_graph = DependencyGraph()
        
        # File tracking for incremental updates
        self._file_info: Dict[str, FileInfo] = {}
        
        # File ignore patterns (from .gitignore + defaults)
        self._ignore_patterns = list(self.DEFAULT_IGNORE_PATTERNS)
        self._load_gitignore()
        self._load_reverie_ignore()
        self._negated_ignore_patterns = [
            line[1:].strip().lstrip('/')
            for line in self._ignore_patterns
            if line.lstrip().startswith('!') and not line.lstrip().startswith(r'\!')
        ]
        try:
            self._ignore_spec = GitIgnoreSpec.from_lines(self._ignore_patterns)
        except Exception:
            report_suppressed_exception("compile project ignore rules")
            self._ignore_spec = GitIgnoreSpec.from_lines(self.DEFAULT_IGNORE_PATTERNS)
        self._ignore_fingerprint = hashlib.sha256(
            "\n".join(self._ignore_patterns).encode("utf-8", errors="replace")
        ).hexdigest()
        
        # Initialize parsers
        self._parsers: List[BaseParser] = [
            PythonParser(self.project_root),
            LuaParser(self.project_root),
            GDScriptParser(self.project_root),
            ConfigParser(self.project_root),
            DocumentParser(self.project_root),
            TreeSitterParser(self.project_root),
            SimpleScriptParser(self.project_root),
        ]
        
        # Large file tracking
        self._large_files: Set[str] = set()
        
        # Index lock (thread safety)
        self._index_lock = threading.Lock()
        self._last_index_result: Optional[IndexResult] = None
        self._index_progress = IndexProgress()
    
    def _load_gitignore(self) -> None:
        """Load patterns from .gitignore if it exists"""
        self._load_ignore_file(self.project_root / '.gitignore', "read project gitignore rules")
    
    def _load_reverie_ignore(self) -> None:
        """Load patterns from .reverieignore if it exists"""
        self._load_ignore_file(self.project_root / '.reverieignore', "read Reverie ignore rules")

    def _load_ignore_file(self, path: Path, operation: str) -> None:
        """Append an ignore file verbatim so Git wildmatch ordering is preserved."""
        if not path.exists():
            return
        try:
            self._ignore_patterns.extend(path.read_text(encoding='utf-8').splitlines())
        except Exception:
            report_suppressed_exception(operation)

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored"""
        try:
            rel_path = path.relative_to(self.project_root)
        except ValueError:
            return True

        relative = rel_path.as_posix()
        try:
            if path.is_dir() and not relative.endswith('/'):
                relative += '/'
        except OSError:
            pass
        return bool(self._ignore_spec.match_file(relative))

    def _should_descend_ignored_directory(self, path: Path) -> bool:
        """Keep walking an ignored directory when a later negation may re-include a child."""
        try:
            relative = path.relative_to(self.project_root).as_posix().strip('/')
        except ValueError:
            return False
        prefix = f"{relative}/"
        for pattern in self._negated_ignore_patterns:
            normalized = pattern.replace('\\', '/').strip('/')
            fixed_prefix = normalized.split('*', 1)[0].split('?', 1)[0].rstrip('/')
            if fixed_prefix == relative or fixed_prefix.startswith(prefix):
                return True
        return False

    def _cache_metadata(self) -> Dict[str, Any]:
        """Describe inputs that make an on-disk index safe to reuse."""
        return {
            'project_root': os.path.normcase(str(self.project_root)),
            'ignore_fingerprint': self._ignore_fingerprint,
            'max_file_size_kb': self.config.max_file_size_kb,
            'max_full_parse_kb': self.config.max_file_size_for_full_parse_kb,
        }
    
    def _is_supported_file(self, path: Path) -> bool:
        """Check if file extension is supported"""
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def _is_game_asset(self, path: Path) -> bool:
        """Check if file is a game asset"""
        return path.suffix.lower() in self.GAME_ASSET_EXTENSIONS
    
    def _is_game_config(self, path: Path) -> bool:
        """Check if file is a game configuration file"""
        return path.suffix.lower() in self.GAME_CONFIG_EXTENSIONS
    
    def _get_asset_type(self, path: Path) -> Optional[str]:
        """Get the type of game asset"""
        ext = path.suffix.lower()
        
        # Image assets
        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tga', '.webp', '.svg'}:
            return 'image'
        
        # Audio assets
        if ext in {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}:
            return 'audio'
        
        # 3D model assets
        if ext in {'.obj', '.fbx', '.gltf', '.glb', '.dae', '.blend'}:
            return 'model'
        
        # Animation assets
        if ext in {'.anim', '.animation', '.anm'}:
            return 'animation'
        
        # Font assets
        if ext in {'.ttf', '.otf', '.woff', '.woff2'}:
            return 'font'
        
        # Shader assets
        if ext in {'.shader', '.glsl', '.hlsl', '.vert', '.frag'}:
            return 'shader'
        
        # Game-specific assets
        if ext in {'.tscn', '.tres'}:
            return 'godot_resource'
        if ext in {'.tmx', '.tsx'}:
            return 'tilemap'
        
        return None
    
    def _is_large_file(self, path: Path) -> bool:
        """Check if file exceeds size limits"""
        try:
            size_kb = path.stat().st_size / 1024
            return size_kb > self.config.max_file_size_kb
        except Exception:
            return False
    
    def _is_binary_file(self, path: Path) -> bool:
        """Quick check if file is binary"""
        try:
            # First check extension
            if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp',
                                     '.mp3', '.mp4', '.avi', '.mov', '.wav',
                                     '.zip', '.tar', '.gz', '.rar', '.7z', '.pdf',
                                     '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o',
                                     '.pyc', '.pyo', '.pyd', '.db', '.sqlite', '.sqlite3'}:
                return True

            with open(path, 'rb') as f:
                chunk = f.read(8192)
                if not chunk:
                    return False
                # Check for null bytes (common in binary files)
                if b'\x00' in chunk:
                    # Allow some null bytes in UTF-16/32 encodings if BOM matches, but simple null check is usually good enough for code
                    # Text files usually don't have null bytes
                    return True
                
                # Check if mostly non-text characters
                # Text chars: printable ASCII (32-126) + tab (9) + newline (10) + carriage return (13) + extended ascii/utf8
                text_chars = set(range(32, 127)) | {9, 10, 13}
                # Also allow UTF-8 common bytes (roughly) - this logic is simplified
                
                non_text = sum(1 for b in chunk if b not in text_chars)
                # If more than 30% non-ASCII printable, treat as binary (conservative) 
                # This might flag some legitimate UTF-8 files as binary if they have LOTS of non-ascii, 
                # but for codebases it's usually safe. 
                return non_text / len(chunk) > 0.3
        except Exception:
            return True
    
    def _get_parser(self, file_path: Path) -> Optional[BaseParser]:
        """Get appropriate parser for a file"""
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser
        return None
    
    def _calculate_file_hash(self, content: str) -> str:
        """Calculate hash of file content"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _snapshot_progress(self) -> IndexProgress:
        """Return a copy of the current indexing progress state."""
        state = self._index_progress
        return IndexProgress(
            stage=state.stage,
            message=state.message,
            completed=state.completed,
            total=state.total,
            current_file=state.current_file,
            files_scanned=state.files_scanned,
            files_parsed=state.files_parsed,
            files_failed=state.files_failed,
            files_skipped=state.files_skipped,
            chunk_index=state.chunk_index,
            chunk_total=state.chunk_total,
            started_at=state.started_at,
            updated_at=state.updated_at,
        )

    def _emit_progress(
        self,
        callback: Optional[Callable[..., None]],
        *,
        stage: str,
        completed: Optional[int] = None,
        total: Optional[int] = None,
        message: str = "",
        current_file: str = "",
        files_scanned: Optional[int] = None,
        files_parsed: Optional[int] = None,
        files_failed: Optional[int] = None,
        files_skipped: Optional[int] = None,
        chunk_index: Optional[int] = None,
        chunk_total: Optional[int] = None,
    ) -> IndexProgress:
        """Update and optionally publish a live indexing progress snapshot."""
        now = time.time()
        state = self._index_progress
        state.stage = stage
        if completed is not None:
            state.completed = max(0, int(completed))
        if total is not None:
            state.total = max(0, int(total))
        if message:
            state.message = str(message)
        if current_file:
            state.current_file = str(current_file)
        if files_scanned is not None:
            state.files_scanned = max(0, int(files_scanned))
        if files_parsed is not None:
            state.files_parsed = max(0, int(files_parsed))
        if files_failed is not None:
            state.files_failed = max(0, int(files_failed))
        if files_skipped is not None:
            state.files_skipped = max(0, int(files_skipped))
        if chunk_index is not None:
            state.chunk_index = max(0, int(chunk_index))
        if chunk_total is not None:
            state.chunk_total = max(0, int(chunk_total))
        state.updated_at = now

        snapshot = self._snapshot_progress()
        self._index_progress = snapshot

        if not callback:
            return snapshot

        try:
            callback(snapshot)
        except TypeError:
            try:
                callback(snapshot.completed, snapshot.total, snapshot.message)
            except Exception as exc:
                logger.debug("Legacy progress callback rejected snapshot: %s", exc)
        except Exception as exc:
            logger.warning("Progress callback failed: %s", exc)

        return snapshot

    def _apply_parse_result(
        self,
        symbol_table: SymbolTable,
        dependency_graph: DependencyGraph,
        file_info_store: Dict[str, FileInfo],
        file_path: Path,
        parse_result: ParseResult,
        file_info: Optional[FileInfo],
        *,
        remove_existing: bool = True,
    ) -> None:
        """Merge a parsed file into the provided index state."""
        file_key = str(file_path)
        if remove_existing:
            symbol_table.remove_file(file_key)
            dependency_graph.remove_file(file_key)

        for symbol in parse_result.symbols:
            symbol_table.add_symbol(symbol)
        for dep in parse_result.dependencies:
            dependency_graph.add_dependency(dep)
        for symbol in parse_result.symbols:
            if not symbol.parent or symbol.parent == symbol.qualified_name:
                continue
            dependency_graph.add_simple(
                symbol.parent,
                symbol.qualified_name,
                DependencyType.CONTAINS,
                file_path=file_key,
                line=max(1, int(symbol.start_line or 1)),
                context=symbol.name,
            )

        if file_info:
            file_info.symbol_count = parse_result.symbol_count
            file_info_store[file_key] = file_info
            search_body = getattr(file_info, "_content_search_body", None)
            if search_body is not None:
                if self._content_index_connection is not None:
                    self._upsert_content_index(file_key, search_body, parse_result.symbols)
                delattr(file_info, "_content_search_body")

    @staticmethod
    def _initialize_content_index(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS content_documents "
            "(rowid INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE)"
        )
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS content_search "
            "USING fts5(body, content='', tokenize='porter unicode61')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS chunk_documents ("
            "rowid INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, "
            "symbol TEXT NOT NULL, kind TEXT NOT NULL, start_line INTEGER NOT NULL, "
            "end_line INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS chunk_documents_path_idx ON chunk_documents(path)"
        )
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5("
            "name, signature, documentation, body, content='', tokenize='porter unicode61')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS fts_delete_payloads ("
            "search_table TEXT NOT NULL, rowid INTEGER NOT NULL, delete_payload BLOB NOT NULL, "
            "PRIMARY KEY(search_table, rowid)) WITHOUT ROWID"
        )

    # Delete payloads are stored with a one-byte format marker so small rows
    # (the vast majority: symbol names/signatures) avoid a zlib round trip that
    # costs more CPU than it saves. Only bodies past this threshold compress.
    _FTS_PAYLOAD_RAW = 0
    _FTS_PAYLOAD_ZLIB = 1
    _FTS_PAYLOAD_COMPRESS_THRESHOLD = 512

    @staticmethod
    def _pack_fts_delete_payload(fields: Tuple[str, ...]) -> bytes:
        serialized = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(serialized) >= CodebaseIndexer._FTS_PAYLOAD_COMPRESS_THRESHOLD:
            return bytes((CodebaseIndexer._FTS_PAYLOAD_ZLIB,)) + zlib.compress(serialized, level=1)
        return bytes((CodebaseIndexer._FTS_PAYLOAD_RAW,)) + serialized

    @staticmethod
    def _unpack_fts_delete_payload(payload: Any) -> Tuple[str, ...]:
        blob = bytes(payload)
        if not blob:
            return tuple()
        marker, body = blob[0], blob[1:]
        if marker == CodebaseIndexer._FTS_PAYLOAD_ZLIB:
            serialized = zlib.decompress(body).decode("utf-8")
        elif marker == CodebaseIndexer._FTS_PAYLOAD_RAW:
            serialized = body.decode("utf-8")
        else:
            # Legacy payloads had no marker and were a bare zlib stream.
            serialized = zlib.decompress(blob).decode("utf-8")
        values = json.loads(serialized)
        return tuple(str(value or "") for value in values)

    @staticmethod
    def _delete_fts_rows(
        connection: sqlite3.Connection,
        mapping_table: str,
        search_table: str,
        search_fields: Tuple[str, ...],
        file_path: str,
    ) -> None:
        """Delete live FTS rows before removing their path mappings."""
        rowids = connection.execute(
            f"SELECT mapping.rowid, payload.delete_payload FROM {mapping_table} AS mapping "
            "LEFT JOIN fts_delete_payloads AS payload "
            "ON payload.search_table = ? AND payload.rowid = mapping.rowid "
            "WHERE mapping.path = ?",
            (search_table, str(file_path)),
        ).fetchall()
        field_list = ", ".join(search_fields)
        placeholders = ", ".join("?" for _ in range(len(search_fields) + 2))
        for rowid, payload in rowids:
            if payload is None:
                raise ValueError(f"Missing {search_table} delete payload")
            fields = CodebaseIndexer._unpack_fts_delete_payload(payload)
            if len(fields) != len(search_fields):
                raise ValueError(f"Invalid {search_table} delete payload")
            connection.execute(
                f"INSERT INTO {search_table}({search_table}, rowid, {field_list}) "
                f"VALUES ({placeholders})",
                ("delete", int(rowid), *fields),
            )
        if rowids:
            connection.executemany(
                "DELETE FROM fts_delete_payloads WHERE search_table = ? AND rowid = ?",
                ((search_table, int(rowid)) for rowid, _ in rowids),
            )
        connection.execute(f"DELETE FROM {mapping_table} WHERE path = ?", (str(file_path),))

    def _begin_content_index_rebuild(self) -> None:
        """Build a replaceable full-text index beside the active cache."""
        temporary_path = self._cache_manager.content_search_path.with_suffix(".sqlite3.tmp")
        temporary_path.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary_path)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        self._initialize_content_index(connection)
        connection.execute("BEGIN")
        self._content_index_connection = connection
        self._content_index_temporary_path = temporary_path

    def _finish_content_index_rebuild(self) -> bool:
        connection = self._content_index_connection
        temporary_path = self._content_index_temporary_path
        self._content_index_connection = None
        self._content_index_temporary_path = None
        if connection is None or temporary_path is None:
            return False
        try:
            connection.commit()
            connection.close()
            os.replace(temporary_path, self._cache_manager.content_search_path)
            self._reset_content_frequency_cache()
            return True
        except Exception:
            report_suppressed_exception("publish Context Engine content search index")
            try:
                connection.close()
            except Exception:
                report_suppressed_exception("close failed Context Engine content search index")
            temporary_path.unlink(missing_ok=True)
            return False

    def _begin_content_index_update(self) -> None:
        path = self._cache_manager.content_search_path
        connection = sqlite3.connect(path)
        self._initialize_content_index(connection)
        connection.execute("BEGIN")
        self._content_index_connection = connection

    def _finish_content_index_update(self) -> None:
        connection = self._content_index_connection
        self._content_index_connection = None
        if connection is None:
            return
        try:
            connection.commit()
        except Exception:
            report_suppressed_exception("update Context Engine content search index")
        finally:
            connection.close()
            self._reset_content_frequency_cache()

    def _reset_content_frequency_cache(self) -> None:
        """Drop memoized content document-frequency data after the index changes."""
        self._content_document_total = None
        self._content_df_cache.clear()

    @staticmethod
    def _symbol_search_fields(symbol: Symbol) -> Optional[Tuple[str, str, str, str]]:
        searchable_kinds = {
            "CLASS", "ENUM", "FUNCTION", "INTERFACE", "MACRO", "METHOD", "MODULE",
            "NAMESPACE", "PROPERTY", "STRUCT", "TRAIT", "TYPE_ALIAS",
        }
        kind = str(getattr(getattr(symbol, "kind", None), "name", "") or "")
        if kind not in searchable_kinds:
            return None
        qualified_name = str(symbol.qualified_name or "")
        simple_name = str(symbol.name or "")
        expanded_name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", simple_name).replace("_", " ")
        name = " ".join(part for part in (qualified_name, simple_name, expanded_name, kind.lower()) if part)
        signature = str(symbol.signature or "")[:4096]
        documentation = str(symbol.docstring or "")[:8192]
        body = str(symbol.source_code or "")
        if not any((name, signature, documentation, body)):
            return None
        if len(body) > 49152:
            body = body[:36864] + "\n...\n" + body[-8192:]
        return name, signature, documentation, body

    def _upsert_content_index(
        self,
        file_path: str,
        content: str,
        symbols: Optional[List[Symbol]] = None,
    ) -> None:
        connection = self._content_index_connection
        if connection is None:
            return
        self._delete_fts_rows(
            connection, "content_documents", "content_search", ("body",), str(file_path)
        )
        self._delete_fts_rows(
            connection,
            "chunk_documents",
            "chunk_search",
            ("name", "signature", "documentation", "body"),
            str(file_path),
        )
        cursor = connection.execute(
            "INSERT INTO content_documents(path) VALUES (?)",
            (str(file_path),),
        )
        content_rowid = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO content_search(rowid, body) VALUES (?, ?)",
            (content_rowid, str(content or "")),
        )
        connection.execute(
            "INSERT INTO fts_delete_payloads(search_table, rowid, delete_payload) VALUES (?, ?, ?)",
            (
                "content_search",
                content_rowid,
                self._pack_fts_delete_payload((str(content or ""),)),
            ),
        )
        # Collect chunk rows and insert them in three bulk executemany calls
        # instead of three per-symbol executes. Rowids are assigned explicitly
        # from the current table maximum so chunk_search and its delete payload
        # can reference them without a per-row lastrowid round-trip. This is safe
        # because the content index connection is single-threaded within a
        # transaction, and it turns O(symbols) SQLite round-trips into O(1).
        document_rows: List[Tuple[int, str, str, str, int, int]] = []
        search_rows: List[Tuple[int, str, str, str, str]] = []
        payload_rows: List[Tuple[str, int, bytes]] = []
        next_rowid: Optional[int] = None
        for symbol in list(symbols or [])[:512]:
            fields = self._symbol_search_fields(symbol)
            if fields is None:
                continue
            if next_rowid is None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(rowid), 0) FROM chunk_documents"
                ).fetchone()
                next_rowid = (int(row[0]) if row else 0) + 1
            chunk_rowid = next_rowid
            next_rowid += 1
            document_rows.append(
                (
                    chunk_rowid,
                    str(file_path),
                    str(symbol.qualified_name or symbol.name or ""),
                    str(getattr(getattr(symbol, "kind", None), "name", "") or "UNKNOWN"),
                    max(1, int(symbol.start_line or 1)),
                    max(1, int(symbol.end_line or symbol.start_line or 1)),
                )
            )
            search_rows.append((chunk_rowid, *fields))
            payload_rows.append(
                ("chunk_search", chunk_rowid, self._pack_fts_delete_payload(fields))
            )
        if document_rows:
            connection.executemany(
                "INSERT INTO chunk_documents(rowid, path, symbol, kind, start_line, end_line) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                document_rows,
            )
            connection.executemany(
                "INSERT INTO chunk_search(rowid, name, signature, documentation, body) "
                "VALUES (?, ?, ?, ?, ?)",
                search_rows,
            )
            connection.executemany(
                "INSERT INTO fts_delete_payloads(search_table, rowid, delete_payload) "
                "VALUES (?, ?, ?)",
                payload_rows,
            )

    def _remove_from_content_index(self, file_path: str) -> None:
        if self._content_index_connection is not None:
            self._delete_fts_rows(
                self._content_index_connection,
                "content_documents",
                "content_search",
                ("body",),
                str(file_path),
            )
            self._delete_fts_rows(
                self._content_index_connection,
                "chunk_documents",
                "chunk_search",
                ("name", "signature", "documentation", "body"),
                str(file_path),
            )

    def search_content_terms(
        self,
        weighted_terms: List[Tuple[str, float]],
        *,
        limit: int = 80,
    ) -> Optional[List[Dict[str, Any]]]:
        """Fuse independent weighted full-text matches without rereading workspace files."""
        path = self._cache_manager.content_search_path
        term_weights: Dict[str, float] = {}
        for term, weight in weighted_terms:
            normalized = str(term or "").strip().lower()
            if normalized:
                term_weights[normalized] = max(term_weights.get(normalized, 0.0), float(weight or 0.0))
        terms = sorted(term_weights.items(), key=lambda item: (-item[1], item[0]))[:16]
        if not path.is_file() or not terms:
            return None

        scores: Dict[str, float] = {}
        contributions: Dict[str, Dict[str, float]] = {}
        per_term_limit = max(24, min(96, max(1, int(limit or 80)) * 2))
        try:
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
                for term, weight in terms:
                    query = f'"{term.replace(chr(34), chr(34) * 2)}"'
                    rows = connection.execute(
                        "SELECT content_documents.path, bm25(content_search) AS relevance "
                        "FROM content_search JOIN content_documents "
                        "ON content_documents.rowid = content_search.rowid "
                        "WHERE content_search MATCH ? ORDER BY relevance, "
                        "content_documents.path COLLATE NOCASE, content_documents.rowid LIMIT ?",
                        (query, per_term_limit),
                    ).fetchall()
                    for rank, (file_path, relevance) in enumerate(rows, start=1):
                        # FTS5 returns better BM25 matches as larger negative values.
                        # Log scaling and reciprocal rank keep one repeated term from
                        # overwhelming agreement across several independent terms.
                        bm25_strength = math.log1p(max(0.0, -float(relevance or 0.0)))
                        contribution = float(weight) * bm25_strength / math.sqrt(rank)
                        if contribution <= 0.0:
                            continue
                        file_key = str(file_path)
                        scores[file_key] = scores.get(file_key, 0.0) + contribution
                        contributions.setdefault(file_key, {})[term] = contribution
        except Exception:
            report_suppressed_exception("query Context Engine content search index")
            return None
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].lower()))
        return [
            {
                "file_path": file_path,
                "score": round(score, 4),
                "terms": [
                    term
                    for term, _ in sorted(
                        contributions.get(file_path, {}).items(),
                        key=lambda item: (-item[1], item[0]),
                    )[:6]
                ],
            }
            for file_path, score in ranked[: max(1, int(limit or 80))]
        ]

    def content_document_frequencies(
        self,
        terms: Iterable[str],
    ) -> Optional[Dict[str, int]]:
        """Return true content document frequency per term from the FTS index.

        This uses the same porter/unicode61 tokenizer as content search, so it
        stays consistent with how terms are actually matched at query time and
        correctly counts underscore identifiers (e.g. ``output_transaction``)
        that a metadata-only frequency table would miss. Results are memoized
        per index revision so repeated queries stay cheap.
        """
        path = self._cache_manager.content_search_path
        normalized: List[str] = []
        seen: Set[str] = set()
        for term in terms:
            token = str(term or "").strip().lower()
            if token and token not in seen:
                seen.add(token)
                normalized.append(token)
        if not normalized:
            return {}
        if not path.is_file():
            return None

        cache = self._content_df_cache
        result: Dict[str, int] = {}
        missing = [term for term in normalized if term not in cache]
        if missing:
            try:
                with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
                    if self._content_document_total is None:
                        total_row = connection.execute(
                            "SELECT COUNT(*) FROM content_documents"
                        ).fetchone()
                        self._content_document_total = int(total_row[0]) if total_row else 0
                    for term in missing:
                        # FTS5 MATCH needs a quoted phrase so identifiers with
                        # underscores or punctuation are treated literally.
                        query = f'"{term.replace(chr(34), chr(34) * 2)}"'
                        try:
                            row = connection.execute(
                                "SELECT COUNT(*) FROM content_search WHERE content_search MATCH ?",
                                (query,),
                            ).fetchone()
                        except sqlite3.OperationalError:
                            cache[term] = 0
                            continue
                        cache[term] = int(row[0]) if row else 0
            except Exception:
                report_suppressed_exception("read Context Engine content document frequency")
                return None
        for term in normalized:
            result[term] = cache.get(term, 0)
        return result

    def content_document_total(self) -> int:
        """Return the number of documents in the content search index."""
        if self._content_document_total is not None:
            return self._content_document_total
        path = self._cache_manager.content_search_path
        if not path.is_file():
            return 0
        try:
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT COUNT(*) FROM content_documents").fetchone()
                self._content_document_total = int(row[0]) if row else 0
        except Exception:
            report_suppressed_exception("read Context Engine content document total")
            return 0
        return self._content_document_total

    def search_code_chunks(
        self,
        weighted_terms: List[Tuple[str, float]],
        *,
        limit: int = 120,
    ) -> Optional[List[Dict[str, Any]]]:
        """Search symbol-sized code and documentation chunks with field-aware BM25."""
        path = self._cache_manager.content_search_path
        term_weights: Dict[str, float] = {}
        for term, weight in weighted_terms:
            normalized = str(term or "").strip().lower()
            if normalized:
                term_weights[normalized] = max(term_weights.get(normalized, 0.0), float(weight or 0.0))
        terms = sorted(term_weights.items(), key=lambda item: (-item[1], item[0]))[:18]
        if not path.is_file() or not terms:
            return None

        scores: Dict[int, float] = {}
        metadata: Dict[int, Tuple[str, str, str, int, int]] = {}
        contributions: Dict[int, Dict[str, float]] = {}
        per_term_limit = max(32, min(120, max(1, int(limit or 120)) * 2))
        try:
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
                for term, weight in terms:
                    query = f'"{term.replace(chr(34), chr(34) * 2)}"'
                    rows = connection.execute(
                        "SELECT chunk_documents.rowid, chunk_documents.path, "
                        "chunk_documents.symbol, chunk_documents.kind, "
                        "chunk_documents.start_line, chunk_documents.end_line, "
                        "bm25(chunk_search, 5.5, 3.0, 1.8, 1.0) AS relevance "
                        "FROM chunk_search JOIN chunk_documents "
                        "ON chunk_documents.rowid = chunk_search.rowid "
                        "WHERE chunk_search MATCH ? ORDER BY relevance, "
                        "chunk_documents.path COLLATE NOCASE, chunk_documents.start_line, "
                        "chunk_documents.symbol COLLATE NOCASE, chunk_documents.rowid LIMIT ?",
                        (query, per_term_limit),
                    ).fetchall()
                    for rank, row in enumerate(rows, start=1):
                        rowid, file_path, symbol, kind, start_line, end_line, relevance = row
                        strength = math.log1p(max(0.0, -float(relevance or 0.0)))
                        contribution = float(weight) * strength / math.sqrt(rank)
                        if term in str(symbol or "").lower():
                            contribution *= 1.25
                        if contribution <= 0.0:
                            continue
                        key = int(rowid)
                        scores[key] = scores.get(key, 0.0) + contribution
                        contributions.setdefault(key, {})[term] = contribution
                        metadata[key] = (
                            str(file_path), str(symbol), str(kind), int(start_line), int(end_line)
                        )
        except Exception:
            report_suppressed_exception("query Context Engine code chunk index")
            return None

        ranked = sorted(
            scores.items(),
            key=lambda item: (
                -item[1] * (1.0 + min(0.36, max(0, len(contributions.get(item[0], {})) - 1) * 0.09)),
                metadata[item[0]][0].lower(),
                metadata[item[0]][3],
            ),
        )
        hits: List[Dict[str, Any]] = []
        for rowid, raw_score in ranked[: max(1, int(limit or 120))]:
            file_path, symbol, kind, start_line, end_line = metadata[rowid]
            term_scores = contributions.get(rowid, {})
            score = raw_score * (1.0 + min(0.36, max(0, len(term_scores) - 1) * 0.09))
            hits.append(
                {
                    "file_path": file_path,
                    "symbol": symbol,
                    "kind": kind,
                    "start_line": start_line,
                    "end_line": end_line,
                    "score": round(score, 4),
                    "terms": [
                        term
                        for term, _ in sorted(term_scores.items(), key=lambda item: (-item[1], item[0]))[:8]
                    ],
                }
            )
        return hits

    def _swap_index_state(
        self,
        symbol_table: SymbolTable,
        dependency_graph: DependencyGraph,
        file_info: Dict[str, FileInfo],
        large_files: Set[str],
    ) -> None:
        """Atomically replace the live index state while preserving object identity."""
        with self._index_lock:
            self.symbol_table.replace_with(symbol_table)
            self.dependency_graph.replace_with(dependency_graph)
            self._file_info.clear()
            self._file_info.update(file_info)
            self._large_files.clear()
            self._large_files.update(large_files)

    def _format_index_status_label(self, status: Dict[str, Any]) -> Optional[str]:
        """Condense the live index snapshot into a short UI-friendly label."""
        stage = str(status.get("stage", "") or "").strip().lower()
        if not stage:
            return None

        try:
            percent = float(status.get("percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            percent = 0.0

        try:
            display_percent = float(status.get("display_percent", percent) or percent)
        except (TypeError, ValueError):
            display_percent = percent

        try:
            files_indexed = int(status.get("files_indexed", 0) or 0)
        except (TypeError, ValueError):
            files_indexed = 0

        if stage in {"scan", "parse", "commit", "incremental"}:
            return f"Indexing {display_percent:.0f}%"
        last_result = self._last_index_result
        last_result_success = bool(getattr(last_result, "success", False)) if last_result is not None else False

        if stage == "complete":
            if last_result is not None and last_result_success:
                return "index finished"
            return None
        if stage == "idle" and (files_indexed > 0 or last_result_success):
            return "index finished"
        return None

    def get_index_status(self) -> Dict[str, Any]:
        """Return a live snapshot of the indexer's current state."""
        status = self._index_progress.to_dict()
        status.update(
            {
                'files_indexed': len(self._file_info),
                'symbols_indexed': len(self.symbol_table),
                'dependencies_indexed': len(self.dependency_graph),
                'large_files': len(self._large_files),
            }
        )
        status['display_label'] = self._format_index_status_label(status)
        status['is_active'] = str(status.get('stage', '') or '').lower() in {
            'scan',
            'parse',
            'commit',
            'incremental',
        }
        status['is_finished'] = status['display_label'] == 'index finished'
        if self._last_index_result is not None:
            status['last_result'] = {
                'files_scanned': self._last_index_result.files_scanned,
                'files_parsed': self._last_index_result.files_parsed,
                'files_failed': self._last_index_result.files_failed,
                'files_skipped': self._last_index_result.files_skipped,
                'symbols_extracted': self._last_index_result.symbols_extracted,
                'dependencies_extracted': self._last_index_result.dependencies_extracted,
                'parse_time_ms': self._last_index_result.parse_time_ms,
                'total_time_ms': self._last_index_result.total_time_ms,
                'success': self._last_index_result.success,
                'errors': len(self._last_index_result.errors),
                'warnings': len(self._last_index_result.warnings),
            }
        return status

    def _extract_text_tokens(self, *values: str) -> List[str]:
        """Extract a compact set of retrieval-friendly tokens."""
        import re

        stop_words = {
            'the', 'and', 'for', 'with', 'from', 'into', 'that', 'this', 'these',
            'those', 'your', 'have', 'will', 'would', 'should', 'could', 'their',
            'about', 'where', 'when', 'which', 'while', 'true', 'false', 'none',
            'null', 'then', 'else', 'than', 'return', 'class', 'function', 'module',
            'config', 'value', 'data', 'item', 'items', 'file', 'files',
        }
        tokens: List[str] = []
        seen: Set[str] = set()
        for value in values:
            text = str(value or "")
            for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text):
                parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).replace("_", " ").split()
                for part in parts:
                    token = part.lower().strip()
                    if len(token) < 3 or token in stop_words or token in seen:
                        continue
                    seen.add(token)
                    tokens.append(token)
        return tokens[:48]

    def _infer_file_tags(self, file_path: Path, parse_result: ParseResult) -> List[str]:
        """Infer coarse roles that help task-level retrieval."""
        try:
            path_text = str(file_path.resolve().relative_to(self.project_root)).lower().replace("\\", "/")
        except (OSError, ValueError):
            path_text = file_path.name.lower()
        tags: List[str] = []
        tag_rules = {
            'test': ['test', 'tests', 'spec'],
            'config': ['config', 'settings', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf'],
            'docs': ['docs/', '/doc/', '.md', '.mdx', '.rst', '.txt', 'readme'],
            'api': ['api', 'route', 'routes', 'endpoint', 'handler', 'controller'],
            'service': ['service', 'services', 'provider'],
            'model': ['model', 'models', 'schema', 'entity'],
            'cli': ['cli', 'command', 'commands'],
            'ui': ['ui', 'view', 'views', 'component', 'components', 'page', 'pages'],
            'infra': ['deploy', 'infra', 'terraform', 'docker', 'k8s', 'kubernetes'],
            'engine': ['context_engine', 'engine', 'retriever', 'indexer', 'parser'],
        }
        for tag, patterns in tag_rules.items():
            if any(pattern in path_text for pattern in patterns):
                tags.append(tag)
        language = str(parse_result.language or "").lower()
        if language in {"markdown", "rst", "text"} and 'docs' not in tags:
            tags.append('docs')
        return tags[:8]

    def _build_file_summary(
        self,
        file_path: Path,
        parse_result: ParseResult,
        imports: List[Dict[str, Any]],
        symbols: List[Symbol],
        tags: List[str],
    ) -> str:
        """Create a compact natural-language summary for a file."""
        role = "code file"
        if "docs" in tags:
            role = "documentation"
        elif "config" in tags:
            role = "configuration"
        elif "test" in tags:
            role = "test file"
        elif "api" in tags:
            role = "API surface"
        elif "service" in tags:
            role = "service module"
        elif "engine" in tags:
            role = "engine module"

        symbol_names = [symbol.name for symbol in symbols[:5] if symbol.name]
        import_names: List[str] = []
        for item in imports[:4]:
            if not isinstance(item, dict):
                continue
            import_name = str(item.get('module') or item.get('name') or item.get('path') or "").strip()
            if import_name:
                import_names.append(import_name)

        parts = [f"{role} {file_path.name}"]
        if symbol_names:
            parts.append("defines " + ", ".join(symbol_names))
        if import_names:
            parts.append("depends on " + ", ".join(import_names))
        if tags:
            parts.append("tags: " + ", ".join(tags))
        return ". ".join(parts).strip()

    def _enrich_file_info(
        self,
        file_path: Path,
        content: str,
        parse_result: ParseResult,
        file_info: Optional[FileInfo],
    ) -> Optional[FileInfo]:
        """Populate retrieval-oriented metadata for the file cache."""
        if file_info is None:
            return None

        imports = [item for item in (parse_result.imports or []) if isinstance(item, dict)]
        top_level_symbols = [symbol.qualified_name for symbol in parse_result.symbols[:12]]
        symbol_names = [symbol.name for symbol in parse_result.symbols[:20] if symbol.name]
        dependency_targets = list({
            dep.to_symbol
            for dep in parse_result.dependencies[:40]
            if getattr(dep, "to_symbol", None)
        })[:20]
        tags = self._infer_file_tags(file_path, parse_result)
        try:
            relative_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            relative_path = str(file_path)
        keywords = self._extract_text_tokens(
            relative_path,
            parse_result.language,
            " ".join(symbol_names),
            " ".join(top_level_symbols),
            " ".join(str(item.get('module') or '') for item in imports),
            " ".join(tags),
            content[:3000],
        )
        summary = self._build_file_summary(file_path, parse_result, imports, parse_result.symbols, tags)

        file_info.language = parse_result.language
        file_info.line_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
        file_info.imports = imports[:16]
        file_info.import_count = len(imports)
        file_info.symbol_names = symbol_names
        file_info.top_level_symbols = top_level_symbols
        file_info.keywords = keywords
        file_info.tags = tags
        file_info.dependency_targets = dependency_targets
        file_info.summary = summary[:360]
        if file_info.size <= 1024 * 1024:
            setattr(file_info, "_content_search_body", content)
        return file_info
    
    def scan_files(self, progress_callback: Optional[Callable[..., None]] = None) -> List[Path]:
        """Scan project for all supported files with size filtering."""
        import logging
        logger = logging.getLogger(__name__)
        
        files = []
        large_files = []
        
        logger.info(f"Starting file scan in: {self.project_root}")
        dir_count = 0
        file_count = 0
        self._emit_progress(
            progress_callback,
            stage="scan",
            completed=0,
            total=0,
            message="Scanning workspace files",
        )
        
        try:
            for root, dirs, filenames in os.walk(self.project_root):
                root_path = Path(root)
                dir_count += 1
                
                # Log progress every 100 directories
                if dir_count % 100 == 0:
                    logger.info(f"Scanned {dir_count} directories, found {len(files) + len(large_files)} files so far...")
                    self._emit_progress(
                        progress_callback,
                        stage="scan",
                        completed=file_count,
                        total=0,
                        message=f"Scanning directories ({dir_count} folders)",
                        files_scanned=len(files) + len(large_files),
                    )
                
                # Filter out ignored directories
                original_dir_count = len(dirs)
                dirs[:] = [
                    directory
                    for directory in dirs
                    if (
                        not self._should_ignore(root_path / directory)
                        or self._should_descend_ignored_directory(root_path / directory)
                    )
                ]
                filtered_count = original_dir_count - len(dirs)
                
                if filtered_count > 0:
                    logger.debug(f"Filtered {filtered_count} directories in {root_path}")
                
                for filename in filenames:
                    file_count += 1
                    file_path = root_path / filename
                    
                    # Log progress every 1000 files
                    if file_count % 1000 == 0:
                        logger.info(f"Processed {file_count} files, accepted {len(files) + len(large_files)} files...")
                        self._emit_progress(
                            progress_callback,
                            stage="scan",
                            completed=file_count,
                            total=0,
                            message=f"Scanning files ({file_count} checked)",
                            files_scanned=len(files) + len(large_files),
                        )
                    
                    if self._should_ignore(file_path):
                        continue
                    
                    # Include code files, game assets, and game config files
                    if not (self._is_supported_file(file_path) or 
                           self._is_game_asset(file_path) or 
                           self._is_game_config(file_path)):
                        continue
                    
                    # Track large files separately (but still include them)
                    try:
                        if self._is_large_file(file_path):
                            large_files.append(file_path)
                            self._large_files.add(str(file_path))
                        else:
                            files.append(file_path)
                    except Exception as e:
                        logger.warning(f"Error checking file size for {file_path}: {e}")
                        continue
            
            logger.info(f"File scan complete: {dir_count} directories, {file_count} files checked")
            logger.info(f"Found {len(files)} normal files, {len(large_files)} large files")
            self._emit_progress(
                progress_callback,
                stage="scan",
                completed=file_count,
                total=0,
                message=f"Scan complete: {len(files) + len(large_files)} candidate files",
                files_scanned=len(files) + len(large_files),
            )
            
        except Exception as e:
            logger.error(f"Error during file scan: {e}")
            import traceback
            traceback.print_exc()
            self._emit_progress(
                progress_callback,
                stage="scan",
                completed=file_count,
                total=0,
                message=f"Scan failed after {file_count} files",
                files_scanned=len(files) + len(large_files),
            )
        
        # Append large files at the end (process last)
        files.extend(large_files)
        
        return files
    
    def full_index(
        self,
        show_progress: bool = True,
        progress_callback: Optional[Callable[..., None]] = None
    ) -> IndexResult:
        """
        Perform full indexing of the codebase.
        
        Optimized for large codebases with chunked processing.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        start_time = time.time()
        result = IndexResult()
        callback = (progress_callback or self.config.progress_callback) if show_progress else None

        logger.info("Starting full index...")

        # Keep the previous large-file tracking in case scanning fails.
        previous_large_files = set(self._large_files)
        self._large_files = set()
        self._index_progress = IndexProgress(
            stage="scan",
            message="Scanning workspace files",
            started_at=start_time,
            updated_at=start_time,
        )

        self._emit_progress(
            callback,
            stage="scan",
            completed=0,
            total=0,
            message="Scanning workspace files",
        )

        scan_start = time.time()
        try:
            files = self.scan_files(progress_callback=callback)
            scan_time = time.time() - scan_start
            logger.info("File scan completed in %.2fs, found %d files", scan_time, len(files))
        except Exception as e:
            logger.error("File scan failed: %s", e)
            result.fatal_errors.append(f"File scan failed: {e}")
            result.errors.append(f"File scan failed: {e}")
            self._large_files = previous_large_files
            result.total_time_ms = (time.time() - start_time) * 1000
            self._last_index_result = result
            self._emit_progress(
                callback,
                stage="complete",
                completed=0,
                total=0,
                message="Indexing aborted during scan",
            )
            return result

        result.files_scanned = len(files)

        # Calculate total size.
        logger.info("Calculating total size...")
        for f in files:
            try:
                result.total_bytes += f.stat().st_size
            except Exception:
                report_suppressed_exception("read indexed file size")
        logger.info("Total size: %.2f MB", result.total_bytes / (1024 * 1024))

        # Build the new index off to the side so the live index only changes on commit.
        new_symbol_table = SymbolTable()
        new_dependency_graph = DependencyGraph()
        new_file_info: Dict[str, FileInfo] = {}
        new_large_files = set(self._large_files)

        parse_start = time.time()
        chunk_size = max(1, int(self.config.chunk_size))
        total_chunks = max(1, (len(files) + chunk_size - 1) // chunk_size)
        processed_files = 0

        logger.info(
            "Processing %d files in %d chunks (chunk_size=%d)",
            len(files),
            total_chunks,
            chunk_size,
        )

        self._emit_progress(
            callback,
            stage="parse",
            completed=0,
            total=len(files),
            message="Preparing parser workers",
            files_scanned=len(files),
            files_parsed=0,
            files_failed=0,
            files_skipped=0,
            chunk_index=0,
            chunk_total=total_chunks,
        )

        content_index_started = False
        try:
            self._begin_content_index_rebuild()
            content_index_started = True
        except Exception:
            report_suppressed_exception("initialize Context Engine content search index")

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            for chunk_idx in range(0, len(files), chunk_size):
                chunk = files[chunk_idx:chunk_idx + chunk_size]
                chunk_num = chunk_idx // chunk_size + 1

                logger.info("Processing chunk %d/%d (%d files)...", chunk_num, total_chunks, len(chunk))
                self._emit_progress(
                    callback,
                    stage="parse",
                    completed=processed_files,
                    total=len(files),
                    message=f"Parsing chunk {chunk_num}/{total_chunks}",
                    files_scanned=len(files),
                    files_parsed=result.files_parsed,
                    files_failed=result.files_failed,
                    files_skipped=result.files_skipped,
                    chunk_index=chunk_num,
                    chunk_total=total_chunks,
                )

                futures = {}
                for file_path in chunk:
                    futures[executor.submit(self._parse_file_safe, file_path)] = file_path

                try:
                    for future in as_completed(futures, timeout=300):
                        file_path = futures[future]

                        try:
                            parse_result, file_info = future.result()
                        except Exception as exc:
                            logger.warning("Error parsing file %s: %s", file_path, exc)
                            result.files_failed += 1
                            result.errors.append(f"{file_path}: {exc}")
                            processed_files += 1
                            self._emit_progress(
                                callback,
                                stage="parse",
                                completed=processed_files,
                                total=len(files),
                                message=f"Failed: {Path(file_path).name}",
                                current_file=str(file_path),
                                files_scanned=len(files),
                                files_parsed=result.files_parsed,
                                files_failed=result.files_failed,
                                files_skipped=result.files_skipped,
                                chunk_index=chunk_num,
                                chunk_total=total_chunks,
                            )
                            continue

                        if parse_result is None:
                            result.files_skipped += 1
                            processed_files += 1
                            logger.debug("Skipped: %s", file_path)
                            self._emit_progress(
                                callback,
                                stage="parse",
                                completed=processed_files,
                                total=len(files),
                                message=f"Skipped: {Path(file_path).name}",
                                current_file=str(file_path),
                                files_scanned=len(files),
                                files_parsed=result.files_parsed,
                                files_failed=result.files_failed,
                                files_skipped=result.files_skipped,
                                chunk_index=chunk_num,
                                chunk_total=total_chunks,
                            )
                            continue

                        if parse_result.success:
                            result.files_parsed += 1
                            result.symbols_extracted += parse_result.symbol_count
                            result.dependencies_extracted += len(parse_result.dependencies)
                            self._apply_parse_result(
                                new_symbol_table,
                                new_dependency_graph,
                                new_file_info,
                                file_path,
                                parse_result,
                                file_info,
                                remove_existing=False,
                            )
                            logger.debug(
                                "Parsed %s: %d symbols, %d deps",
                                file_path,
                                parse_result.symbol_count,
                                len(parse_result.dependencies),
                            )
                        else:
                            result.files_failed += 1
                            result.errors.extend(parse_result.errors)
                            logger.warning("Failed: %s", parse_result.errors)

                        processed_files += 1
                        self._emit_progress(
                            callback,
                            stage="parse",
                            completed=processed_files,
                            total=len(files),
                            message=f"Parsed: {Path(file_path).name}",
                            current_file=str(file_path),
                            files_scanned=len(files),
                            files_parsed=result.files_parsed,
                            files_failed=result.files_failed,
                            files_skipped=result.files_skipped,
                            chunk_index=chunk_num,
                            chunk_total=total_chunks,
                        )

                except TimeoutError:
                    logger.error("Chunk %d timed out (300s)", chunk_num)
                    result.fatal_errors.append(f"Chunk {chunk_num} timed out")
                    result.errors.append(f"Chunk {chunk_num} timed out")
                    for future, file_path in futures.items():
                        if not future.done():
                            logger.error("  Stuck on file: %s", file_path)
                            result.errors.append(f"Timeout on: {file_path}")
                except Exception as e:
                    logger.error("Error processing chunk %d: %s", chunk_num, e)
                    result.errors.append(f"Chunk {chunk_num}: {str(e)}")

        if content_index_started and not self._finish_content_index_rebuild():
            result.warnings.append("Failed to persist the content search index")

        new_dependency_graph.resolve_targets(new_symbol_table)

        result.parse_time_ms = (time.time() - parse_start) * 1000
        logger.info("Parsing completed in %.0fms", result.parse_time_ms)

        if new_large_files:
            result.warnings.append(
                f"Found {len(new_large_files)} large file(s) that may have reduced parsing"
            )

        self._emit_progress(
            callback,
            stage="commit",
            completed=result.files_parsed,
            total=max(len(files), 1),
            message="Swapping in the rebuilt index",
            files_scanned=len(files),
            files_parsed=result.files_parsed,
            files_failed=result.files_failed,
            files_skipped=result.files_skipped,
            chunk_index=total_chunks,
            chunk_total=total_chunks,
        )
        self._swap_index_state(new_symbol_table, new_dependency_graph, new_file_info, new_large_files)

        if not self.save_cache():
            result.warnings.append("Failed to persist the rebuilt context cache")

        result.total_time_ms = (time.time() - start_time) * 1000
        self._last_index_result = result

        self._emit_progress(
            callback,
            stage="complete",
            completed=result.files_parsed + result.files_failed + result.files_skipped,
            total=max(len(files), 1),
            message="index finished",
            files_scanned=len(files),
            files_parsed=result.files_parsed,
            files_failed=result.files_failed,
            files_skipped=result.files_skipped,
            chunk_index=total_chunks,
            chunk_total=total_chunks,
        )

        return result
    
    def incremental_index(self, changed_files: Optional[List[Path]] = None) -> IndexResult:
        """
        Perform incremental indexing.
        
        If changed_files is None, detects changes automatically using
        modification times.
        """
        start_time = time.time()
        result = IndexResult()

        if changed_files is None:
            changed_files = self._detect_changes()

        total_files = max(len(changed_files), 1)
        self._index_progress = IndexProgress(
            stage="incremental",
            message="Indexing 0%",
            total=total_files,
            started_at=start_time,
            updated_at=start_time,
        )

        result.files_scanned = len(changed_files)

        parse_start = time.time()

        self._emit_progress(
            None,
            stage="incremental",
            completed=0,
            total=total_files,
            message="Indexing 0%",
            files_scanned=len(changed_files),
            files_parsed=0,
            files_failed=0,
            files_skipped=0,
        )

        content_index_started = False
        try:
            self._begin_content_index_update()
            content_index_started = True
        except Exception:
            report_suppressed_exception("open Context Engine content search update")

        for index, file_path in enumerate(changed_files, start=1):
            file_key = str(file_path)
            try:
                self._remove_from_content_index(file_key)
                # Remove the previous file state before reparsing so stale symbols
                # do not survive a parse error.
                with self._index_lock:
                    self.symbol_table.remove_file(file_key)
                    self.dependency_graph.remove_file(file_key)
                    self._file_info.pop(file_key, None)

                parse_result, file_info = self._parse_file_safe(file_path)

                if parse_result is None:
                    result.files_skipped += 1
                    continue

                if parse_result.success:
                    result.files_parsed += 1
                    result.symbols_extracted += parse_result.symbol_count
                    result.dependencies_extracted += len(parse_result.dependencies)

                    with self._index_lock:
                        self._apply_parse_result(
                            self.symbol_table,
                            self.dependency_graph,
                            self._file_info,
                            file_path,
                            parse_result,
                            file_info,
                            remove_existing=False,
                        )
                else:
                    result.files_failed += 1
                    result.errors.extend(parse_result.errors)

            except Exception as e:
                result.files_failed += 1
                result.errors.append(f"{file_path}: {str(e)}")
            finally:
                percent = (index / total_files) * 100.0
                self._emit_progress(
                    None,
                    stage="incremental",
                    completed=index,
                    total=total_files,
                    message=f"Indexing {percent:.0f}%",
                    current_file=str(file_path),
                    files_scanned=len(changed_files),
                    files_parsed=result.files_parsed,
                    files_failed=result.files_failed,
                    files_skipped=result.files_skipped,
                )

        if content_index_started:
            self._finish_content_index_update()

        with self._index_lock:
            self.dependency_graph.resolve_targets(self.symbol_table)

        result.parse_time_ms = (time.time() - parse_start) * 1000
        result.total_time_ms = (time.time() - start_time) * 1000
        self._last_index_result = result

        if not self.save_cache():
            result.warnings.append("Failed to persist incremental cache update")

        self._emit_progress(
            None,
            stage="complete",
            completed=total_files,
            total=total_files,
            message="index finished",
            files_scanned=len(changed_files),
            files_parsed=result.files_parsed,
            files_failed=result.files_failed,
            files_skipped=result.files_skipped,
        )

        return result
    
    def _detect_changes(self) -> List[Path]:
        """Detect files that have changed since last index"""
        changed = []
        current_files = set()
        
        for file_path in self.scan_files():
            file_str = str(file_path)
            current_files.add(file_str)
            
            try:
                stat = file_path.stat()
                mtime = stat.st_mtime
                size = stat.st_size
                
                if file_str not in self._file_info:
                    # New file
                    changed.append(file_path)
                elif (self._file_info[file_str].mtime != mtime or
                      self._file_info[file_str].size != size):
                    # Modified file
                    changed.append(file_path)
            except Exception:
                report_suppressed_exception("compare indexed file metadata")
        
        # Check for deleted files
        with self._index_lock:
            for file_str in list(self._file_info.keys()):
                if file_str not in current_files:
                    # File was deleted
                    self.symbol_table.remove_file(file_str)
                    self.dependency_graph.remove_file(file_str)
                    del self._file_info[file_str]
        
        return changed
    
    def _parse_file_safe(self, file_path: Path) -> Tuple[Optional[ParseResult], Optional[FileInfo]]:
        """Parse a file with safety checks for large files"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Skip binary files
            if self._is_binary_file(file_path):
                return None, None
            
            # Check file size
            try:
                stat = file_path.stat()
                size_kb = stat.st_size / 1024
            except Exception:
                return None, None
            
            # Skip extremely large files
            if size_kb > self.config.max_file_size_kb:
                logger.debug(
                    "Skipping oversized file %s (%.1fKB > %dKB)",
                    file_path,
                    size_kb,
                    self.config.max_file_size_kb,
                )
                return None, None
            
            logger.debug(f"Parsing file: {file_path}")
            result = self._parse_file(file_path)
            logger.debug(f"Parsed file: {file_path}")
            return result
        
        except Exception as e:
            logger.warning(f"Parse error for {file_path}: {e}")
            return ParseResult(
                file_path=str(file_path),
                language="unknown",
                errors=[f"Parse error: {str(e)}"]
            ), None
    
    def _parse_file(self, file_path: Path) -> Tuple[ParseResult, Optional[FileInfo]]:
        """Parse a single file and return result with file info"""
        parser = self._get_parser(file_path)
        
        if parser is None:
            return ParseResult(
                file_path=str(file_path),
                language="unknown",
                errors=["No parser available"]
            ), None
        
        # Read file
        content = parser.read_file(file_path)
        if content is None:
            return ParseResult(
                file_path=str(file_path),
                language=parser.LANGUAGE,
                errors=["Could not read file"]
            ), None
        
        # Get file info
        try:
            stat = file_path.stat()
            file_info = FileInfo(
                path=str(file_path),
                mtime=stat.st_mtime,
                size=stat.st_size,
                content_hash=self._calculate_file_hash(content)
            )
        except Exception:
            file_info = None
        
        # Parse
        parse_result = parser.parse_file(file_path, content)
        file_info = self._enrich_file_info(file_path, content, parse_result, file_info)
        
        # Lazy-load optimization: avoid storing full source for large files
        if self.config.lazy_load_source and file_info:
            size_kb = file_info.size / 1024
            if size_kb > self.config.max_file_size_for_full_parse_kb:
                for symbol in parse_result.symbols:
                    # Keep signature only, drop full source
                    pass
                    # if len(symbol.source_code or '') > 2000:
                    #    symbol.source_code = symbol.source_code[:2000] + "\n# ... (truncated for large file)"
        
        return parse_result, file_info
    
    def update_file(self, file_path: Path) -> IndexResult:
        """Update index for a single file (called after edits)"""
        return self.incremental_index([file_path.resolve()])

    def save_cache(self) -> bool:
        """Persist the latest index state to disk."""
        return self._cache_manager.save(
            self.symbol_table,
            self.dependency_graph,
            self._file_info,
            metadata=self._cache_metadata(),
        )

    def load_cache(self) -> bool:
        """Load cached index state when available."""
        cached = self._cache_manager.load(expected_metadata=self._cache_metadata())
        if not cached:
            return False
        self.symbol_table.replace_with(cached['symbol_table'])
        self.dependency_graph.replace_with(cached['dependency_graph'])
        self._file_info.clear()
        self._file_info.update(cached['file_info'])
        self._large_files.clear()
        self._large_files.update({
            path for path, info in self._file_info.items()
            if getattr(info, "size", 0) / 1024 > self.config.max_file_size_kb
        })
        self._index_progress = IndexProgress(
            stage="idle",
            message="Loaded cached index",
            started_at=time.time(),
            updated_at=time.time(),
        )
        self._last_index_result = None
        return True
    
    def get_statistics(self) -> Dict:
        """Get detailed indexing statistics"""
        total_size = sum(fi.size for fi in self._file_info.values())
        
        return {
            'files_indexed': len(self._file_info),
            'total_size_mb': total_size / (1024 * 1024),
            'large_files': len(self._large_files),
            'symbols': self.symbol_table.get_statistics(),
            'dependencies': self.dependency_graph.get_statistics(),
            'project_root': str(self.project_root),
            'index_status': self.get_index_status(),
            'cache_info': self._cache_manager.get_cache_info() or {},
        }
    
    def get_game_assets(self) -> Dict[str, List[Dict]]:
        """Get all game assets organized by type"""
        assets_by_type = {
            'image': [],
            'audio': [],
            'model': [],
            'animation': [],
            'font': [],
            'shader': [],
            'godot_resource': [],
            'tilemap': [],
            'other': []
        }
        
        for file_str, file_info in self._file_info.items():
            file_path = Path(file_str)
            
            if self._is_game_asset(file_path):
                asset_type = self._get_asset_type(file_path)
                
                asset_info = {
                    'path': file_str,
                    'name': file_path.name,
                    'size': file_info.size,
                    'size_kb': file_info.size / 1024,
                    'modified': file_info.mtime
                }
                
                if asset_type:
                    assets_by_type[asset_type].append(asset_info)
                else:
                    assets_by_type['other'].append(asset_info)
        
        return assets_by_type
    
    def get_game_asset_statistics(self) -> Dict:
        """Get statistics about game assets"""
        assets = self.get_game_assets()
        
        stats = {
            'total_assets': 0,
            'total_size_mb': 0.0,
            'by_type': {}
        }
        
        for asset_type, asset_list in assets.items():
            if asset_list:
                type_size = sum(a['size'] for a in asset_list)
                stats['by_type'][asset_type] = {
                    'count': len(asset_list),
                    'size_mb': type_size / (1024 * 1024)
                }
                stats['total_assets'] += len(asset_list)
                stats['total_size_mb'] += type_size / (1024 * 1024)
        
        return stats
    
    def find_file(self, pattern: str) -> List[str]:
        """Find files matching a pattern"""
        matches = []
        
        for file_str in self._file_info:
            if fnmatch.fnmatch(file_str, f'*{pattern}*'):
                matches.append(file_str)
        
        return matches
    
    def get_file_symbols(self, file_path: str) -> List[Symbol]:
        """Get all symbols from a specific file"""
        # Try exact match first
        symbols = self.symbol_table.get_all_in_file(file_path)
        if not symbols:
            try:
                # Try resolved path
                resolved = str(Path(file_path).resolve())
                if resolved != file_path:
                    symbols = self.symbol_table.get_all_in_file(resolved)
            except Exception:
                report_suppressed_exception("resolve symbol lookup path")
        return symbols
    
    def refresh(self) -> IndexResult:
        """Refresh index by detecting and updating changed files"""
        return self.incremental_index()
