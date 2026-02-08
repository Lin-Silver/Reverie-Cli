"""
GDScript Parser for Godot Engine

This parser extracts:
- Class definitions (class_name, extends)
- Function definitions (func name(...))
- Variable definitions (var, const, export)
- Signal definitions (signal name)
- Enum definitions
- Inner classes
- Comments and documentation
"""

import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import time

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind
from ..dependency_graph import Dependency, DependencyType


class GDScriptParser(BaseParser):
    """
    Parser for GDScript files (Godot Engine).
    
    Supports:
    - Class definitions (class_name, extends)
    - Function definitions (func, static func)
    - Variable definitions (var, const, export var, onready var)
    - Signal definitions
    - Enum definitions
    - Inner classes
    - Type annotations
    """
    
    LANGUAGE = "gdscript"
    FILE_EXTENSIONS = ('.gd',)
    
    # Regex patterns for GDScript constructs
    CLASS_NAME_PATTERN = re.compile(
        r'^\s*class_name\s+([A-Za-z_][A-Za-z0-9_]*)',
        re.MULTILINE
    )
    
    EXTENDS_PATTERN = re.compile(
        r'^\s*extends\s+([A-Za-z_][A-Za-z0-9_.]*)',
        re.MULTILINE
    )
    
    INNER_CLASS_PATTERN = re.compile(
        r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:extends\s+([A-Za-z_][A-Za-z0-9_.]*))?:',
        re.MULTILINE
    )
    
    FUNCTION_PATTERN = re.compile(
        r'^\s*(static\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*(?:->\s*([A-Za-z_][A-Za-z0-9_.]*))?:',
        re.MULTILINE
    )
    
    VARIABLE_PATTERN = re.compile(
        r'^\s*(export\s*(?:\([^)]*\)\s*)?|onready\s+|const\s+|var\s+)([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([A-Za-z_][A-Za-z0-9_.]*))?(?:\s*=\s*(.+))?',
        re.MULTILINE
    )
    
    SIGNAL_PATTERN = re.compile(
        r'^\s*signal\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*?)\))?',
        re.MULTILINE
    )
    
    ENUM_PATTERN = re.compile(
        r'^\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{',
        re.MULTILINE
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
        
        # Extract class name and inheritance
        self._class_name = None
        self._base_class = None
        self._extract_class_info(content, result)
        
        # Extract different constructs
        self._extract_signals(content, result)
        self._extract_enums(content, result)
        self._extract_inner_classes(content, result)
        self._extract_functions(content, result)
        self._extract_variables(content, result)
        
        result.parse_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _extract_class_info(self, content: str, result: ParseResult) -> None:
        """Extract class_name and extends declarations"""
        # Extract class_name
        class_match = self.CLASS_NAME_PATTERN.search(content)
        if class_match:
            self._class_name = class_match.group(1)
            line_num = content[:class_match.start()].count('\n') + 1
            
            # Create class symbol
            qname = f"{self._module_name}.{self._class_name}"
            
            symbol = Symbol(
                name=self._class_name,
                qualified_name=qname,
                kind=SymbolKind.CLASS,
                file_path=self._file_path,
                start_line=line_num,
                end_line=len(self._lines),
                signature=f"class_name {self._class_name}",
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
        
        # Extract extends
        extends_match = self.EXTENDS_PATTERN.search(content)
        if extends_match:
            self._base_class = extends_match.group(1)
            line_num = content[:extends_match.start()].count('\n') + 1
            
            # Add inheritance dependency
            if self._class_name:
                result.dependencies.append(Dependency(
                    from_symbol=f"{self._module_name}.{self._class_name}",
                    to_symbol=self._base_class,
                    dep_type=DependencyType.INHERITS,
                    file_path=self._file_path,
                    line=line_num,
                    context=f"extends {self._base_class}"
                ))
    
    def _extract_signals(self, content: str, result: ParseResult) -> None:
        """Extract signal definitions"""
        for match in self.SIGNAL_PATTERN.finditer(content):
            signal_name = match.group(1)
            params_str = match.group(2) or ""
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            if self._class_name:
                qname = f"{self._module_name}.{self._class_name}.{signal_name}"
                parent = f"{self._module_name}.{self._class_name}"
            else:
                qname = f"{self._module_name}.{signal_name}"
                parent = None
            
            # Parse parameters
            params = self._parse_parameters(params_str)
            
            # Build signature
            signature = f"signal {signal_name}"
            if params_str:
                signature += f"({params_str})"
            
            # Get source line
            source = self._lines[line_num - 1] if line_num <= len(self._lines) else ""
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=signal_name,
                qualified_name=qname,
                kind=SymbolKind.PROPERTY,  # Signals are like properties/events
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parent=parent,
                parameters=params,
                modifiers=['signal'],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_enums(self, content: str, result: ParseResult) -> None:
        """Extract enum definitions"""
        for match in self.ENUM_PATTERN.finditer(content):
            enum_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            if self._class_name:
                qname = f"{self._module_name}.{self._class_name}.{enum_name}"
                parent = f"{self._module_name}.{self._class_name}"
            else:
                qname = f"{self._module_name}.{enum_name}"
                parent = None
            
            # Extract enum body
            source, end_line = self._extract_block_body(line_num)
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=enum_name,
                qualified_name=qname,
                kind=SymbolKind.CLASS,  # Treat enums as a type of class
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=f"enum {enum_name}",
                docstring=docstring,
                source_code=source,
                parent=parent,
                modifiers=['enum'],
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_inner_classes(self, content: str, result: ParseResult) -> None:
        """Extract inner class definitions"""
        for match in self.INNER_CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            base_class = match.group(2)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            if self._class_name:
                qname = f"{self._module_name}.{self._class_name}.{class_name}"
                parent = f"{self._module_name}.{self._class_name}"
            else:
                qname = f"{self._module_name}.{class_name}"
                parent = None
            
            # Build signature
            signature = f"class {class_name}"
            if base_class:
                signature += f" extends {base_class}"
            signature += ":"
            
            # Extract class body
            source, end_line = self._extract_indented_block(line_num)
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=class_name,
                qualified_name=qname,
                kind=SymbolKind.CLASS,
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parent=parent,
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
            
            # Add inheritance dependency
            if base_class:
                result.dependencies.append(Dependency(
                    from_symbol=qname,
                    to_symbol=base_class,
                    dep_type=DependencyType.INHERITS,
                    file_path=self._file_path,
                    line=line_num,
                    context=f"class {class_name} extends {base_class}"
                ))
    
    def _extract_functions(self, content: str, result: ParseResult) -> None:
        """Extract function definitions"""
        for match in self.FUNCTION_PATTERN.finditer(content):
            is_static = match.group(1) is not None
            func_name = match.group(2)
            params_str = match.group(3)
            return_type = match.group(4)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            if self._class_name:
                qname = f"{self._module_name}.{self._class_name}.{func_name}"
                parent = f"{self._module_name}.{self._class_name}"
                kind = SymbolKind.METHOD
            else:
                qname = f"{self._module_name}.{func_name}"
                parent = None
                kind = SymbolKind.FUNCTION
            
            # Parse parameters
            params = self._parse_parameters(params_str)
            
            # Build signature
            signature = f"{'static ' if is_static else ''}func {func_name}({params_str})"
            if return_type:
                signature += f" -> {return_type}"
            signature += ":"
            
            # Extract function body
            source, end_line = self._extract_indented_block(line_num)
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            modifiers = []
            if is_static:
                modifiers.append('static')
            
            symbol = Symbol(
                name=func_name,
                qualified_name=qname,
                kind=kind,
                file_path=self._file_path,
                start_line=line_num,
                end_line=end_line,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parent=parent,
                return_type=return_type,
                parameters=params,
                modifiers=modifiers,
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_variables(self, content: str, result: ParseResult) -> None:
        """Extract variable definitions"""
        for match in self.VARIABLE_PATTERN.finditer(content):
            modifier = match.group(1).strip()
            var_name = match.group(2)
            type_annotation = match.group(3)
            value = match.group(4)
            
            line_num = content[:match.start()].count('\n') + 1
            
            # Build qualified name
            if self._class_name:
                qname = f"{self._module_name}.{self._class_name}.{var_name}"
                parent = f"{self._module_name}.{self._class_name}"
            else:
                qname = f"{self._module_name}.{var_name}"
                parent = None
            
            # Determine kind
            if modifier.startswith('const'):
                kind = SymbolKind.CONSTANT
            else:
                kind = SymbolKind.VARIABLE
            
            # Build modifiers list
            modifiers = []
            if 'export' in modifier:
                modifiers.append('export')
            if 'onready' in modifier:
                modifiers.append('onready')
            if 'const' in modifier:
                modifiers.append('const')
            
            # Build signature
            signature = f"{modifier}{var_name}"
            if type_annotation:
                signature += f": {type_annotation}"
            if value:
                # Truncate long values
                value_str = value.strip()
                if len(value_str) > 50:
                    value_str = value_str[:50] + "..."
                signature += f" = {value_str}"
            
            # Get source line
            source = self._lines[line_num - 1] if line_num <= len(self._lines) else ""
            
            # Extract docstring
            docstring = self._extract_docstring(line_num)
            
            symbol = Symbol(
                name=var_name,
                qualified_name=qname,
                kind=kind,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=signature,
                docstring=docstring,
                source_code=source,
                parent=parent,
                type_annotation=type_annotation,
                modifiers=modifiers,
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _parse_parameters(self, params_str: str) -> List[Dict]:
        """Parse function parameters with type annotations"""
        if not params_str.strip():
            return []
        
        params = []
        for param in params_str.split(','):
            param = param.strip()
            if not param:
                continue
            
            # Parse: name: type = default
            param_dict = {'name': param, 'type': None, 'default': None}
            
            # Check for default value
            if '=' in param:
                param, default = param.split('=', 1)
                param = param.strip()
                param_dict['default'] = default.strip()
            
            # Check for type annotation
            if ':' in param:
                name, type_ann = param.split(':', 1)
                param_dict['name'] = name.strip()
                param_dict['type'] = type_ann.strip()
            else:
                param_dict['name'] = param
            
            params.append(param_dict)
        
        return params
    
    def _extract_indented_block(self, start_line: int) -> Tuple[str, int]:
        """Extract an indented block (function, class, etc.)"""
        if start_line > len(self._lines):
            return "", start_line
        
        # Get the indentation of the definition line
        def_line = self._lines[start_line - 1]
        base_indent = len(def_line) - len(def_line.lstrip())
        
        end_line = start_line
        
        # Find the end of the block (when indentation returns to base level or less)
        for i in range(start_line, len(self._lines)):
            line = self._lines[i]
            
            # Skip empty lines
            if not line.strip():
                continue
            
            # Check indentation
            line_indent = len(line) - len(line.lstrip())
            
            # If indentation is less than or equal to base, we've reached the end
            if line_indent <= base_indent:
                end_line = i
                break
        else:
            # Reached end of file
            end_line = len(self._lines)
        
        # Extract source
        source_lines = self._lines[start_line - 1:end_line]
        return '\n'.join(source_lines), end_line
    
    def _extract_block_body(self, start_line: int) -> Tuple[str, int]:
        """Extract block body by finding matching closing brace"""
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
        """Extract comment before a definition (GDScript docstring convention)"""
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
            if line.startswith('#'):
                # Remove comment marker
                comment = line[1:].strip()
                docstring_lines.insert(0, comment)
            else:
                # Stop at non-comment line
                break
        
        if docstring_lines:
            return '\n'.join(docstring_lines)
        
        return None
