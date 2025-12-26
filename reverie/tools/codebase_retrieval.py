"""
Codebase Retrieval Tool - Primary tool for Context Engine access

This is THE most important tool for reducing model hallucinations.
The system prompt instructs the model to call this tool BEFORE any edits.

Provides:
- Symbol lookup and search
- Dependency analysis
- File content retrieval
- Code structure exploration
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from .base import BaseTool, ToolResult


class CodebaseRetrievalTool(BaseTool):
    """
    Tool for querying the codebase via Context Engine.
    
    This tool enables the AI to understand the codebase before making changes,
    significantly reducing hallucinations and improving code quality.
    """
    
    name = "codebase-retrieval"
    
    description = """Query the codebase for detailed information about symbols, files, and code structure.

IMPORTANT: You MUST call this tool before making any code edits to understand:
- The exact implementation of functions/classes you want to modify
- Dependencies and relationships between symbols
- The correct signatures and types
- Existing patterns in the codebase

Query types:
- symbol: Get detailed info about a specific function, class, or variable
- file: Get the structure and contents of a file
- search: Search for symbols matching a pattern
- dependencies: Get what a symbol depends on or what depends on it

Examples:
- Query a function: {"query_type": "symbol", "query": "MyClass.my_method"}
- Search for classes: {"query_type": "search", "query": "Controller", "filter_kind": "class"}
- Get file structure: {"query_type": "file", "query": "src/utils/helpers.py"}
- Find dependencies: {"query_type": "dependencies", "query": "process_data", "direction": "outgoing"}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["symbol", "file", "search", "dependencies", "outline"],
                "description": "Type of query to perform"
            },
            "query": {
                "type": "string",
                "description": "Symbol name, file path, or search pattern"
            },
            "include_source": {
                "type": "boolean",
                "description": "Include full source code in results (default: true)",
                "default": True
            },
            "include_dependencies": {
                "type": "boolean",
                "description": "Include dependency information (default: true)",
                "default": True
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth for dependency traversal (default: 2)",
                "default": 2
            },
            "filter_kind": {
                "type": "string",
                "enum": ["class", "function", "method", "variable", "interface", "struct", "enum", "all"],
                "description": "Filter results by symbol kind",
                "default": "all"
            },
            "direction": {
                "type": "string",
                "enum": ["outgoing", "incoming", "both"],
                "description": "For dependencies query: outgoing (what it uses) or incoming (what uses it)",
                "default": "outgoing"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 20)",
                "default": 20
            }
        },
        "required": ["query_type", "query"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._context_engine = None
        self._retriever = None
    
    def _get_retriever(self):
        """Get or create context retriever"""
        if self._retriever is None and self.context:
            self._retriever = self.context.get('retriever')
        return self._retriever
    
    def execute(self, **kwargs) -> ToolResult:
        query_type = kwargs.get('query_type')
        query = kwargs.get('query', '')
        include_source = kwargs.get('include_source', True)
        include_dependencies = kwargs.get('include_dependencies', True)
        max_depth = kwargs.get('max_depth', 2)
        filter_kind = kwargs.get('filter_kind', 'all')
        direction = kwargs.get('direction', 'outgoing')
        limit = kwargs.get('limit', 20)
        
        retriever = self._get_retriever()
        
        if not retriever:
            return ToolResult.fail(
                "Context Engine not initialized. The codebase has not been indexed yet."
            )
        
        try:
            if query_type == "symbol":
                return self._query_symbol(
                    retriever, query, include_source, include_dependencies, max_depth
                )
            
            elif query_type == "file":
                return self._query_file(retriever, query, include_source)
            
            elif query_type == "search":
                return self._search_symbols(retriever, query, filter_kind, limit)
            
            elif query_type == "dependencies":
                return self._query_dependencies(
                    retriever, query, direction, max_depth, limit
                )
            
            elif query_type == "outline":
                return self._query_outline(retriever, query)
            
            else:
                return ToolResult.fail(f"Unknown query type: {query_type}")
        
        except Exception as e:
            return ToolResult.fail(f"Error executing query: {str(e)}")
    
    def _query_symbol(
        self,
        retriever,
        query: str,
        include_source: bool,
        include_dependencies: bool,
        max_depth: int
    ) -> ToolResult:
        """Query a specific symbol"""
        result = retriever.retrieve_symbol(
            query,
            include_dependencies=include_dependencies,
            max_depth=max_depth
        )
        
        if not result:
            return ToolResult.fail(
                f"Symbol '{query}' not found in codebase. "
                "Try using search to find similar symbols."
            )
        
        output_parts = []
        
        # Main symbol info
        sym = result.symbol
        output_parts.append(f"# {sym.kind.name}: {sym.qualified_name}")
        output_parts.append(f"File: {sym.file_path}:{sym.start_line}-{sym.end_line}")
        output_parts.append(f"Language: {sym.language}")
        
        if sym.signature:
            output_parts.append(f"\n## Signature\n```\n{sym.signature}\n```")
        
        if sym.docstring:
            output_parts.append(f"\n## Documentation\n{sym.docstring}")
        
        if include_source and sym.source_code:
            output_parts.append(f"\n## Source Code\n```{sym.language}\n{sym.source_code}\n```")
        
        # Parent
        if result.parent:
            output_parts.append(f"\n## Parent\n- {result.parent.kind.name}: {result.parent.qualified_name}")
        
        # Children
        if result.children:
            output_parts.append("\n## Children")
            for child in result.children:
                line = f"- {child.kind.name}: {child.name}"
                if child.signature:
                    line += f"\n  {child.signature}"
                output_parts.append(line)
        
        # Dependencies
        if include_dependencies and result.dependencies:
            output_parts.append("\n## Dependencies (what it uses)")
            for dep in result.dependencies:
                dep_info = f"- {dep.kind.name}: {dep.qualified_name}"
                if dep.file_path != sym.file_path:
                    dep_info += f" ({dep.file_path})"
                output_parts.append(dep_info)
                if include_source and dep.signature:
                    output_parts.append(f"  ```\n  {dep.signature}\n  ```")
        
        # Dependents
        if result.dependents:
            output_parts.append("\n## Used by")
            for dep in result.dependents:
                output_parts.append(f"- {dep.qualified_name} ({dep.file_path}:{dep.start_line})")
        
        return ToolResult.ok(
            '\n'.join(output_parts),
            data={
                'symbol': sym.qualified_name,
                'file': sym.file_path,
                'line': sym.start_line
            }
        )
    
    def _query_file(
        self,
        retriever,
        file_path: str,
        include_source: bool
    ) -> ToolResult:
        """Query file structure and contents"""
        symbols = retriever.get_file_outline(file_path)
        
        if not symbols:
            # Try to find the file
            return ToolResult.fail(
                f"No symbols found in '{file_path}'. "
                "The file may not exist or may not be indexed."
            )
        
        output_parts = []
        output_parts.append(f"# File: {file_path}")
        output_parts.append(f"Symbols found: {len(symbols)}")
        output_parts.append("")
        
        # Group by kind
        by_kind = {}
        for sym in symbols:
            kind = sym.kind.name
            if kind not in by_kind:
                by_kind[kind] = []
            by_kind[kind].append(sym)
        
        for kind, syms in by_kind.items():
            output_parts.append(f"\n## {kind}s ({len(syms)})")
            for sym in syms:
                line = f"- **{sym.name}** (line {sym.start_line})"
                if sym.signature:
                    output_parts.append(line)
                    output_parts.append(f"  ```\n  {sym.signature}\n  ```")
                else:
                    output_parts.append(line)
        
        return ToolResult.ok(
            '\n'.join(output_parts),
            data={'file': file_path, 'symbol_count': len(symbols)}
        )
    
    def _search_symbols(
        self,
        retriever,
        pattern: str,
        filter_kind: str,
        limit: int
    ) -> ToolResult:
        """Search for symbols matching a pattern"""
        from ..context_engine.symbol_table import SymbolKind
        
        # Convert filter to SymbolKind list
        kinds = None
        if filter_kind != "all":
            kind_map = {
                "class": [SymbolKind.CLASS],
                "function": [SymbolKind.FUNCTION],
                "method": [SymbolKind.METHOD],
                "variable": [SymbolKind.VARIABLE, SymbolKind.CONSTANT],
                "interface": [SymbolKind.INTERFACE],
                "struct": [SymbolKind.STRUCT],
                "enum": [SymbolKind.ENUM]
            }
            kinds = kind_map.get(filter_kind)
        
        results = retriever.search(pattern, kinds=kinds, limit=limit)
        
        if not results:
            return ToolResult.ok(
                f"No symbols found matching '{pattern}'.",
                data={'count': 0}
            )
        
        output_parts = []
        output_parts.append(f"# Search results for: {pattern}")
        output_parts.append(f"Found {len(results)} symbols")
        output_parts.append("")
        
        for sym in results:
            line = f"- **{sym.kind.name}** `{sym.qualified_name}`"
            output_parts.append(line)
            output_parts.append(f"  File: {sym.file_path}:{sym.start_line}")
            if sym.signature:
                output_parts.append(f"  Signature: `{sym.signature}`")
        
        return ToolResult.ok(
            '\n'.join(output_parts),
            data={'count': len(results)}
        )
    
    def _query_dependencies(
        self,
        retriever,
        symbol: str,
        direction: str,
        max_depth: int,
        limit: int
    ) -> ToolResult:
        """Query symbol dependencies"""
        symbol_ctx = retriever.retrieve_symbol(
            symbol,
            include_dependencies=True,
            include_dependents=(direction in ["incoming", "both"]),
            max_depth=max_depth
        )
        
        if not symbol_ctx:
            return ToolResult.fail(f"Symbol '{symbol}' not found.")
        
        output_parts = []
        output_parts.append(f"# Dependencies for: {symbol_ctx.symbol.qualified_name}")
        
        if direction in ["outgoing", "both"] and symbol_ctx.dependencies:
            output_parts.append(f"\n## Outgoing (what it depends on): {len(symbol_ctx.dependencies)}")
            for dep in symbol_ctx.dependencies[:limit]:
                output_parts.append(f"- {dep.kind.name}: {dep.qualified_name}")
                if dep.file_path:
                    output_parts.append(f"  Location: {dep.file_path}:{dep.start_line}")
        
        if direction in ["incoming", "both"] and symbol_ctx.dependents:
            output_parts.append(f"\n## Incoming (what depends on it): {len(symbol_ctx.dependents)}")
            for dep in symbol_ctx.dependents[:limit]:
                output_parts.append(f"- {dep.kind.name}: {dep.qualified_name}")
                if dep.file_path:
                    output_parts.append(f"  Location: {dep.file_path}:{dep.start_line}")
        
        if symbol_ctx.call_chain:
            output_parts.append(f"\n## Call chain")
            output_parts.append(" -> ".join(symbol_ctx.call_chain))
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _query_outline(self, retriever, file_path: str) -> ToolResult:
        """Get outline/structure of a file"""
        return self._query_file(retriever, file_path, include_source=False)
