"""
Document parser for repository knowledge sources.

Indexes lightweight structure from Markdown/text documents so the Context
Engine can retrieve architecture notes, runbooks, and design docs alongside
code.
"""

from pathlib import Path
from typing import Optional, List, Tuple
import re

from .base import BaseParser, ParseResult
from ..symbol_table import Symbol, SymbolKind


class DocumentParser(BaseParser):
    """Parse lightweight structural symbols from docs and text files."""

    LANGUAGE = "document"
    FILE_EXTENSIONS: Tuple[str, ...] = (".md", ".mdx", ".txt", ".rst")

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
        symbols: List[Symbol] = []

        heading_candidates = self._collect_headings(lines)
        if not heading_candidates:
            excerpt = "\n".join(lines[:20]).strip()
            if excerpt:
                symbols.append(
                    Symbol(
                        name=file_path.stem,
                        qualified_name=module_name or file_path.stem,
                        kind=SymbolKind.MODULE,
                        file_path=str(file_path),
                        start_line=1,
                        end_line=min(len(lines), 20) or 1,
                        signature=f"document {file_path.name}",
                        source_code=excerpt,
                        language=result.language,
                    )
                )
        else:
            for index, (line_number, heading_text, level) in enumerate(heading_candidates, start=1):
                section_end = len(lines)
                for next_line, _, _ in heading_candidates[index:]:
                    if next_line > line_number:
                        section_end = next_line - 1
                        break
                excerpt = "\n".join(lines[line_number - 1 : min(section_end, line_number + 16)]).strip()
                slug = self._slugify(heading_text) or f"section_{index}"
                qualified_name = f"{module_name}.{slug}" if module_name else slug
                symbols.append(
                    Symbol(
                        name=heading_text,
                        qualified_name=qualified_name,
                        kind=SymbolKind.MODULE,
                        file_path=str(file_path),
                        start_line=line_number,
                        end_line=max(line_number, min(section_end, line_number + 16)),
                        signature=f"h{level} {heading_text}",
                        source_code=excerpt,
                        language=result.language,
                    )
                )

        result.symbols.extend(symbols)
        return result

    def _language_for(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        if ext in {".md", ".mdx"}:
            return "markdown"
        if ext == ".rst":
            return "rst"
        return "text"

    def _collect_headings(self, lines: List[str]) -> List[Tuple[int, str, int]]:
        headings: List[Tuple[int, str, int]] = []

        for index, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip()
            if not line.strip():
                continue

            markdown_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if markdown_match:
                level = len(markdown_match.group(1))
                text = markdown_match.group(2).strip()
                if text:
                    headings.append((index, text, level))
                continue

            if index < len(lines):
                underline = lines[index].strip()
                if underline and set(underline) <= {"=", "-", "~"} and len(underline) >= max(3, len(line.strip()) // 2):
                    level = 1 if underline[0] == "=" else 2
                    headings.append((index, line.strip(), level))

        return headings

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower())
        return slug.strip("_")
