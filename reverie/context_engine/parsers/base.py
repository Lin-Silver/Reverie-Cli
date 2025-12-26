"""
Base parser interface for Context Engine

All language-specific parsers must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from ..symbol_table import Symbol, SymbolKind
from ..dependency_graph import Dependency, DependencyType


@dataclass
class ParseResult:
    """Result of parsing a file"""
    file_path: str
    language: str
    symbols: List[Symbol] = field(default_factory=list)
    dependencies: List[Dependency] = field(default_factory=list)
    imports: List[Dict] = field(default_factory=list)  # [{module, alias, symbols}]
    errors: List[str] = field(default_factory=list)
    parse_time_ms: float = 0.0
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0
    
    @property
    def symbol_count(self) -> int:
        return len(self.symbols)


class BaseParser(ABC):
    """
    Abstract base class for language parsers.
    
    Each parser is responsible for:
    1. Extracting symbols (functions, classes, variables, etc.)
    2. Building dependency relationships
    3. Extracting import statements
    """
    
    # Override in subclasses
    LANGUAGE: str = "unknown"
    FILE_EXTENSIONS: Tuple[str, ...] = ()
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    @abstractmethod
    def parse_file(self, file_path: Path, content: Optional[str] = None) -> ParseResult:
        """
        Parse a single file and extract symbols/dependencies.
        
        Args:
            file_path: Path to the file
            content: Optional file content (if already read)
        
        Returns:
            ParseResult with symbols and dependencies
        """
        pass
    
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file"""
        pass
    
    def get_relative_path(self, file_path: Path) -> str:
        """Get path relative to project root"""
        try:
            return str(file_path.relative_to(self.project_root))
        except ValueError:
            return str(file_path)
    
    def read_file(self, file_path: Path) -> Optional[str]:
        """Read file content with encoding detection"""
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                return None
        
        return None
    
    def extract_docstring(self, source: str, start_line: int) -> Optional[str]:
        """
        Extract docstring from source code starting at given line.
        Override for language-specific behavior.
        """
        return None
    
    def get_module_name(self, file_path: Path) -> str:
        """
        Convert file path to module-style name.
        e.g., src/utils/helpers.py -> src.utils.helpers
        """
        rel_path = self.get_relative_path(file_path)
        # Remove extension
        if '.' in rel_path:
            rel_path = rel_path.rsplit('.', 1)[0]
        # Convert path separators to dots
        module_name = rel_path.replace('/', '.').replace('\\', '.')
        return module_name
