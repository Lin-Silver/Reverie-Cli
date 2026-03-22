"""
Markdown Formatter - Gemini-inspired terminal rendering for Reverie.

This module keeps the Dreamscape palette but renders markdown as structured
terminal blocks so model output feels closer to a modern agent TUI:
- fenced code blocks become syntax-highlighted previews
- tables become real terminal tables
- lists, quotes, and headings are rendered as distinct blocks
- inline emphasis is still preserved for normal text
"""

from __future__ import annotations

import re
from typing import List, Optional

from rich import box
from rich.console import Console, Group, RenderableType
from rich.padding import Padding
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .theme import DECO, THEME


COLORS = {
    "h1": THEME.PINK_GLOW,
    "h2": THEME.PINK_SOFT,
    "h3": THEME.BLUE_SOFT,
    "h4": THEME.TEXT_SECONDARY,
    "h5": THEME.TEXT_SECONDARY,
    "h6": THEME.TEXT_DIM,
    "bold": THEME.TEXT_PRIMARY,
    "italic": THEME.PURPLE_SOFT,
    "bold_italic": THEME.PINK_SOFT,
    "code_inline": THEME.MINT_SOFT,
    "code_block": THEME.BLUE_SOFT,
    "link": THEME.BLUE_MEDIUM,
    "link_url": THEME.TEXT_DIM,
    "list_marker": THEME.PINK_SOFT,
    "list_number": THEME.PURPLE_SOFT,
    "blockquote": THEME.TEXT_SECONDARY,
    "blockquote_bar": THEME.PURPLE_SOFT,
    "text": THEME.TEXT_SECONDARY,
    "hr": THEME.TEXT_DIM,
}

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
BLOCKQUOTE_RE = re.compile(r"^>\s*(.*)$")
UNORDERED_LIST_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
ORDERED_LIST_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
HORIZONTAL_RULE_RE = re.compile(r"^[-*_]{3,}\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*(:?-+:?)\s*(\|\s*(:?-+:?)\s*)+\|?\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([A-Za-z0-9_+.-]*)\s*$")
BLOCK_MARKDOWN_HINT_RE = re.compile(
    r"(?m)^\s*(?:#{1,6}\s|>|\|.*\||[-*+]\s|\d+\.\s|[-*_]{3,}\s*$|```|~~~)"
)
INLINE_PATTERNS = [
    (re.compile(r"`([^`]+)`"), "code_inline"),
    (re.compile(r"\*\*\*([^*]+)\*\*\*"), "bold_italic"),
    (re.compile(r"___([^_]+)___"), "bold_italic"),
    (re.compile(r"\*\*([^*]+)\*\*"), "bold"),
    (re.compile(r"__([^_]+)__"), "bold"),
    (re.compile(r"\*([^*]+)\*"), "italic"),
    (re.compile(r"_([^_]+)_"), "italic"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), "link"),
]

SYNTAX_LANGUAGE_MAP = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "tsx": "tsx",
    "sh": "bash",
    "ps1": "powershell",
    "yml": "yaml",
}


