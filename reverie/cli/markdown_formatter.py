"""
Markdown Formatter - Clean Markdown rendering with Dreamscape colors

This module converts Markdown syntax to clean, colored terminal output
with a dreamy pink-purple-blue color scheme without showing raw
markdown characters like #, *, etc.
"""

import re
from typing import Tuple, List
from rich.text import Text
from rich.console import Console

from .theme import THEME, DECO


# ═══════════════════════════════════════════════════════════════════════════════
# DREAMSCAPE COLOR SCHEME
# ═══════════════════════════════════════════════════════════════════════════════

COLORS = {
    # Headers - Gradient from pink to blue
    'h1': THEME.PINK_SOFT,         # Soft cherry blossom for main headers
    'h2': THEME.PURPLE_MEDIUM,     # Muted amethyst for secondary
    'h3': THEME.BLUE_SOFT,         # Soft sky blue for tertiary
    'h4': THEME.PINK_GLOW,         # Luminous pink
    'h5': THEME.PURPLE_GLOW,       # Glowing lavender
    'h6': THEME.BLUE_GLOW,         # Luminous cyan
    
    # Text formatting
    'bold': THEME.PINK_SOFT,       # Soft Pink for bold emphasis
    'italic': THEME.PURPLE_SOFT,   # Lavender for italic
    'bold_italic': THEME.PINK_GLOW, # Luminous pink for bold italic
    
    # Code
    'code_inline': THEME.MINT_SOFT,  # Soft mint for inline code
    'code_block': THEME.BLUE_SOFT,   # Soft blue for code blocks
    
    # Links
    'link': THEME.BLUE_MEDIUM,       # Cerulean dream for links
    'link_url': THEME.TEXT_DIM,      # Muted for URLs
    
    # Lists and structure
    'list_marker': THEME.PINK_SOFT,  # Soft pink for list markers
    'list_number': THEME.PURPLE_SOFT, # Lavender for numbers
    
    # Quotes
    'blockquote': THEME.PURPLE_MEDIUM, # Muted purple for quotes
    'blockquote_bar': THEME.PURPLE_SOFT, # Lavender for quote bar
    
    # General text
    'text': THEME.TEXT_SECONDARY,    # Soft off-white for readability
    
    # Horizontal rule
    'hr': THEME.PURPLE_MEDIUM,       # Muted purple for dividers
}


