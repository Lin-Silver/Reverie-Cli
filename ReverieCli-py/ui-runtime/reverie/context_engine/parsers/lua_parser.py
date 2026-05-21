"""
Lua Parser for Love2D and other Lua-based game engines

This parser extracts:
- Function definitions (local and global)
- Variable definitions (local and global)
- Table definitions
- Module imports (require statements)
- Comments and documentation
"""

import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import time

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind
from ..dependency_graph import Dependency, DependencyType


class LuaParser(BaseParser):
    """
    Parser for Lua script files, optimized for Love2D game development.
    
    Supports:
    - Function definitions (function name(...) and local function name(...))
    - Variable assignments (local var = ... and var = ...)
    - Table definitions (local tbl = {} and tbl = {})
    - Module imports (require "module" and require("module"))
    - Method definitions (function Class:method(...))
    - Anonymous functions assigned to variables
    """
    
    LANGUAGE = "lua"
    FILE_EXTENSIONS = ('.lua',)
    
    # Regex patterns for Lua constructs
    FUNCTION_PATTERN = re.compile(
        r'^\s*(local\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_.:]*)\s*\((.*?)\)',
        re.MULTILINE
    )
    
    METHOD_PATTERN = re.compile(
        r'^\s*(local\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_.]*):([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)',
        re.MULTILINE
    )
    
    VARIABLE_PATTERN = re.compile(
        r'^\s*(local\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)',
        re.MULTILINE
    )
    
    TABLE_PATTERN = re.compile(
        r'^\s*(local\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\{',
        re.MULTILINE
    )
    
    REQUIRE_PATTERN = re.compile(
        r'require\s*[\(\s]*["\']([^"\']+)["\'][\)\s]*',
        re.MULTILINE
    )
    
    COMMENT_PATTERN = re.compile(
        r'--\[\[.*?\]\]|--.*?$',
        re.MULTILINE | re.DOTALL
    )
    
    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.FILE_EXTENSIONS
    
    def parse_file(self, file_path: Path, content: Optional[str] = None) -> ParseResult:
        start_time = time.time()
        result = ParseResult(
            file_path=str(file_path),
            language=self.LANGUAGE
        )
        
        # Read content if not provided
        if content is None:
            content = self.read_file(file_path)
            if content is None:
                result.errors.append(f"Could not read file: {file_path}")
                return result
        
        # Store content lines for source extraction
        self._lines = content.split('\n')
        self._content = content
        self._file_path = str(file_path)
        self._module_name = self.get_module_name(file_path)
        
        # Extract different constructs
        self._extract_requires(content, result)
        self._extract_functions(content, result)
        self._extract_methods(content, result)
        self._extract_variables(content, result)
        self._extract_tables(content, result)
        
        result.parse_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _extract_requires(self, content: str, result: ParseResult) -> None:
        """Extract require statements (module imports)"""
        for match in self.REQUIRE_PATTERN.finditer(content):
            module_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            result.imports.append({
                'module': module_name,
                'alias': None,
                'symbols': None,
                'line': line_num
            })
            
            # Add dependency
            result.dependencies.append(Dependency(
                from_symbol=self._module_name,
                to_symbol=module_name,
                dep_type=DependencyType.IMPORTS,
                file_path=self._file_path,
                line=line_num,
                context=f'require "{module_name}"'
            ))
    
    def _extract_functions(self, content: str, result: ParseResult) -> None:
        """Extract function definitions"""
        for match in self.FUNCTION_PATTERN.finditer(content):
            is_local = match.group(1) is not None
            full_name = match.group(2)
            params_str = match.group(3)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Parse function name (handle nested names like module.submodule.func)
            name_parts = full_name.split('.')
            simple_name = name_parts[-1]
            
            # Build qualified name
            if is_local:
                qname = f"{self._module_name}.{simple_name}"
            else:
                qname = f"{self._module_name}.{full_name}"
            
            # Parse parameters
            params = self._parse_parameters(params_str)
            
            # Build signature
            signature = f"{'local ' if is_local else ''}function {full_name}({params_str})"
            
            # Extract source code (find function end)
            source, end_line = self._extract_function_body(line_num)
            
            # Extract docstring (comment before function)
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=simple_name,
                qualified_name=qname,
                kind=SymbolKind.FUNCTION,
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parameters=params,
                modifiers=['local'] if is_local else [],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_methods(self, content: str, result: ParseResult) -> None:
        """Extract method definitions (Class:method syntax)"""
        for match in self.METHOD_PATTERN.finditer(content):
            is_local = match.group(1) is not None
            class_name = match.group(2)
            method_name = match.group(3)
            params_str = match.group(4)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            qname = f"{self._module_name}.{class_name}.{method_name}"
            
            # Parse parameters (add implicit 'self')
            params = [{'name': 'self', 'type': None}]
            params.extend(self._parse_parameters(params_str))
            
            # Build signature
            signature = f"{'local ' if is_local else ''}function {class_name}:{method_name}({params_str})"
            
            # Extract source code
            source, end_line = self._extract_function_body(line_num)
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=method_name,
                qualified_name=qname,
                kind=SymbolKind.METHOD,
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parent=f"{self._module_name}.{class_name}",
                parameters=params,
                modifiers=['local'] if is_local else [],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_variables(self, content: str, result: ParseResult) -> None:
        """Extract variable assignments"""
        for match in self.VARIABLE_PATTERN.finditer(content):
            is_local = match.group(1) is not None
            var_name = match.group(2)
            value = match.group(3).strip()
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Skip if this is a function definition (handled separately)
            if value.startswith('function'):
                continue
            
            # Skip if this is a table definition (handled separately)
            if value.startswith('{'):
                continue
            
            # Build qualified name
            qname = f"{self._module_name}.{var_name}"
            
            # Determine if it's a constant (ALL_CAPS convention)
            kind = SymbolKind.CONSTANT if var_name.isupper() else SymbolKind.VARIABLE
            
            # Get source line
            source = self._lines[line_num - 1] if line_num <= len(self._lines) else ""
            
            symbol = Symbol(
                name=var_name,
                qualified_name=qname,
                kind=kind,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                source_code=source,
                modifiers=['local'] if is_local else [],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_tables(self, content: str, result: ParseResult) -> None:
        """Extract table definitions"""
        for match in self.TABLE_PATTERN.finditer(content):
            is_local = match.group(1) is not None
            table_name = match.group(2)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            qname = f"{self._module_name}.{table_name}"
            
            # Extract table body
            source, end_line = self._extract_table_body(line_num)
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=table_name,
                qualified_name=qname,
                kind=SymbolKind.CLASS,  # Treat tables as classes (Lua's OOP mechanism)
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=f"{'local ' if is_local else ''}{table_name} = {{}}",
                docstring=docstring,
                source_code=source,
                modifiers=['local'] if is_local else [],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _parse_parameters(self, params_str: str) -> List[Dict]:
        """Parse function parameters"""
        if not params_str.strip():
            return []
        
        params = []
        for param in params_str.split(','):
            param = param.strip()
            if param:
                # Check for default value (Lua doesn't have native default params, but some use comments)
                if '=' in param:
                    name, default = param.split('=', 1)
                    params.append({
                        'name': name.strip(),
                        'type': None,
                        'default': default.strip()
                    })
                else:
                    params.append({
                        'name': param,
                        'type': None
                    })
        
        return params
    
    def _extract_function_body(self, start_line: int) -> Tuple[str, int]:
        """Extract function body by finding matching 'end' keyword"""
        if start_line > len(self._lines):
            return "", start_line
        
        depth = 1
        end_line = start_line
        
        for i in range(start_line, len(self._lines)):
            line = self._lines[i]
            
            # Count function/if/for/while keywords (increase depth)
            depth += len(re.findall(r'\b(function|if|for|while|repeat)\b', line))
            
            # Count end keywords (decrease depth)
            depth -= len(re.findall(r'\bend\b', line))
            
            # Count until keywords for repeat-until
            depth -= len(re.findall(r'\buntil\b', line))
            
            if depth == 0:
                end_line = i + 1
                break
        
        # Extract source
        source_lines = self._lines[start_line - 1:end_line]
        return '\n'.join(source_lines), end_line
    
    def _extract_table_body(self, start_line: int) -> Tuple[str, int]:
        """Extract table body by finding matching closing brace"""
        if start_line > len(self._lines):
            return "", start_line
        
        depth = 1
        end_line = start_line
        
        # Start from the line with the opening brace
        start_idx = start_line - 1
        
        for i in range(start_line, len(self._lines)):
            line = self._lines[i]
            
            # Count opening braces
            depth += line.count('{')
            
            # Count closing braces
            depth -= line.count('}')
            
            if depth == 0:
                end_line = i + 1
                break
        
        # Extract source
        source_lines = self._lines[start_idx:end_line]
        return '\n'.join(source_lines), end_line
    
    def _extract_docstring(self, line_num: int) -> Optional[str]:
        """Extract comment before a definition (Lua docstring convention)"""
        if line_num <= 1:
            return None
        
        docstring_lines = []
        
        # Look backwards for comments
        for i in range(line_num - 2, -1, -1):
            line = self._lines[i].strip()
            
            # Stop at empty line
            if not line:
                break
            
            # Check for single-line comment
            if line.startswith('--'):
                # Remove comment markers
                comment = line[2:].strip()
                docstring_lines.insert(0, comment)
            else:
                # Stop at non-comment line
                break
        
        if docstring_lines:
            return '\n'.join(docstring_lines)
        
        return None
