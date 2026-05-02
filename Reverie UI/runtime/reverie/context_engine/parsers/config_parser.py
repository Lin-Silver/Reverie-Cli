"""
Configuration File Parser for game configuration files

Supports:
- JSON (.json)
- YAML (.yaml, .yml)
- XML (.xml)
- TOML (.toml)
- INI (.ini, .cfg, .conf)
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import time

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind


class ConfigParser(BaseParser):
    """
    Parser for game configuration files.
    
    Extracts configuration keys and values from various formats.
    """
    
    LANGUAGE = "config"
    FILE_EXTENSIONS = ('.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.cfg', '.conf')
    
    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.FILE_EXTENSIONS
    
    def parse_file(self, file_path: Path, content: Optional[str] = None) -> ParseResult:
        start_time = time.time()
        result = ParseResult(
            file_path=str(file_path),
            language=self._get_language(file_path)
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
        
        # Parse based on file extension
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.json':
                self._parse_json(content, result)
            elif ext in {'.yaml', '.yml'}:
                self._parse_yaml(content, result)
            elif ext == '.xml':
                self._parse_xml(content, result)
            elif ext == '.toml':
                self._parse_toml(content, result)
            elif ext in {'.ini', '.cfg', '.conf'}:
                self._parse_ini(content, result)
        except Exception as e:
            result.errors.append(f"Parse error: {str(e)}")
        
        result.parse_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _get_language(self, file_path: Path) -> str:
        """Get specific language based on extension"""
        ext = file_path.suffix.lower()
        
        if ext == '.json':
            return 'json'
        elif ext in {'.yaml', '.yml'}:
            return 'yaml'
        elif ext == '.xml':
            return 'xml'
        elif ext == '.toml':
            return 'toml'
        elif ext in {'.ini', '.cfg', '.conf'}:
            return 'ini'
        
        return 'config'
    
    def _parse_json(self, content: str, result: ParseResult) -> None:
        """Parse JSON configuration"""
        try:
            data = json.loads(content)
            self._extract_from_dict(data, result, prefix="")
        except json.JSONDecodeError as e:
            result.errors.append(f"JSON parse error: {str(e)}")
    
    def _parse_yaml(self, content: str, result: ParseResult) -> None:
        """Parse YAML configuration"""
        try:
            import yaml
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                self._extract_from_dict(data, result, prefix="")
        except ImportError:
            # Fallback to simple key-value extraction if PyYAML not available
            self._parse_simple_key_value(content, result)
        except Exception as e:
            result.errors.append(f"YAML parse error: {str(e)}")
    
    def _parse_xml(self, content: str, result: ParseResult) -> None:
        """Parse XML configuration"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            self._extract_from_xml(root, result, prefix="")
        except ImportError:
            # Fallback to simple tag extraction
            self._parse_simple_xml(content, result)
        except Exception as e:
            result.errors.append(f"XML parse error: {str(e)}")
    
    def _parse_toml(self, content: str, result: ParseResult) -> None:
        """Parse TOML configuration"""
        try:
            import tomli
            data = tomli.loads(content)
            self._extract_from_dict(data, result, prefix="")
        except ImportError:
            # Fallback to simple key-value extraction
            self._parse_simple_key_value(content, result)
        except Exception as e:
            result.errors.append(f"TOML parse error: {str(e)}")
    
    def _parse_ini(self, content: str, result: ParseResult) -> None:
        """Parse INI/CFG configuration"""
        import configparser
        
        try:
            config = configparser.ConfigParser()
            config.read_string(content)
            
            for section in config.sections():
                for key in config[section]:
                    value = config[section][key]
                    qname = f"{self._module_name}.{section}.{key}"
                    
                    # Find line number
                    line_num = self._find_line_number(f"{key}")
                    
                    symbol = Symbol(
                        name=key,
                        qualified_name=qname,
                        kind=SymbolKind.CONSTANT,
                        file_path=self._file_path,
                        start_line=line_num,
                        end_line=line_num,
                        signature=f"{key} = {value}",
                        parent=f"{self._module_name}.{section}",
                        language=result.language
                    )
                    
                    result.symbols.append(symbol)
        
        except Exception as e:
            result.errors.append(f"INI parse error: {str(e)}")
    
    def _extract_from_dict(
        self,
        data: Dict[str, Any],
        result: ParseResult,
        prefix: str,
        parent: Optional[str] = None
    ) -> None:
        """Recursively extract configuration from dictionary"""
        for key, value in data.items():
            qname = f"{self._module_name}.{prefix}{key}" if prefix else f"{self._module_name}.{key}"
            
            # Find line number
            line_num = self._find_line_number(f'"{key}"')
            
            if isinstance(value, dict):
                # Nested configuration
                symbol = Symbol(
                    name=key,
                    qualified_name=qname,
                    kind=SymbolKind.CLASS,  # Treat nested configs as classes
                    file_path=self._file_path,
                    start_line=line_num,
                    end_line=line_num,
                    signature=f"{key}: {{...}}",
                    parent=parent,
                    language=result.language
                )
                result.symbols.append(symbol)
                
                # Recurse into nested dict
                self._extract_from_dict(value, result, f"{prefix}{key}.", qname)
            
            elif isinstance(value, list):
                # Array configuration
                symbol = Symbol(
                    name=key,
                    qualified_name=qname,
                    kind=SymbolKind.VARIABLE,
                    file_path=self._file_path,
                    start_line=line_num,
                    end_line=line_num,
                    signature=f"{key}: [{len(value)} items]",
                    parent=parent,
                    language=result.language
                )
                result.symbols.append(symbol)
            
            else:
                # Simple value
                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:50] + "..."
                
                symbol = Symbol(
                    name=key,
                    qualified_name=qname,
                    kind=SymbolKind.CONSTANT,
                    file_path=self._file_path,
                    start_line=line_num,
                    end_line=line_num,
                    signature=f"{key} = {value_str}",
                    parent=parent,
                    language=result.language
                )
                result.symbols.append(symbol)
    
    def _extract_from_xml(
        self,
        element,
        result: ParseResult,
        prefix: str,
        parent: Optional[str] = None
    ) -> None:
        """Recursively extract configuration from XML element"""
        tag = element.tag
        qname = f"{self._module_name}.{prefix}{tag}" if prefix else f"{self._module_name}.{tag}"
        
        # Find line number (approximate)
        line_num = self._find_line_number(f"<{tag}")
        
        # Extract attributes
        if element.attrib:
            for attr_name, attr_value in element.attrib.items():
                attr_qname = f"{qname}.@{attr_name}"
                
                symbol = Symbol(
                    name=f"@{attr_name}",
                    qualified_name=attr_qname,
                    kind=SymbolKind.CONSTANT,
                    file_path=self._file_path,
                    start_line=line_num,
                    end_line=line_num,
                    signature=f"@{attr_name} = {attr_value}",
                    parent=qname,
                    language=result.language
                )
                result.symbols.append(symbol)
        
        # Extract text content
        if element.text and element.text.strip():
            text_value = element.text.strip()
            if len(text_value) > 50:
                text_value = text_value[:50] + "..."
            
            symbol = Symbol(
                name=tag,
                qualified_name=qname,
                kind=SymbolKind.CONSTANT,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=f"{tag} = {text_value}",
                parent=parent,
                language=result.language
            )
            result.symbols.append(symbol)
        
        # Recurse into children
        for child in element:
            self._extract_from_xml(child, result, f"{prefix}{tag}.", qname)
    
    def _parse_simple_key_value(self, content: str, result: ParseResult) -> None:
        """Simple fallback parser for key-value pairs"""
        # Match patterns like: key: value or key = value
        pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*[:=]\s*(.+)', re.MULTILINE)
        
        for match in pattern.finditer(content):
            key = match.group(1)
            value = match.group(2).strip()
            line_num = content[:match.start()].count('\n') + 1
            
            qname = f"{self._module_name}.{key}"
            
            if len(value) > 50:
                value = value[:50] + "..."
            
            symbol = Symbol(
                name=key,
                qualified_name=qname,
                kind=SymbolKind.CONSTANT,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=f"{key} = {value}",
                language=result.language
            )
            result.symbols.append(symbol)
    
    def _parse_simple_xml(self, content: str, result: ParseResult) -> None:
        """Simple fallback XML parser"""
        # Match XML tags
        pattern = re.compile(r'<([a-zA-Z_][a-zA-Z0-9_-]*)[^>]*>([^<]*)</\1>', re.MULTILINE)
        
        for match in pattern.finditer(content):
            tag = match.group(1)
            value = match.group(2).strip()
            line_num = content[:match.start()].count('\n') + 1
            
            if not value:
                continue
            
            qname = f"{self._module_name}.{tag}"
            
            if len(value) > 50:
                value = value[:50] + "..."
            
            symbol = Symbol(
                name=tag,
                qualified_name=qname,
                kind=SymbolKind.CONSTANT,
                file_path=self._file_path,
                start_line=line_num,
                end_line=line_num,
                signature=f"{tag} = {value}",
                language=result.language
            )
            result.symbols.append(symbol)
    
    def _find_line_number(self, search_str: str) -> int:
        """Find line number containing search string"""
        for i, line in enumerate(self._lines, 1):
            if search_str in line:
                return i
        return 1
