"""
Python Parser - Uses Python's built-in ast module

This parser provides deep analysis of Python code including:
- Class and function definitions
- Decorators and type hints
- Import statements and dependencies
- Variable assignments at module level
- Docstrings extraction
"""

import ast
from pathlib import Path
from typing import Optional, List, Dict, Set
import time

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind, Reference
from ..dependency_graph import Dependency, DependencyType


class PythonParser(BaseParser):
    """
    High-fidelity Python parser using the ast module.
    
    Advantages over tree-sitter for Python:
    - Native Python support, no external dependencies
    - Access to semantic information
    - Better docstring extraction
    - Type annotation parsing
    """
    
    LANGUAGE = "python"
    FILE_EXTENSIONS = ('.py', '.pyw', '.pyi')
    
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
        
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            result.errors.append(f"Syntax error: {e}")
            return result
        
        # Extract symbols and dependencies
        self._extract_from_ast(tree, result)
        
        result.parse_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _extract_from_ast(self, tree: ast.AST, result: ParseResult) -> None:
        """Main extraction logic"""
        
        # First pass: collect all imports
        self._import_map: Dict[str, str] = {}  # alias -> full module path
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._process_import(node, result)
        
        # Second pass: extract symbols and dependencies
        self._process_node(tree, result, parent_qname=None)
    
    def _process_import(self, node: ast.AST, result: ParseResult) -> None:
        """Process import statements"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                self._import_map[name] = alias.name
                result.imports.append({
                    'module': alias.name,
                    'alias': alias.asname,
                    'symbols': None,
                    'line': node.lineno
                })
        
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                full_path = f"{module}.{alias.name}" if module else alias.name
                self._import_map[name] = full_path
            
            result.imports.append({
                'module': module,
                'alias': None,
                'symbols': [(a.name, a.asname) for a in node.names],
                'line': node.lineno,
                'level': node.level  # Relative import level
            })
    
    def _process_node(
        self,
        node: ast.AST,
        result: ParseResult,
        parent_qname: Optional[str]
    ) -> None:
        """Recursively process AST nodes"""
        
        if isinstance(node, ast.Module):
            # Create module symbol
            module_sym = Symbol(
                name=self._module_name.split('.')[-1],
                qualified_name=self._module_name,
                kind=SymbolKind.MODULE,
                file_path=self._file_path,
                start_line=1,
                end_line=len(self._lines),
                language=self.LANGUAGE
            )
            result.symbols.append(module_sym)
            
            # Process children
            for child in node.body:
                self._process_node(child, result, self._module_name)
        
        elif isinstance(node, ast.ClassDef):
            self._process_class(node, result, parent_qname)
        
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            self._process_function(node, result, parent_qname)
        
        elif isinstance(node, ast.Assign):
            self._process_assignment(node, result, parent_qname)
        
        elif isinstance(node, ast.AnnAssign):
            self._process_annotated_assignment(node, result, parent_qname)
    
    def _process_class(
        self,
        node: ast.ClassDef,
        result: ParseResult,
        parent_qname: Optional[str]
    ) -> None:
        """Process class definition"""
        qname = f"{parent_qname}.{node.name}" if parent_qname else node.name
        
        # Get decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        # Get base classes
        bases = [self._get_annotation_str(b) for b in node.bases]
        
        # Get source code
        source = self._get_source(node.lineno, node.end_lineno or node.lineno)
        
        # Get docstring
        docstring = ast.get_docstring(node)
        
        # Build signature
        signature = f"class {node.name}"
        if bases:
            signature += f"({', '.join(bases)})"
        signature += ":"
        
        symbol = Symbol(
            name=node.name,
            qualified_name=qname,
            kind=SymbolKind.CLASS,
            file_path=self._file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_column=node.col_offset,
            signature=signature,
            docstring=docstring,
            source_code=source,
            parent=parent_qname,
            decorators=decorators,
            language=self.LANGUAGE
        )
        
        result.symbols.append(symbol)
        
        # Add inheritance dependencies
        for base in node.bases:
            base_name = self._get_annotation_str(base)
            if base_name:
                result.dependencies.append(Dependency(
                    from_symbol=qname,
                    to_symbol=self._resolve_name(base_name),
                    dep_type=DependencyType.INHERITS,
                    file_path=self._file_path,
                    line=node.lineno,
                    context=f"class {node.name}({base_name})"
                ))
        
        # Process class body
        children = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_qname = f"{qname}.{child.name}"
                children.append(child_qname)
                self._process_function(child, result, qname, is_method=True)
            elif isinstance(child, ast.ClassDef):
                child_qname = f"{qname}.{child.name}"
                children.append(child_qname)
                self._process_class(child, result, qname)
            elif isinstance(child, ast.Assign):
                self._process_assignment(child, result, qname, is_class_var=True)
            elif isinstance(child, ast.AnnAssign):
                self._process_annotated_assignment(child, result, qname, is_class_var=True)
        
        symbol.children = children
    
    def _process_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        result: ParseResult,
        parent_qname: Optional[str],
        is_method: bool = False
    ) -> None:
        """Process function/method definition"""
        qname = f"{parent_qname}.{node.name}" if parent_qname else node.name
        
        # Determine kind
        if is_method:
            if node.name.startswith('__') and node.name.endswith('__'):
                kind = SymbolKind.METHOD  # dunder method
            elif any(self._get_decorator_name(d) == 'property' for d in node.decorator_list):
                kind = SymbolKind.PROPERTY
            elif any(self._get_decorator_name(d) in ('staticmethod', 'classmethod') 
                    for d in node.decorator_list):
                kind = SymbolKind.METHOD
            else:
                kind = SymbolKind.METHOD
        else:
            kind = SymbolKind.FUNCTION
        
        # Get decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        # Get modifiers
        modifiers = []
        if isinstance(node, ast.AsyncFunctionDef):
            modifiers.append('async')
        if 'staticmethod' in decorators:
            modifiers.append('static')
        if 'classmethod' in decorators:
            modifiers.append('classmethod')
        if 'property' in decorators:
            modifiers.append('property')
        
        # Get parameters
        params = self._extract_parameters(node.args)
        
        # Get return type
        return_type = self._get_annotation_str(node.returns) if node.returns else None
        
        # Build signature
        param_strs = []
        for p in params:
            ps = p['name']
            if p.get('type'):
                ps += f": {p['type']}"
            if p.get('default'):
                ps += f" = {p['default']}"
            param_strs.append(ps)
        
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        signature = f"{async_prefix}def {node.name}({', '.join(param_strs)})"
        if return_type:
            signature += f" -> {return_type}"
        signature += ":"
        
        # Get source and docstring
        source = self._get_source(node.lineno, node.end_lineno or node.lineno)
        docstring = ast.get_docstring(node)
        
        symbol = Symbol(
            name=node.name,
            qualified_name=qname,
            kind=kind,
            file_path=self._file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_column=node.col_offset,
            signature=signature,
            docstring=docstring,
            source_code=source,
            parent=parent_qname,
            return_type=return_type,
            parameters=params,
            decorators=decorators,
            modifiers=modifiers,
            language=self.LANGUAGE
        )
        
        result.symbols.append(symbol)
        
        # Extract call dependencies from function body
        self._extract_calls(node, qname, result)
    
    def _process_assignment(
        self,
        node: ast.Assign,
        result: ParseResult,
        parent_qname: Optional[str],
        is_class_var: bool = False
    ) -> None:
        """Process variable assignment"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                qname = f"{parent_qname}.{name}" if parent_qname else name
                
                # Skip private variables (single underscore prefix) at module level
                # but keep class variables and constants
                if not is_class_var and name.startswith('_') and not name.startswith('__'):
                    continue
                
                # Determine if it's a constant (ALL_CAPS)
                kind = SymbolKind.CONSTANT if name.isupper() else SymbolKind.VARIABLE
                
                source = self._get_source(node.lineno, node.end_lineno or node.lineno)
                
                symbol = Symbol(
                    name=name,
                    qualified_name=qname,
                    kind=kind,
                    file_path=self._file_path,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    start_column=target.col_offset,
                    source_code=source,
                    parent=parent_qname,
                    language=self.LANGUAGE
                )
                
                result.symbols.append(symbol)
    
    def _process_annotated_assignment(
        self,
        node: ast.AnnAssign,
        result: ParseResult,
        parent_qname: Optional[str],
        is_class_var: bool = False
    ) -> None:
        """Process annotated variable assignment"""
        if isinstance(node.target, ast.Name):
            name = node.target.id
            qname = f"{parent_qname}.{name}" if parent_qname else name
            
            type_annotation = self._get_annotation_str(node.annotation)
            kind = SymbolKind.CONSTANT if name.isupper() else SymbolKind.VARIABLE
            
            source = self._get_source(node.lineno, node.end_lineno or node.lineno)
            
            symbol = Symbol(
                name=name,
                qualified_name=qname,
                kind=kind,
                file_path=self._file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                start_column=node.target.col_offset,
                source_code=source,
                parent=parent_qname,
                type_annotation=type_annotation,
                language=self.LANGUAGE
            )
            
            result.symbols.append(symbol)
    
    def _extract_calls(
        self,
        node: ast.AST,
        caller_qname: str,
        result: ParseResult
    ) -> None:
        """Extract function/method calls from a node"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child.func)
                if call_name:
                    result.dependencies.append(Dependency(
                        from_symbol=caller_qname,
                        to_symbol=self._resolve_name(call_name),
                        dep_type=DependencyType.CALLS,
                        file_path=self._file_path,
                        line=child.lineno if hasattr(child, 'lineno') else 0,
                        context=call_name
                    ))
    
    def _get_call_name(self, node: ast.AST) -> Optional[str]:
        """Get the name of a called function/method"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_call_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_call_name(node.func)
        return None
    
    def _get_decorator_name(self, node: ast.AST) -> str:
        """Get decorator name from node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return str(node)
    
    def _get_annotation_str(self, node: Optional[ast.AST]) -> Optional[str]:
        """Convert type annotation AST to string"""
        if node is None:
            return None
        
        try:
            return ast.unparse(node)
        except Exception:
            # Fallback for older Python versions
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Constant):
                return repr(node.value)
            elif isinstance(node, ast.Subscript):
                value = self._get_annotation_str(node.value)
                slice_val = self._get_annotation_str(node.slice)
                return f"{value}[{slice_val}]"
            elif isinstance(node, ast.Attribute):
                value = self._get_annotation_str(node.value)
                return f"{value}.{node.attr}"
            return None
    
    def _extract_parameters(self, args: ast.arguments) -> List[Dict]:
        """Extract function parameters with types and defaults"""
        params = []
        
        # Calculate default offset
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        default_offset = num_args - num_defaults
        
        for i, arg in enumerate(args.args):
            param = {
                'name': arg.arg,
                'type': self._get_annotation_str(arg.annotation)
            }
            
            # Check for default value
            default_idx = i - default_offset
            if default_idx >= 0 and default_idx < len(args.defaults):
                try:
                    param['default'] = ast.unparse(args.defaults[default_idx])
                except Exception:
                    param['default'] = '...'
            
            params.append(param)
        
        # Add *args
        if args.vararg:
            params.append({
                'name': f"*{args.vararg.arg}",
                'type': self._get_annotation_str(args.vararg.annotation)
            })
        
        # Add keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            param = {
                'name': arg.arg,
                'type': self._get_annotation_str(arg.annotation)
            }
            if i < len(args.kw_defaults) and args.kw_defaults[i]:
                try:
                    param['default'] = ast.unparse(args.kw_defaults[i])
                except Exception:
                    param['default'] = '...'
            params.append(param)
        
        # Add **kwargs
        if args.kwarg:
            params.append({
                'name': f"**{args.kwarg.arg}",
                'type': self._get_annotation_str(args.kwarg.annotation)
            })
        
        return params
    
    def _get_source(self, start_line: int, end_line: int) -> str:
        """Extract source code for line range"""
        if not self._lines:
            return ""
        
        # Adjust for 0-based indexing
        start_idx = max(0, start_line - 1)
        end_idx = min(len(self._lines), end_line)
        
        return '\n'.join(self._lines[start_idx:end_idx])
    
    def _resolve_name(self, name: str) -> str:
        """Resolve a name to its qualified form using import map"""
        parts = name.split('.')
        first = parts[0]
        
        if first in self._import_map:
            resolved = self._import_map[first]
            if len(parts) > 1:
                return f"{resolved}.{'.'.join(parts[1:])}"
            return resolved
        
        # If not in imports, might be local or builtin
        return name
