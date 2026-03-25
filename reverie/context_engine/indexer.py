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
from typing import List, Dict, Optional, Set, Tuple, Callable, Any
from dataclasses import dataclass, field
import time
import os
import fnmatch
import hashlib
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from .symbol_table import Symbol, SymbolTable
from .dependency_graph import DependencyGraph, Dependency
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
        '__pycache__', '**/__pycache__/**',
        'node_modules', '**/node_modules/**',
        '.venv', '**/.venv/**',
        'venv', '**/venv/**',
        '.env', '**/.env/**',
        'env', '**/env/**',
        'dist', '**/dist/**',
        'build', '**/build/**',
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
        '.unity', '.prefab',  # Unity
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
        
        # Core data structures
        self.symbol_table = SymbolTable()
        self.dependency_graph = DependencyGraph()
        
        # File tracking for incremental updates
        self._file_info: Dict[str, FileInfo] = {}
        
        # File ignore patterns (from .gitignore + defaults)
        self._ignore_patterns = set(self.DEFAULT_IGNORE_PATTERNS)
        self._load_gitignore()
        self._load_reverie_ignore()
        
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
        gitignore_path = self.project_root / '.gitignore'
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith('#'):
                            self._ignore_patterns.add(line)
                            # Add recursive version
                            if not line.startswith('**/'):
                                self._ignore_patterns.add(f'**/{line}')
            except Exception:
                pass
    
    def _load_reverie_ignore(self) -> None:
        """Load patterns from .reverieignore if it exists"""
        reverie_ignore = self.project_root / '.reverieignore'
        if reverie_ignore.exists():
            try:
                with open(reverie_ignore, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self._ignore_patterns.add(line)
                            if not line.startswith('**/'):
                                self._ignore_patterns.add(f'**/{line}')
            except Exception:
                pass
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored"""
        try:
            rel_path = str(path.relative_to(self.project_root))
        except ValueError:
            return True
        
        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch(path.name, pattern):
                return True
        
        return False
    
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
        if ext in {'.unity', '.prefab'}:
            return 'unity_resource'
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

        if file_info:
            file_info.symbol_count = parse_result.symbol_count
            file_info_store[file_key] = file_info

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
        path_text = str(file_path).lower().replace("\\", "/")
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
                dirs[:] = [d for d in dirs if not self._should_ignore(root_path / d)]
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
                pass
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

        for index, file_path in enumerate(changed_files, start=1):
            file_key = str(file_path)
            try:
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
                pass
        
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
        )

    def load_cache(self) -> bool:
        """Load cached index state when available."""
        cached = self._cache_manager.load()
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
            'unity_resource': [],
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
                pass
        return symbols
    
    def refresh(self) -> IndexResult:
        """Refresh index by detecting and updating changed files"""
        return self.incremental_index()
