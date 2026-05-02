"""
Simple Script Parser for lightweight game scripting files.

Supports:
- Lua (.lua) for Love2D
- GDScript (.gd) for Godot
"""

from pathlib import Path
from typing import Optional
import re

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind


class SimpleScriptParser(BaseParser):
    LANGUAGE = "script"
    FILE_EXTENSIONS = (".lua", ".gd")

    def __init__(self, project_root: Path):
        super().__init__(project_root)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.FILE_EXTENSIONS

    def parse_file(self, file_path: Path, content: Optional[str] = None) -> ParseResult:
        result = ParseResult(file_path=str(file_path), language=self._language_for(file_path))
        if content is None:
            content = self.read_file(file_path)
            if content is None:
                result.errors.append("Could not read file")
                return result

        lines = content.splitlines()
        module_name = self.get_module_name(file_path)

        for i, line in enumerate(lines):
            line_num = i + 1
            # Functions
            func_match = re.search(r'\bfunction\s+([a-zA-Z0-9_\.]+)\s*\(', line)
            if func_match:
                name = func_match.group(1).split(".")[-1]
                result.symbols.append(Symbol(
                    name=name,
                    qualified_name=f"{module_name}.{name}" if module_name else name,
                    kind=SymbolKind.FUNCTION,
                    file_path=str(file_path),
                    start_line=line_num,
                    end_line=line_num,
                    source_code=line.strip(),
                    language=result.language
                ))

            # Classes (GDScript)
            class_match = re.search(r'\bclass_name\s+([A-Za-z0-9_]+)', line)
            if class_match:
                name = class_match.group(1)
                result.symbols.append(Symbol(
                    name=name,
                    qualified_name=f"{module_name}.{name}" if module_name else name,
                    kind=SymbolKind.CLASS,
                    file_path=str(file_path),
                    start_line=line_num,
                    end_line=line_num,
                    source_code=line.strip(),
                    language=result.language
                ))

            # Variables
            var_match = re.search(r'^(?:var|local)\s+([A-Za-z0-9_]+)', line.strip())
            if var_match:
                name = var_match.group(1)
                result.symbols.append(Symbol(
                    name=name,
                    qualified_name=f"{module_name}.{name}" if module_name else name,
                    kind=SymbolKind.VARIABLE,
                    file_path=str(file_path),
                    start_line=line_num,
                    end_line=line_num,
                    source_code=line.strip(),
                    language=result.language
                ))

        return result

    def _language_for(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        if ext == ".lua":
            return "lua"
        if ext == ".gd":
            return "gdscript"
        return "script"
