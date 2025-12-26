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
from dataclasses import asdict

from .symbol_table import SymbolTable
from .dependency_graph import DependencyGraph


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
    
    CACHE_VERSION = "1.0.0"
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
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
            # Save index with metadata
            index_data = {
                'version': self.CACHE_VERSION,
                'saved_at': time.time(),
                'symbol_count': len(symbol_table),
                'dependency_count': len(dependency_graph),
                'file_count': len(file_info),
                'metadata': metadata or {}
            }
            
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2)
            
            # Save symbol table (compressed)
            symbol_data = symbol_table.to_dict()
            self._save_compressed(self.symbols_path, symbol_data)
            
            # Save dependency graph (compressed)
            dep_data = dependency_graph.to_dict()
            self._save_compressed(self.dependencies_path, dep_data)
            
            # Save file info
            files_data = {
                path: {
                    'path': info.path,
                    'mtime': info.mtime,
                    'size': info.size,
                    'content_hash': info.content_hash
                }
                for path, info in file_info.items()
            }
            
            with open(self.files_path, 'w', encoding='utf-8') as f:
                json.dump(files_data, f)
            
            return True
            
        except Exception as e:
            print(f"Error saving cache: {e}")
            return False
    
    def load(self) -> Optional[Dict]:
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
            # Check index
            if not self.index_path.exists():
                return None
            
            with open(self.index_path, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            # Version check
            if index_data.get('version') != self.CACHE_VERSION:
                return None
            
            # Load symbol table
            symbol_data = self._load_compressed(self.symbols_path)
            if symbol_data is None:
                return None
            symbol_table = SymbolTable.from_dict(symbol_data)
            
            # Load dependency graph
            dep_data = self._load_compressed(self.dependencies_path)
            if dep_data is None:
                return None
            dependency_graph = DependencyGraph.from_dict(dep_data)
            
            # Load file info
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
                    content_hash=data['content_hash']
                )
                for path, data in files_data.items()
            }
            
            return {
                'symbol_table': symbol_table,
                'dependency_graph': dependency_graph,
                'file_info': file_info,
                'metadata': index_data.get('metadata', {}),
                'saved_at': index_data.get('saved_at')
            }
            
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None
    
    def is_valid(self) -> bool:
        """Check if cache exists and is valid"""
        if not self.index_path.exists():
            return False
        
        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            return index_data.get('version') == self.CACHE_VERSION
        except Exception:
            return False
    
    def clear(self) -> None:
        """Clear all cache files"""
        for path in [self.index_path, self.symbols_path, 
                     self.dependencies_path, self.files_path]:
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
            return None
    
    def _save_compressed(self, path: Path, data: Dict) -> None:
        """Save data as compressed JSON"""
        json_str = json.dumps(data)
        compressed = gzip.compress(json_str.encode('utf-8'))
        
        with open(path, 'wb') as f:
            f.write(compressed)
    
    def _load_compressed(self, path: Path) -> Optional[Dict]:
        """Load compressed JSON data"""
        if not path.exists():
            return None
        
        try:
            with open(path, 'rb') as f:
                compressed = f.read()
            
            json_str = gzip.decompress(compressed).decode('utf-8')
            return json.loads(json_str)
        except Exception:
            return None
