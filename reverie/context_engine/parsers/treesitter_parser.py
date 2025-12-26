"""
Tree-sitter based multi-language parser

Supports:
- JavaScript / TypeScript
- C / C++
- C#
- Rust
- Go
- Java
- Zig
- HTML / CSS

Tree-sitter provides fast, incremental parsing with concrete syntax trees.
This parser uses tree-sitter queries to extract symbols efficiently.
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
import time
import re

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind, Reference
from ..dependency_graph import Dependency, DependencyType


# Language configurations
SUPPORTED_LANGUAGES: Dict[str, Dict] = {
    'javascript': {
        'extensions': ('.js', '.mjs', '.cjs'),
        'tree_sitter_lang': 'javascript'
    },
    'typescript': {
        'extensions': ('.ts', '.tsx'),
        'tree_sitter_lang': 'typescript'
    },
    'c': {
        'extensions': ('.c', '.h'),
        'tree_sitter_lang': 'c'
    },
    'cpp': {
        'extensions': ('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.hxx', '.h'),
        'tree_sitter_lang': 'cpp'
    },
    'csharp': {
        'extensions': ('.cs',),
        'tree_sitter_lang': 'c_sharp'
    },
    'rust': {
        'extensions': ('.rs',),
        'tree_sitter_lang': 'rust'
    },
    'go': {
        'extensions': ('.go',),
        'tree_sitter_lang': 'go'
    },
    'java': {
        'extensions': ('.java',),
        'tree_sitter_lang': 'java'
    },
    'zig': {
        'extensions': ('.zig',),
        'tree_sitter_lang': 'zig'
    },
    'html': {
        'extensions': ('.html', '.htm'),
        'tree_sitter_lang': 'html'
    },
    'css': {
        'extensions': ('.css',),
        'tree_sitter_lang': 'css'
    }
}


@dataclass
class TreeSitterConfig:
    """Configuration for a tree-sitter language"""
    language: str
    parser: Any = None
    query_functions: str = ""
    query_classes: str = ""
    query_imports: str = ""


class TreeSitterParser(BaseParser):
    """
    Multi-language parser using tree-sitter.
    
    Falls back to regex-based parsing if tree-sitter is not available.
    This ensures the Context Engine works even without tree-sitter installed.
    """
    
    LANGUAGE = "multi"
    FILE_EXTENSIONS = tuple(
        ext for lang_config in SUPPORTED_LANGUAGES.values()
        for ext in lang_config['extensions']
    )
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self._parsers: Dict[str, Any] = {}
        self._tree_sitter_available = False
        self._init_tree_sitter()
    
    def _init_tree_sitter(self) -> None:
        """Initialize tree-sitter parsers if available"""
        try:
            import tree_sitter
            # Try to import language bindings
            self._tree_sitter_available = True
            self._ts = tree_sitter
            
            # Initialize parsers lazily
            self._parser_cache = {}
            
        except ImportError:
            self._tree_sitter_available = False
            # Will use regex fallback
    
    def _get_parser(self, language: str):
        """Get or create parser for a language"""
        if not self._tree_sitter_available:
            return None
        
        if language in self._parser_cache:
            return self._parser_cache[language]
        
        try:
            parser = self._ts.Parser()
            
            # Try to load language
            lang_name = SUPPORTED_LANGUAGES[language]['tree_sitter_lang']
            
            # Dynamic import of language
            if language == 'javascript':
                import tree_sitter_javascript as ts_lang
            elif language == 'typescript':
                import tree_sitter_typescript as ts_lang
            elif language == 'python':
                import tree_sitter_python as ts_lang
            elif language == 'c':
                import tree_sitter_c as ts_lang
            elif language == 'cpp':
                import tree_sitter_cpp as ts_lang
            elif language == 'rust':
                import tree_sitter_rust as ts_lang
            elif language == 'go':
                import tree_sitter_go as ts_lang
            elif language == 'java':
                import tree_sitter_java as ts_lang
            elif language == 'csharp':
                import tree_sitter_c_sharp as ts_lang
            elif language == 'html':
                import tree_sitter_html as ts_lang
            elif language == 'css':
                import tree_sitter_css as ts_lang
            else:
                return None
            
            lang = ts_lang.language()
            parser.language = lang
            self._parser_cache[language] = parser
            return parser
            
        except ImportError:
            return None
        except Exception:
            return None
    
    def can_parse(self, file_path: Path) -> bool:
        ext = file_path.suffix.lower()
        return ext in self.FILE_EXTENSIONS
    
    def _detect_language(self, file_path: Path) -> Optional[str]:
        """Detect language from file extension"""
        ext = file_path.suffix.lower()
        for lang, config in SUPPORTED_LANGUAGES.items():
            if ext in config['extensions']:
                return lang
        return None
    
    def parse_file(self, file_path: Path, content: Optional[str] = None) -> ParseResult:
        start_time = time.time()
        
        language = self._detect_language(file_path)
        if not language:
            return ParseResult(
                file_path=str(file_path),
                language="unknown",
                errors=["Unknown file type"]
            )
        
        result = ParseResult(
            file_path=str(file_path),
            language=language
        )
        
        # Read content if not provided
        if content is None:
            content = self.read_file(file_path)
            if content is None:
                result.errors.append(f"Could not read file: {file_path}")
                return result
        
        self._content = content
        self._lines = content.split('\n')
        self._file_path = str(file_path)
        self._module_name = self.get_module_name(file_path)
        
        # Try tree-sitter first
        parser = self._get_parser(language)
        if parser:
            try:
                self._parse_with_tree_sitter(parser, content, language, result)
            except Exception as e:
                result.errors.append(f"Tree-sitter error: {e}")
                # Fall back to regex
                self._parse_with_regex(content, language, result)
        else:
            # Use regex fallback
            self._parse_with_regex(content, language, result)
        
        result.parse_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _parse_with_tree_sitter(
        self,
        parser,
        content: str,
        language: str,
        result: ParseResult
    ) -> None:
        """Parse using tree-sitter"""
        tree = parser.parse(content.encode('utf-8'))
        root = tree.root_node
        
        # Walk the tree and extract symbols
        self._walk_tree(root, language, result, parent_qname=self._module_name)
    
    def _walk_tree(
        self,
        node,
        language: str,
        result: ParseResult,
        parent_qname: str
    ) -> None:
        """Recursively walk tree-sitter AST"""
        node_type = node.type
        
        # Language-specific extraction
        if language in ('javascript', 'typescript'):
            self._extract_js_ts(node, language, result, parent_qname)
        elif language in ('c', 'cpp'):
            self._extract_c_cpp(node, language, result, parent_qname)
        elif language == 'csharp':
            self._extract_csharp(node, result, parent_qname)
        elif language == 'rust':
            self._extract_rust(node, result, parent_qname)
        elif language == 'go':
            self._extract_go(node, result, parent_qname)
        elif language == 'java':
            self._extract_java(node, result, parent_qname)
        elif language == 'zig':
            self._extract_zig(node, result, parent_qname)
        elif language == 'html':
            self._extract_html(node, result, parent_qname)
        elif language == 'css':
            self._extract_css(node, result, parent_qname)
        
        # Recurse to children
        for child in node.children:
            self._walk_tree(child, language, result, parent_qname)
    
    def _extract_js_ts(self, node, language: str, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from JavaScript/TypeScript"""
        node_type = node.type
        
        if node_type == 'function_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'class_declaration':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_class_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'method_definition':
            name = self._get_child_text(node, 'name', 'property_identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, language, is_method=True)
        
        elif node_type == 'arrow_function':
            # Check if assigned to a variable
            pass  # Will be caught by variable_declarator
        
        elif node_type == 'variable_declarator':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                # Check if it's a function assignment
                value = node.child_by_field_name('value')
                if value and value.type in ('arrow_function', 'function'):
                    self._add_function_symbol(node, name, parent_qname, result, language)
                else:
                    self._add_variable_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'interface_declaration' and language == 'typescript':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_interface_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'type_alias_declaration' and language == 'typescript':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_type_alias_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'import_statement':
            self._extract_js_import(node, result)
    
    def _extract_c_cpp(self, node, language: str, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from C/C++"""
        node_type = node.type
        
        if node_type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            name = self._get_declarator_name(declarator)
            if name:
                self._add_function_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'class_specifier':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_class_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'struct_specifier':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_struct_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'enum_specifier':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_enum_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'namespace_definition':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_namespace_symbol(node, name, parent_qname, result, language)
        
        elif node_type == 'preproc_def':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_macro_symbol(node, name, parent_qname, result, language)
    
    def _extract_csharp(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from C#"""
        node_type = node.type
        
        if node_type == 'method_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'csharp', is_method=True)
        
        elif node_type == 'class_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_class_symbol(node, name, parent_qname, result, 'csharp')
        
        elif node_type == 'interface_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_interface_symbol(node, name, parent_qname, result, 'csharp')
        
        elif node_type == 'struct_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_struct_symbol(node, name, parent_qname, result, 'csharp')
        
        elif node_type == 'enum_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_enum_symbol(node, name, parent_qname, result, 'csharp')
        
        elif node_type == 'namespace_declaration':
            name = self._get_namespace_name(node)
            if name:
                self._add_namespace_symbol(node, name, parent_qname, result, 'csharp')
        
        elif node_type == 'property_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_property_symbol(node, name, parent_qname, result, 'csharp')
    
    def _extract_rust(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from Rust"""
        node_type = node.type
        
        if node_type == 'function_item':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'rust')
        
        elif node_type == 'struct_item':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_struct_symbol(node, name, parent_qname, result, 'rust')
        
        elif node_type == 'enum_item':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_enum_symbol(node, name, parent_qname, result, 'rust')
        
        elif node_type == 'trait_item':
            name = self._get_child_text(node, 'name', 'type_identifier')
            if name:
                self._add_trait_symbol(node, name, parent_qname, result, 'rust')
        
        elif node_type == 'impl_item':
            # Implementation block
            trait_name = None
            type_name = None
            for child in node.children:
                if child.type == 'type_identifier':
                    if type_name is None:
                        type_name = child.text.decode('utf-8')
                    else:
                        trait_name = type_name
                        type_name = child.text.decode('utf-8')
            # Don't create symbol, but children (methods) will be extracted
        
        elif node_type == 'mod_item':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_module_symbol(node, name, parent_qname, result, 'rust')
        
        elif node_type == 'macro_definition':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_macro_symbol(node, name, parent_qname, result, 'rust')
    
    def _extract_go(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from Go"""
        node_type = node.type
        
        if node_type == 'function_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'go')
        
        elif node_type == 'method_declaration':
            name = self._get_child_text(node, 'name', 'field_identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'go', is_method=True)
        
        elif node_type == 'type_declaration':
            for child in node.children:
                if child.type == 'type_spec':
                    type_name = self._get_child_text(child, 'name', 'type_identifier')
                    type_def = child.child_by_field_name('type')
                    if type_name and type_def:
                        if type_def.type == 'struct_type':
                            self._add_struct_symbol(child, type_name, parent_qname, result, 'go')
                        elif type_def.type == 'interface_type':
                            self._add_interface_symbol(child, type_name, parent_qname, result, 'go')
                        else:
                            self._add_type_alias_symbol(child, type_name, parent_qname, result, 'go')
    
    def _extract_java(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from Java"""
        node_type = node.type
        
        if node_type == 'method_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'java', is_method=True)
        
        elif node_type == 'class_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_class_symbol(node, name, parent_qname, result, 'java')
        
        elif node_type == 'interface_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_interface_symbol(node, name, parent_qname, result, 'java')
        
        elif node_type == 'enum_declaration':
            name = self._get_child_text(node, 'name', 'identifier')
            if name:
                self._add_enum_symbol(node, name, parent_qname, result, 'java')
    
    def _extract_zig(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract symbols from Zig"""
        node_type = node.type
        
        if node_type == 'FnDecl':
            # Zig function declaration
            name = None
            for child in node.children:
                if child.type == 'IDENTIFIER':
                    name = child.text.decode('utf-8')
                    break
            if name:
                self._add_function_symbol(node, name, parent_qname, result, 'zig')
        
        elif node_type == 'VarDecl':
            # Zig variable/constant declaration
            name = None
            is_const = False
            for child in node.children:
                if child.type == 'KEYWORD_const':
                    is_const = True
                elif child.type == 'IDENTIFIER':
                    name = child.text.decode('utf-8')
                    break
            if name:
                if is_const:
                    self._add_constant_symbol(node, name, parent_qname, result, 'zig')
                else:
                    self._add_variable_symbol(node, name, parent_qname, result, 'zig')
    
    def _extract_html(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract elements from HTML"""
        node_type = node.type
        
        if node_type == 'element':
            # Get tag name
            start_tag = node.child_by_field_name('tag_name')
            if start_tag:
                tag_name = start_tag.text.decode('utf-8') if start_tag.text else None
                if tag_name:
                    # Get id attribute if present
                    attrs = {}
                    for child in node.children:
                        if child.type == 'start_tag':
                            for attr in child.children:
                                if attr.type == 'attribute':
                                    attr_name = self._get_child_text(attr, 'attribute_name', 'attribute_name')
                                    attr_value = self._get_child_text(attr, 'attribute_value', 'quoted_attribute_value')
                                    if attr_name and attr_value:
                                        attrs[attr_name] = attr_value.strip('"\'')
                    
                    if 'id' in attrs:
                        self._add_html_element_symbol(node, attrs['id'], parent_qname, result, tag_name)
    
    def _extract_css(self, node, result: ParseResult, parent_qname: str) -> None:
        """Extract selectors from CSS"""
        node_type = node.type
        
        if node_type == 'rule_set':
            selectors = []
            for child in node.children:
                if child.type == 'selectors':
                    selectors_text = child.text.decode('utf-8') if child.text else ''
                    selectors = [s.strip() for s in selectors_text.split(',')]
            
            for selector in selectors:
                if selector:
                    self._add_css_selector_symbol(node, selector, parent_qname, result)
    
    # Helper methods for adding symbols
    def _add_function_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult,
        language: str, is_method: bool = False
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.METHOD if is_method else SymbolKind.FUNCTION,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_class_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.CLASS,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_interface_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.INTERFACE,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_struct_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.STRUCT,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_enum_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.ENUM,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_trait_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.TRAIT,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_namespace_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.NAMESPACE,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
                            source_code=self._get_node_text(node),  # No limit for namespaces            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_module_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.MODULE,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_macro_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.MACRO,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_variable_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.VARIABLE,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_constant_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.CONSTANT,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_property_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.PROPERTY,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_type_alias_symbol(
        self, node, name: str, parent_qname: str, result: ParseResult, language: str
    ) -> None:
        qname = f"{parent_qname}.{name}" if parent_qname else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=SymbolKind.TYPE_ALIAS,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            parent=parent_qname if parent_qname != self._module_name else None,
            language=language
        )
        result.symbols.append(symbol)
    
    def _add_html_element_symbol(
        self, node, element_id: str, parent_qname: str, result: ParseResult, tag_name: str
    ) -> None:
        qname = f"{parent_qname}.#{element_id}" if parent_qname else f"#{element_id}"
        
        symbol = Symbol(
            name=element_id,
            qualified_name=qname,
            kind=SymbolKind.HTML_ELEMENT,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"<{tag_name} id=\"{element_id}\">",
            language='html'
        )
        result.symbols.append(symbol)
    
    def _add_css_selector_symbol(
        self, node, selector: str, parent_qname: str, result: ParseResult
    ) -> None:
        qname = f"{parent_qname}.{selector}" if parent_qname else selector
        
        symbol = Symbol(
            name=selector,
            qualified_name=qname,
            kind=SymbolKind.CSS_SELECTOR,
            file_path=self._file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=self._get_node_text(node),
            language='css'
        )
        result.symbols.append(symbol)
    
    # Utility methods
    def _get_child_text(self, node, field_name: str, fallback_type: str) -> Optional[str]:
        """Get text from a child node by field name or type"""
        child = node.child_by_field_name(field_name)
        if child:
            return child.text.decode('utf-8') if child.text else None
        
        # Fallback: search by type
        for c in node.children:
            if c.type == fallback_type:
                return c.text.decode('utf-8') if c.text else None
        
        return None
    
    def _get_declarator_name(self, node) -> Optional[str]:
        """Extract function name from C/C++ declarator"""
        if node is None:
            return None
        
        if node.type == 'identifier':
            return node.text.decode('utf-8') if node.text else None
        elif node.type == 'function_declarator':
            return self._get_declarator_name(node.child_by_field_name('declarator'))
        elif node.type == 'pointer_declarator':
            return self._get_declarator_name(node.child_by_field_name('declarator'))
        
        for child in node.children:
            result = self._get_declarator_name(child)
            if result:
                return result
        
        return None
    
    def _get_namespace_name(self, node) -> Optional[str]:
        """Get namespace name for C#"""
        for child in node.children:
            if child.type == 'qualified_name':
                return child.text.decode('utf-8') if child.text else None
            elif child.type == 'identifier':
                return child.text.decode('utf-8') if child.text else None
        return None
    
    def _get_node_text(self, node) -> str:
        """Get source text for a node"""
        if node.text:
            return node.text.decode('utf-8')
        
        start_line = node.start_point[0]
        end_line = node.end_point[0]
        
        if start_line == end_line:
            return self._lines[start_line][node.start_point[1]:node.end_point[1]]
        
        lines = self._lines[start_line:end_line + 1]
        if lines:
            lines[0] = lines[0][node.start_point[1]:]
            lines[-1] = lines[-1][:node.end_point[1]]
        
        return '\n'.join(lines)
    
    def _extract_js_import(self, node, result: ParseResult) -> None:
        """Extract import statement from JS/TS"""
        source = node.text.decode('utf-8') if node.text else ''
        
        # Parse import statement
        import_info = {
            'line': node.start_point[0] + 1,
            'source': source
        }
        
        result.imports.append(import_info)
    
    # Regex fallback parsing
    def _parse_with_regex(self, content: str, language: str, result: ParseResult) -> None:
        """Fallback parsing using regex when tree-sitter is not available"""
        
        if language in ('javascript', 'typescript'):
            self._regex_parse_js_ts(content, language, result)
        elif language in ('c', 'cpp'):
            self._regex_parse_c_cpp(content, language, result)
        elif language == 'csharp':
            self._regex_parse_csharp(content, result)
        elif language == 'rust':
            self._regex_parse_rust(content, result)
        elif language == 'go':
            self._regex_parse_go(content, result)
        elif language == 'java':
            self._regex_parse_java(content, result)
        elif language == 'html':
            self._regex_parse_html(content, result)
        elif language == 'css':
            self._regex_parse_css(content, result)
    
    def _regex_parse_js_ts(self, content: str, language: str, result: ParseResult) -> None:
        """Regex-based parsing for JavaScript/TypeScript"""
        lines = content.split('\n')
        
        # Function patterns
        func_patterns = [
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            r'(?:const|let|var)\s+(\w+)\s*=\s*function\s*\(',
        ]
        
        # Class pattern
        class_pattern = r'(?:export\s+)?class\s+(\w+)'
        
        # Interface pattern (TypeScript)
        interface_pattern = r'(?:export\s+)?interface\s+(\w+)'
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Check for functions
            for pattern in func_patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    self._add_regex_symbol(name, SymbolKind.FUNCTION, line_num, language, result)
                    break
            
            # Check for classes
            match = re.search(class_pattern, line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.CLASS, line_num, language, result)
            
            # Check for interfaces (TypeScript)
            if language == 'typescript':
                match = re.search(interface_pattern, line)
                if match:
                    self._add_regex_symbol(match.group(1), SymbolKind.INTERFACE, line_num, language, result)
    
    def _regex_parse_c_cpp(self, content: str, language: str, result: ParseResult) -> None:
        """Regex-based parsing for C/C++"""
        lines = content.split('\n')
        
        # Function pattern (simplified)
        func_pattern = r'^\s*(?:static\s+)?(?:inline\s+)?(?:\w+\s+)+(\w+)\s*\([^;]*$'
        
        # Class/struct pattern
        class_pattern = r'^\s*(?:class|struct)\s+(\w+)'
        
        # Namespace pattern
        namespace_pattern = r'^\s*namespace\s+(\w+)'
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            match = re.search(func_pattern, line)
            if match and not line.strip().endswith(';'):
                self._add_regex_symbol(match.group(1), SymbolKind.FUNCTION, line_num, language, result)
            
            match = re.search(class_pattern, line)
            if match:
                kind = SymbolKind.CLASS if 'class' in line else SymbolKind.STRUCT
                self._add_regex_symbol(match.group(1), kind, line_num, language, result)
            
            match = re.search(namespace_pattern, line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.NAMESPACE, line_num, language, result)
    
    def _regex_parse_csharp(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for C#"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Classes
            match = re.search(r'(?:public|private|internal|protected)?\s*(?:static\s+)?(?:partial\s+)?class\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.CLASS, line_num, 'csharp', result)
            
            # Interfaces
            match = re.search(r'(?:public|private|internal)?\s*interface\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.INTERFACE, line_num, 'csharp', result)
            
            # Methods
            match = re.search(r'(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?(?:\w+)\s+(\w+)\s*\(', line)
            if match and not any(kw in line for kw in ['class ', 'interface ', 'struct ']):
                self._add_regex_symbol(match.group(1), SymbolKind.METHOD, line_num, 'csharp', result)
    
    def _regex_parse_rust(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for Rust"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Functions
            match = re.search(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.FUNCTION, line_num, 'rust', result)
            
            # Structs
            match = re.search(r'(?:pub\s+)?struct\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.STRUCT, line_num, 'rust', result)
            
            # Enums
            match = re.search(r'(?:pub\s+)?enum\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.ENUM, line_num, 'rust', result)
            
            # Traits
            match = re.search(r'(?:pub\s+)?trait\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.TRAIT, line_num, 'rust', result)
    
    def _regex_parse_go(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for Go"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Functions
            match = re.search(r'func\s+(\w+)\s*\(', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.FUNCTION, line_num, 'go', result)
            
            # Methods
            match = re.search(r'func\s+\([^)]+\)\s+(\w+)\s*\(', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.METHOD, line_num, 'go', result)
            
            # Structs
            match = re.search(r'type\s+(\w+)\s+struct\s*\{', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.STRUCT, line_num, 'go', result)
            
            # Interfaces
            match = re.search(r'type\s+(\w+)\s+interface\s*\{', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.INTERFACE, line_num, 'go', result)
    
    def _regex_parse_java(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for Java"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Classes
            match = re.search(r'(?:public|private|protected)?\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.CLASS, line_num, 'java', result)
            
            # Interfaces
            match = re.search(r'(?:public|private)?\s*interface\s+(\w+)', line)
            if match:
                self._add_regex_symbol(match.group(1), SymbolKind.INTERFACE, line_num, 'java', result)
            
            # Methods
            match = re.search(r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+)\s+(\w+)\s*\(', line)
            if match and not any(kw in line for kw in ['class ', 'interface ']):
                self._add_regex_symbol(match.group(1), SymbolKind.METHOD, line_num, 'java', result)
    
    def _regex_parse_html(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for HTML"""
        # Find elements with id attributes
        pattern = r'<(\w+)[^>]*\bid\s*=\s*["\']([^"\']+)["\']'
        
        for match in re.finditer(pattern, content):
            tag_name = match.group(1)
            element_id = match.group(2)
            
            # Calculate line number
            line_num = content[:match.start()].count('\n') + 1
            
            symbol = Symbol(
                name=element_id,
                qualified_name=f"#{element_id}",
                kind=SymbolKind.HTML_ELEMENT,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=f"<{tag_name} id=\"{element_id}\">",
                language='html'
            )
            result.symbols.append(symbol)
    
    def _regex_parse_css(self, content: str, result: ParseResult) -> None:
        """Regex-based parsing for CSS"""
        # Find CSS selectors
        pattern = r'([^{]+)\s*\{'
        
        for match in re.finditer(pattern, content):
            selector = match.group(1).strip()
            
            # Skip empty or malformed selectors
            if not selector or selector.startswith('/*'):
                continue
            
            # Calculate line number
            line_num = content[:match.start()].count('\n') + 1
            
            symbol = Symbol(
                name=selector,
                qualified_name=selector,
                kind=SymbolKind.CSS_SELECTOR,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                language='css'
            )
            result.symbols.append(symbol)
    
    def _add_regex_symbol(
        self, name: str, kind: SymbolKind, line: int, language: str, result: ParseResult
    ) -> None:
        """Add a symbol found via regex parsing"""
        qname = f"{self._module_name}.{name}" if self._module_name else name
        
        symbol = Symbol(
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=self._file_path,
            start_line=line,
            end_line=line,
            source_code=self._lines[line - 1] if line <= len(self._lines) else "",
            language=language
        )
        result.symbols.append(symbol)
