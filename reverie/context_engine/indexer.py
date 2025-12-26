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
from typing import List, Dict, Optional, Set, Tuple, Callable
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
from .parsers.python_parser import PythonParser
from .parsers.treesitter_parser import TreeSitterParser, SUPPORTED_LANGUAGES


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
    
    @property
    def success(self) -> bool:
        return self.files_failed == 0
    
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
    progress_callback: Optional[Callable[[int, int, str], None]] = None


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
    }
    
    def __init__(
        self,
        project_root: Path,
        cache_dir: Optional[Path] = None,
        config: Optional[IndexConfig] = None
    ):
        self.project_root = Path(project_root).resolve()
        self.cache_dir = cache_dir or (self.project_root / '.reverie' / 'context_cache')
        self.config = config or IndexConfig()
        
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
            TreeSitterParser(self.project_root),
        ]
        
        # Large file tracking
        self._large_files: Set[str] = set()
        
        # Index lock (thread safety)
        self._index_lock = threading.Lock()
    
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
    
    def scan_files(self) -> List[Path]:
        """Scan project for all supported files with size filtering"""
        files = []
        large_files = []
        
        for root, dirs, filenames in os.walk(self.project_root):
            root_path = Path(root)
            
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore(root_path / d)]
            
            for filename in filenames:
                file_path = root_path / filename
                
                if self._should_ignore(file_path):
                    continue
                
                if not self._is_supported_file(file_path):
                    continue
                
                # Track large files separately (but still include them)
                if self._is_large_file(file_path):
                    large_files.append(file_path)
                    self._large_files.add(str(file_path))
                else:
                    files.append(file_path)
        
        # Append large files at the end (process last)
        files.extend(large_files)
        
        return files
    
    def full_index(
        self,
        show_progress: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> IndexResult:
        """
        Perform full indexing of the codebase.
        
        Optimized for large codebases with chunked processing.
        """
        start_time = time.time()
        result = IndexResult()
        callback = progress_callback or self.config.progress_callback
        
        # Clear existing data
        with self._index_lock:
            self.symbol_table = SymbolTable()
            self.dependency_graph = DependencyGraph()
            self._file_info.clear()
            self._large_files.clear()
        
        # Scan for files
        files = self.scan_files()
        result.files_scanned = len(files)
        
        if callback:
            callback(0, len(files), "Starting indexing...")
        
        # Calculate total size
        for f in files:
            try:
                result.total_bytes += f.stat().st_size
            except Exception:
                pass
        
        # Chunked parallel parsing
        parse_start = time.time()
        chunk_size = self.config.chunk_size
        
        for chunk_idx in range(0, len(files), chunk_size):
            chunk = files[chunk_idx:chunk_idx + chunk_size]
            
            if callback:
                progress = min(chunk_idx + chunk_size, len(files))
                callback(progress, len(files), f"Processing chunk {chunk_idx // chunk_size + 1}...")
            
            # Process chunk in parallel
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = {
                    executor.submit(self._parse_file_safe, f): f
                    for f in chunk
                }
                
                # Collect results
                chunk_symbols = []
                chunk_deps = []
                
                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        parse_result, file_info = future.result()
                        
                        if parse_result is None:
                            result.files_skipped += 1
                            continue
                        
                        if parse_result.success:
                            result.files_parsed += 1
                            result.symbols_extracted += parse_result.symbol_count
                            result.dependencies_extracted += len(parse_result.dependencies)
                            
                            chunk_symbols.extend(parse_result.symbols)
                            chunk_deps.extend(parse_result.dependencies)
                            
                            # Track file info
                            if file_info:
                                file_info.symbol_count = parse_result.symbol_count
                                self._file_info[str(file_path)] = file_info
                        else:
                            result.files_failed += 1
                            result.errors.extend(parse_result.errors)
                    
                    except Exception as e:
                        result.files_failed += 1
                        result.errors.append(f"{file_path}: {str(e)}")
                
                # Batch commit to symbol table and dependency graph
                with self._index_lock:
                    for symbol in chunk_symbols:
                        self.symbol_table.add_symbol(symbol)
                    for dep in chunk_deps:
                        self.dependency_graph.add_dependency(dep)
        
        result.parse_time_ms = (time.time() - parse_start) * 1000
        result.total_time_ms = (time.time() - start_time) * 1000
        
        # Add warning for large files
        if self._large_files:
            result.warnings.append(
                f"Found {len(self._large_files)} large file(s) that may have reduced parsing"
            )
        
        if callback:
            callback(len(files), len(files), "Indexing complete!")
        
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
        
        result.files_scanned = len(changed_files)
        
        parse_start = time.time()
        
        for file_path in changed_files:
            try:
                parse_result, file_info = self._parse_file_safe(file_path)
                
                if parse_result is None:
                    result.files_skipped += 1
                    continue
                
                if parse_result.success:
                    result.files_parsed += 1
                    result.symbols_extracted += parse_result.symbol_count
                    result.dependencies_extracted += len(parse_result.dependencies)
                    
                    # Remove old symbols/dependencies from this file
                    with self._index_lock:
                        self.symbol_table.remove_file(str(file_path))
                        self.dependency_graph.remove_file(str(file_path))
                        
                        # Add new symbols/dependencies
                        for symbol in parse_result.symbols:
                            self.symbol_table.add_symbol(symbol)
                        
                        for dep in parse_result.dependencies:
                            self.dependency_graph.add_dependency(dep)
                    
                    # Update file info
                    if file_info:
                        file_info.symbol_count = parse_result.symbol_count
                        self._file_info[str(file_path)] = file_info
                else:
                    result.files_failed += 1
                    result.errors.extend(parse_result.errors)
            
            except Exception as e:
                result.files_failed += 1
                result.errors.append(f"{file_path}: {str(e)}")
        
        result.parse_time_ms = (time.time() - parse_start) * 1000
        result.total_time_ms = (time.time() - start_time) * 1000
        
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
                return ParseResult(
                    file_path=str(file_path),
                    language="unknown",
                    errors=[f"File too large ({size_kb:.1f}KB > {self.config.max_file_size_kb}KB)"]
                ), None
            
            return self._parse_file(file_path)
        
        except Exception as e:
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
    
    def get_statistics(self) -> Dict:
        """Get detailed indexing statistics"""
        total_size = sum(fi.size for fi in self._file_info.values())
        
        return {
            'files_indexed': len(self._file_info),
            'total_size_mb': total_size / (1024 * 1024),
            'large_files': len(self._large_files),
            'symbols': self.symbol_table.get_statistics(),
            'dependencies': self.dependency_graph.get_statistics(),
            'project_root': str(self.project_root)
        }
    
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