class MarkdownFormatter:
    """
    Converts Markdown text to Rich Text with Dreamscape colors.
    
    Removes markdown syntax characters (like #, *, etc.) and applies
    appropriate colors based on the semantic meaning with a dreamy
    pink-purple-blue aesthetic.
    """
    
    def __init__(self):
        self.console = Console(width=None)  # Let console auto-detect width
        self.deco = DECO
    
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
    
    def format_text_with_wrapping(self, markdown_text: str, max_width: int = None) -> Text:
        """
        Convert markdown text to Rich Text with proper text wrapping.
        
        Args:
            markdown_text: Raw markdown string
            max_width: Maximum width for text wrapping (auto-detect if None)
            
        Returns:
            Rich Text object with formatted content and proper wrapping
        """
        if max_width is None:
            max_width = self.console.width or 80
        
        result = Text()
        lines = markdown_text.split('\n')
        
        for i, line in enumerate(lines):
            # Skip empty lines
            if not line.strip():
                if i < len(lines) - 1:
                    result.append('\n')
                continue
            
            formatted_line = self._format_line(line)
            
            # Check if line needs wrapping (excluding special formatting lines)
            if (not line.startswith('#') and 
                not line.startswith('>') and 
                not line.strip().startswith('-') and 
                not line.strip().startswith('*') and 
                not re.match(r'^\s*\d+\.', line) and
                len(line) > max_width):
                
                # Wrap the line while preserving formatting
                wrapped_text = self._wrap_text(formatted_line, max_width)
                result.append_text(wrapped_text)
            else:
                result.append_text(formatted_line)
            
            if i < len(lines) - 1:
                result.append('\n')
        
        return result
    
    def _wrap_text(self, text: Text, max_width: int) -> Text:
        """
        Wrap a Rich Text object to fit within the specified width.
        
        Args:
            text: Rich Text object to wrap
            max_width: Maximum width for each line
            
        Returns:
            Rich Text object with wrapped content
        """
        # Convert to plain text for wrapping, then reapply formatting
        plain_text = text.plain
        words = plain_text.split(' ')
        
        result = Text()
        current_line = Text()
        current_length = 0
        
        for i, word in enumerate(words):
            word_length = len(word)
            
            # Check if we need to start a new line
            if current_length > 0 and current_length + word_length + 1 > max_width:
                result.append_text(current_line)
                result.append('\n')
                current_line = Text()
                current_length = 0
            
            # Add word to current line
            if current_length > 0:
                current_line.append(' ')
                current_length += 1
            
            # Find the corresponding styled span for this word
            # This is a simplified approach - for full preservation we'd need
            # to track character positions more carefully
            current_line.append(word, style=text.style)
            current_length += word_length
        
        # Add the last line
        if current_length > 0:
            result.append_text(current_line)
        
        return result
    
    def _format_line(self, line: str) -> Text:
        """Format a single line of markdown with Dreamscape styling"""
        result = Text()
        
        # Handle headers (# ## ### etc.)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            content = header_match.group(2)
            color_key = f'h{min(level, 6)}'
            color = COLORS[color_key]
            
            # Add decorative prefix based on level
            if level == 1:
                prefix = f"{self.deco.SPARKLE} "
                result.append(prefix, style=color)
                result.append(content.upper(), style=f"bold {color}")
                result.append(f" {self.deco.SPARKLE}", style=color)
            elif level == 2:
                prefix = f"{self.deco.DIAMOND} "
                result.append(prefix, style=color)
                result.append(content, style=f"bold {color}")
            elif level == 3:
                prefix = f"{self.deco.RHOMBUS} "
                result.append(prefix, style=color)
                result.append(content, style=f"bold {color}")
            else:
                prefix = f"{self.deco.DOT_MEDIUM} "
                result.append(prefix, style=color)
                result.append(content, style=color)
            return result
        
        # Handle blockquotes (> text)
        blockquote_match = re.match(r'^>\s*(.*)$', line)
        if blockquote_match:
            content = blockquote_match.group(1)
            result.append(f"{self.deco.LINE_VERTICAL} ", style=COLORS['blockquote_bar'])
            result.append_text(self._format_inline(content, base_style=f"italic {COLORS['blockquote']}"))
            return result
        
        # Handle unordered lists (- or * or +)
        list_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if list_match:
            indent = list_match.group(1)
            content = list_match.group(2)
            result.append(indent)
            result.append(f"{self.deco.SPARKLE_FILLED} ", style=COLORS['list_marker'])
            result.append_text(self._format_inline(content))
            return result
        
        # Handle ordered lists (1. 2. etc.)
        ordered_list_match = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if ordered_list_match:
            indent = ordered_list_match.group(1)
            number = ordered_list_match.group(2)
            content = ordered_list_match.group(3)
            result.append(indent)
            result.append(f"{number}. ", style=f"bold {COLORS['list_number']}")
            result.append_text(self._format_inline(content))
            return result
        
        # Handle horizontal rules (--- or *** or ___)
        if re.match(r'^[-*_]{3,}\s*$', line):
            divider = f" {self.deco.SPARKLE} {self.deco.LINE_HORIZONTAL * 30} {self.deco.SPARKLE} "
            result.append(divider, style=COLORS['hr'])
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
                # Add subtle code styling with brackets
                result.append(best_match.group(1), style=f"bold {COLORS['code_inline']}")
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
    Convenience function to format markdown text with Dreamscape theme.
    
    Args:
        text: Raw markdown string
        
    Returns:
        Rich Text object with formatted content
    """
    formatter = MarkdownFormatter()
    return formatter.format_text_with_wrapping(text)


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
