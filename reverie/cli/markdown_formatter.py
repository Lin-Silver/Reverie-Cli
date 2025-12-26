"""
Markdown Formatter - Clean Markdown rendering with colored text

This module converts Markdown syntax to clean, colored terminal output
without showing raw markdown characters like #, *, etc.
"""

import re
from typing import Tuple, List
from rich.text import Text
from rich.console import Console


# Color scheme - "Nebula Soft" theme (Low-contrast Pink, Purple, Blue)
COLORS = {
    'h1': '#ffb8d1',           # Soft Pastel Pink for main headers
    'h2': '#ce93d8',           # Muted Lavender for secondary
    'h3': '#81d4fa',           # Soft Light Blue for tertiary
    'h4': '#f8bbd0',           # Very pale pink
    'h5': '#e1bee7',           # Very pale purple
    'h6': '#b3e5fc',           # Very pale blue
    'bold': '#ffb8d1',         # Soft Pink for bold
    'italic': '#ce93d8',       # Muted Purple for italic
    'bold_italic': '#f8bbd0',  # Pale Pink for bold italic
    'code_inline': '#a5d6a7',  # Soft Sage Green for inline code
    'code_block': '#81d4fa',   # Soft Blue for code blocks
    'link': '#80cbc4',         # Muted Teal for links
    'link_url': '#78909c',     # Blue-Grey for URLs
    'list_marker': '#ffb8d1',  # Soft Pink for list markers
    'blockquote': '#ce93d8',   # Muted Purple for quotes
    'text': '#e0e0e0',         # Soft off-white for text (easier on eyes)
}


class MarkdownFormatter:
    """
    Converts Markdown text to Rich Text with colors.
    
    Removes markdown syntax characters (like #, *, etc.) and applies
    appropriate colors based on the semantic meaning.
    """
    
    def __init__(self):
        self.console = Console()
    
    def format_text(self, markdown_text: str) -> Text:
        """
        Convert markdown text to Rich Text with colors.
        
        Args:
            markdown_text: Raw markdown string
            
        Returns:
            Rich Text object with formatted content
        """
        result = Text()
        lines = markdown_text.split('\n')
        
        for i, line in enumerate(lines):
            formatted_line = self._format_line(line)
            result.append_text(formatted_line)
            if i < len(lines) - 1:
                result.append('\n')
        
        return result
    
    def _format_line(self, line: str) -> Text:
        """Format a single line of markdown"""
        result = Text()
        
        # Handle headers (# ## ### etc.)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            content = header_match.group(2)
            color_key = f'h{min(level, 6)}'
            # Add some styling based on level
            if level == 1:
                result.append(content.upper(), style=f"bold {COLORS[color_key]}")
            elif level == 2:
                result.append(content, style=f"bold {COLORS[color_key]}")
            else:
                result.append(content, style=COLORS[color_key])
            return result
        
        # Handle blockquotes (> text)
        blockquote_match = re.match(r'^>\s*(.*)$', line)
        if blockquote_match:
            content = blockquote_match.group(1)
            result.append("│ ", style=COLORS['blockquote'])
            result.append_text(self._format_inline(content, base_style=f"italic {COLORS['blockquote']}"))
            return result
        
        # Handle unordered lists (- or * or +)
        list_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if list_match:
            indent = list_match.group(1)
            content = list_match.group(2)
            result.append(indent)
            result.append("• ", style=COLORS['list_marker'])
            result.append_text(self._format_inline(content))
            return result
        
        # Handle ordered lists (1. 2. etc.)
        ordered_list_match = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if ordered_list_match:
            indent = ordered_list_match.group(1)
            number = ordered_list_match.group(2)
            content = ordered_list_match.group(3)
            result.append(indent)
            result.append(f"{number}. ", style=COLORS['list_marker'])
            result.append_text(self._format_inline(content))
            return result
        
        # Handle horizontal rules (--- or *** or ___)
        if re.match(r'^[-*_]{3,}\s*$', line):
            result.append("─" * 40, style=COLORS['list_marker'])
            return result
        
        # Regular line - process inline formatting
        return self._format_inline(line)
    
    def _format_inline(self, text: str, base_style: str = None) -> Text:
        """Format inline markdown elements (bold, italic, code, links)"""
        result = Text()
        
        if not text:
            return result
        
        # Pattern for markdown inline elements
        # Order matters: longer patterns first
        patterns = [
            # Code blocks with backticks (must be before bold/italic)
            (r'`([^`]+)`', 'code_inline'),
            # Bold italic (***text*** or ___text___)
            (r'\*\*\*([^*]+)\*\*\*', 'bold_italic'),
            (r'___([^_]+)___', 'bold_italic'),
            # Bold (**text** or __text__)
            (r'\*\*([^*]+)\*\*', 'bold'),
            (r'__([^_]+)__', 'bold'),
            # Italic (*text* or _text_)
            (r'\*([^*]+)\*', 'italic'),
            (r'_([^_]+)_', 'italic'),
            # Links [text](url)
            (r'\[([^\]]+)\]\(([^)]+)\)', 'link'),
        ]
        
        # Simple approach: process text sequentially
        pos = 0
        default_style = base_style or COLORS['text']
        
        while pos < len(text):
            best_match = None
            best_start = len(text)
            best_pattern_type = None
            
            # Find the earliest match
            for pattern, pattern_type in patterns:
                match = re.search(pattern, text[pos:])
                if match and match.start() < best_start - pos:
                    best_match = match
                    best_start = pos + match.start()
                    best_pattern_type = pattern_type
            
            if best_match is None:
                # No more matches, append rest of text
                result.append(text[pos:], style=default_style)
                break
            
            # Append text before match
            if best_start > pos:
                result.append(text[pos:best_start], style=default_style)
            
            # Append matched content with appropriate style
            if best_pattern_type == 'link':
                link_text = best_match.group(1)
                link_url = best_match.group(2)
                result.append(link_text, style=f"underline {COLORS['link']}")
                result.append(f" ({link_url})", style=COLORS['link_url'])
            elif best_pattern_type == 'code_inline':
                result.append(best_match.group(1), style=COLORS['code_inline'])
            elif best_pattern_type == 'bold':
                result.append(best_match.group(1), style=f"bold {COLORS['bold']}")
            elif best_pattern_type == 'italic':
                result.append(best_match.group(1), style=f"italic {COLORS['italic']}")
            elif best_pattern_type == 'bold_italic':
                result.append(best_match.group(1), style=f"bold italic {COLORS['bold_italic']}")
            
            pos = best_start + len(best_match.group(0))
        
        return result
    
    def format_streaming_chunk(self, chunk: str) -> Text:
        """
        Format a streaming chunk of markdown.
        
        For streaming, we do simpler formatting since we may get partial
        markdown syntax. This handles complete lines within the chunk.
        """
        return self.format_text(chunk)


def format_markdown(text: str) -> Text:
    """
    Convenience function to format markdown text.
    
    Args:
        text: Raw markdown string
        
    Returns:
        Rich Text object with formatted content
    """
    formatter = MarkdownFormatter()
    return formatter.format_text(text)


def format_markdown_streaming(chunk: str) -> Text:
    """
    Format a streaming chunk of markdown.
    
    Args:
        chunk: Streaming chunk of markdown
        
    Returns:
        Rich Text object with formatted content
    """
    formatter = MarkdownFormatter()
    return formatter.format_streaming_chunk(chunk)