class MarkdownFormatter:
    """Convert markdown text into richer terminal renderables."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(width=None)
        self.deco = DECO
        self.theme = THEME

    def format_text(self, markdown_text: str) -> RenderableType:
        return self.format_text_with_wrapping(markdown_text)

    def format_text_with_wrapping(
        self,
        markdown_text: str,
        max_width: Optional[int] = None,
    ) -> RenderableType:
        if max_width is None:
            max_width = self.console.width or 80
        normalized_text = str(markdown_text or "")

        if self._looks_like_plain_text(normalized_text):
            return Text(normalized_text, style=COLORS["text"])

        renderables = self._parse_blocks(normalized_text, max_width=max_width)
        if not renderables:
            return Text("")
        if len(renderables) == 1:
            return renderables[0]
        return Group(*renderables)

    def format_streaming_chunk(self, chunk: str) -> RenderableType:
        return self.format_text(chunk)

    def _safe_symbol(self, preferred: str, fallback: str) -> str:
        """Prefer Unicode glyphs, but degrade cleanly on legacy console encodings."""
        encoding = str(getattr(getattr(self.console, "file", None), "encoding", "") or "utf-8")
        try:
            preferred.encode(encoding)
        except Exception:
            return fallback
        return preferred

    def _looks_like_plain_text(self, text: str) -> bool:
        """Return True when the text has no markdown hints and can skip block parsing."""
        if not text:
            return True
        if BLOCK_MARKDOWN_HINT_RE.search(text):
            return False
        return not any(token in text for token in ("`", "*", "_", "]("))

    def _parse_blocks(self, markdown_text: str, max_width: int) -> List[RenderableType]:
        lines = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        renderables: List[RenderableType] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                renderables.append(Text(""))
                i += 1
                continue

            fence_match = FENCE_RE.match(line)
            if fence_match:
                fence_token = fence_match.group(1)
                language = fence_match.group(2).strip().lower()
                code_lines: List[str] = []
                i += 1
                while i < len(lines):
                    closing_match = FENCE_RE.match(lines[i])
                    if closing_match and closing_match.group(1).startswith(fence_token[0]):
                        break
                    code_lines.append(lines[i])
                    i += 1
                renderables.append(
                    self._render_code_block(
                        code_lines,
                        language=language,
                        max_width=max_width,
                    )
                )
                i += 1
                continue

            if TABLE_ROW_RE.match(line) and i + 1 < len(lines) and TABLE_SEPARATOR_RE.match(lines[i + 1]):
                headers = [cell.strip() for cell in TABLE_ROW_RE.match(line).group(1).split("|")]
                rows: List[List[str]] = []
                i += 2
                while i < len(lines):
                    row_match = TABLE_ROW_RE.match(lines[i])
                    if not row_match:
                        break
                    cells = [cell.strip() for cell in row_match.group(1).split("|")]
                    while len(cells) < len(headers):
                        cells.append("")
                    if len(cells) > len(headers):
                        cells = cells[: len(headers)]
                    rows.append(cells)
                    i += 1
                renderables.append(self._render_table(headers, rows))
                continue

            header_match = HEADER_RE.match(line)
            if header_match:
                renderables.append(self._render_header(header_match))
                i += 1
                continue

            blockquote_match = BLOCKQUOTE_RE.match(line)
            if blockquote_match:
                renderables.append(self._render_blockquote(blockquote_match.group(1)))
                i += 1
                continue

            unordered_match = UNORDERED_LIST_RE.match(line)
            if unordered_match:
                renderables.append(
                    self._render_list_item(
                        unordered_match.group(2),
                        marker=unordered_match.group(0).strip()[0],
                        indent=len(unordered_match.group(1).replace("\t", "    ")),
                        ordered=False,
                    )
                )
                i += 1
                continue

            ordered_match = ORDERED_LIST_RE.match(line)
            if ordered_match:
                renderables.append(
                    self._render_list_item(
                        ordered_match.group(3),
                        marker=ordered_match.group(2),
                        indent=len(ordered_match.group(1).replace("\t", "    ")),
                        ordered=True,
                    )
                )
                i += 1
                continue

            if HORIZONTAL_RULE_RE.match(line):
                rule_char = self._safe_symbol(self.deco.LINE_HORIZONTAL, "-")
                renderables.append(
                    Text(rule_char * max(12, min(max_width - 4, 42)), style=COLORS["hr"])
                )
                i += 1
                continue

            renderables.append(self._render_paragraph(line))
            i += 1

        while renderables and isinstance(renderables[-1], Text) and not renderables[-1].plain:
            renderables.pop()
        return renderables

    def _render_header(self, match: re.Match[str]) -> RenderableType:
        level = len(match.group(1))
        content = match.group(2).strip()
        color = COLORS[f"h{min(level, 6)}"]
        text = Text()
        if level == 1:
            text.append(content, style=f"bold {color}")
        elif level == 2:
            text.append(content, style=f"bold {color}")
        elif level == 3:
            text.append(content, style=f"bold {color}")
        else:
            text.append(content, style=color)
        return text

    def _render_blockquote(self, content: str) -> RenderableType:
        text = Text()
        quote_bar = self._safe_symbol(self.deco.LINE_VERTICAL, "|")
        text.append(f"{quote_bar} ", style=COLORS["blockquote_bar"])
        text.append_text(
            self._format_inline(
                content,
                base_style=f"italic {COLORS['blockquote']}",
            )
        )
        return Padding(text, (0, 0, 0, 1))

    def _render_list_item(
        self,
        item_text: str,
        *,
        marker: str,
        indent: int,
        ordered: bool,
    ) -> RenderableType:
        text = Text(" " * indent)
        bullet = self._safe_symbol("\u2022", "-")
        marker_text = f"{marker}. " if ordered and marker.isdigit() else f"{bullet} "
        marker_style = COLORS["list_number"] if ordered else COLORS["list_marker"]
        text.append(marker_text, style=f"bold {marker_style}")
        text.append_text(self._format_inline(item_text))
        return text

    def _render_paragraph(self, line: str) -> RenderableType:
        return self._format_inline(line)

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> RenderableType:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            show_edge=False,
            pad_edge=False,
            expand=False,
            header_style=f"bold {self.theme.TEXT_PRIMARY}",
        )
        for header in headers:
            table.add_column(header or " ", style=self.theme.TEXT_SECONDARY, overflow="fold")
        for row in rows:
            table.add_row(*[str(cell or "") for cell in row])
        return Padding(table, (0, 0, 0, 2))

    def _render_code_block(
        self,
        code_lines: List[str],
        *,
        language: str,
        max_width: int,
    ) -> RenderableType:
        resolved_language = SYNTAX_LANGUAGE_MAP.get(language, language or "text")
        compact = max_width < 100
        preview_limit = 24 if compact else 40
        code_text = "\n".join(code_lines)
        hidden_lines = 0
        if len(code_lines) > preview_limit:
            hidden_lines = len(code_lines) - preview_limit
            code_text = "\n".join(code_lines[:preview_limit])

        syntax_theme = "ansi_dark" if resolved_language == "diff" else "monokai"
        syntax = Syntax(
            code_text,
            resolved_language or "text",
            theme=syntax_theme,
            line_numbers=True,
            word_wrap=False,
            padding=(0, 0),
            background_color="default",
        )
        parts: List[RenderableType] = [Padding(syntax, (0, 0, 0, 2))]
        if hidden_lines:
            parts.append(
                Padding(
                    Text(
                        f"... {hidden_lines} hidden lines ...",
                        style=self.theme.TEXT_DIM,
                    ),
                    (0, 0, 0, 2),
                )
            )
        return Group(*parts)

    def _format_inline(self, text: str, base_style: Optional[str] = None) -> Text:
        pos = 0
        default_style = base_style or COLORS["text"]
        if not text:
            return Text("", style=default_style)
        if not any(token in text for token in ("`", "*", "_", "](")):
            return Text(text, style=default_style)

        result = Text()
        while pos < len(text):
            best_match = None
            best_start = len(text) + 1
            best_pattern_type = None
            for pattern, pattern_type in INLINE_PATTERNS:
                match = pattern.search(text, pos)
                if match and match.start() < best_start:
                    best_match = match
                    best_start = match.start()
                    best_pattern_type = pattern_type

            if best_match is None:
                result.append(text[pos:], style=default_style)
                break

            if best_start > pos:
                result.append(text[pos:best_start], style=default_style)

            if best_pattern_type == "link":
                link_text = best_match.group(1)
                link_url = best_match.group(2)
                result.append(link_text, style=f"underline {COLORS['link']}")
                result.append(f" ({link_url})", style=COLORS["link_url"])
            elif best_pattern_type == "code_inline":
                result.append(best_match.group(1), style=f"bold {COLORS['code_inline']}")
            elif best_pattern_type == "bold":
                result.append(best_match.group(1), style=f"bold {COLORS['bold']}")
            elif best_pattern_type == "italic":
                result.append(best_match.group(1), style=f"italic {COLORS['italic']}")
            elif best_pattern_type == "bold_italic":
                result.append(best_match.group(1), style=f"bold italic {COLORS['bold_italic']}")

            pos = best_start + len(best_match.group(0))
        return result


_DEFAULT_FORMATTER = MarkdownFormatter()


def format_markdown(
    text: str,
    formatter: Optional[MarkdownFormatter] = None,
    max_width: Optional[int] = None,
) -> RenderableType:
    active_formatter = formatter or _DEFAULT_FORMATTER
    return active_formatter.format_text_with_wrapping(text, max_width=max_width)


def format_markdown_streaming(
    chunk: str,
    formatter: Optional[MarkdownFormatter] = None,
) -> RenderableType:
    active_formatter = formatter or _DEFAULT_FORMATTER
    return active_formatter.format_streaming_chunk(chunk)
