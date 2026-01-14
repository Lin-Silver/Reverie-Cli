"""
Reverie Theme System - Dreamscape Color Palette

A unified theme system for the Reverie TUI featuring a dreamy,
ethereal color palette with pink, purple, and blue gradients.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
from rich.style import Style
from rich.text import Text


@dataclass
class DreamscapeTheme:
    """
    The Dreamscape theme - A dreamy, ethereal color palette.
    
    Features flowing gradients from soft pink through mystical purple to celestial blue.
    Designed to create a soothing, immersive coding experience.
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PRIMARY PALETTE - The core dreamy colors
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Pink spectrum (warm, gentle)
    PINK_SOFT = "#ffb8d1"          # Soft cherry blossom
    PINK_MEDIUM = "#ff9ec4"        # Rose quartz
    PINK_VIBRANT = "#ff85b8"       # Bright sakura
    PINK_GLOW = "#ffd6e7"          # Luminous pink
    
    # Purple spectrum (mystical, magical)
    PURPLE_SOFT = "#e4b0ff"        # Soft lavender
    PURPLE_MEDIUM = "#ce93d8"      # Muted amethyst
    PURPLE_VIBRANT = "#ba68c8"     # Vivid violet
    PURPLE_DEEP = "#9c27b0"        # Deep magenta
    PURPLE_GLOW = "#ead0fe"        # Glowing lavender
    
    # Blue spectrum (celestial, dreamy)
    BLUE_SOFT = "#81d4fa"          # Soft sky blue
    BLUE_MEDIUM = "#64b5f6"        # Cerulean dream
    BLUE_VIBRANT = "#42a5f5"       # Electric azure
    BLUE_DEEP = "#1e88e5"          # Deep sapphire
    BLUE_GLOW = "#b3e5fc"          # Luminous cyan
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ACCENT COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Success/Nature accents
    MINT_SOFT = "#a5d6a7"          # Soft mint green
    MINT_VIBRANT = "#66bb6a"       # Fresh spearmint
    
    # Warning/Warm accents
    PEACH_SOFT = "#ffcc80"         # Soft peach
    AMBER_GLOW = "#ffb86c"         # Warm amber
    
    # Error/Alert accents
    CORAL_SOFT = "#ff8a80"         # Soft coral
    CORAL_VIBRANT = "#ff5252"      # Bright coral
    
    # Thinking/Reasoning accents (ethereal, mystical)
    THINKING_SOFT = "#b39ddb"      # Soft twilight purple
    THINKING_MEDIUM = "#9575cd"    # Mystical violet
    THINKING_DIM = "#7e57c2"       # Deep thought purple
    THINKING_BORDER = "#673ab7"    # Thinking panel border
    THINKING_GLOW = "#d1c4e9"      # Soft lavender glow
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TEXT COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    TEXT_PRIMARY = "#f5f5f5"       # Pure white with slight warmth
    TEXT_SECONDARY = "#e0e0e0"     # Soft off-white
    TEXT_DIM = "#9e9e9e"           # Muted gray
    TEXT_MUTED = "#757575"         # Very muted
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SEMANTIC COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    SUCCESS = "#66bb6a"
    WARNING = "#ffb86c"
    ERROR = "#ff5252"
    INFO = "#81d4fa"
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UI ELEMENT COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    BORDER_PRIMARY = "#ce93d8"      # Primary border (purple)
    BORDER_SECONDARY = "#ba68c8"    # Secondary border
    BORDER_SUBTLE = "#9575cd"       # Subtle borders
    
    PANEL_HEADER = "#ffb8d1"        # Panel titles (pink)
    PANEL_SUBTITLE = "#ce93d8"      # Panel subtitles (purple)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # GRADIENTS FOR DECORATIVE ELEMENTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    @staticmethod
    def get_gradient_pink_purple() -> List[str]:
        """Get pink to purple gradient colors"""
        return ["#ffb8d1", "#f8a5c8", "#e99bd4", "#d791df", "#ce93d8"]
    
    @staticmethod
    def get_gradient_purple_blue() -> List[str]:
        """Get purple to blue gradient colors"""
        return ["#ce93d8", "#b58dd8", "#9c88d9", "#8383d9", "#81d4fa"]
    
    @staticmethod
    def get_gradient_full_spectrum() -> List[str]:
        """Get full pink-purple-blue gradient"""
        return [
            "#ffb8d1", "#f0a0d0", "#e188cf",  # Pink
            "#d270ce", "#c358cd", "#b440cc",  # Pink to purple
            "#a528cb", "#9620ca", "#8718c9",  # Purple
            "#7810c8", "#6908c7", "#5a00c6",  # Deep purple
            "#6b28d8", "#7c50ea", "#8d78fc",  # Purple to blue
            "#81d4fa"                          # Blue
        ]
    
    @staticmethod
    def get_rainbow_dreamy() -> List[str]:
        """Get a softer dreamy rainbow for special effects"""
        return [
            "#ffd6e7", "#ffe4f0",  # Soft pinks
            "#f3e5f5", "#f0e0f8",  # Pale lavender
            "#ede0fb", "#ead0fe",  # Lavender
            "#e7c0ff", "#e4b0ff",  # Purple
            "#d1c4e9", "#b39ddb",  # Muted purple
            "#9fa8da", "#81d4fa",  # Blue
            "#b3e5fc"              # Light blue
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIAL CHARACTERS & DECORATORS
# ═══════════════════════════════════════════════════════════════════════════════

class DreamDecorators:
    """
    Unicode decorators for a dreamy, ethereal UI aesthetic.
    """
    
    # Sparkles and stars
    SPARKLE = "✧"
    SPARKLE_FILLED = "✦"
    STAR = "★"
    STAR_OUTLINE = "☆"
    TWINKLE = "✨"
    
    # Geometric shapes
    DIAMOND = "◇"
    DIAMOND_FILLED = "◆"
    RHOMBUS = "◈"
    CRYSTAL = "❖"
    
    # Circles and dots
    CIRCLE = "○"
    CIRCLE_FILLED = "●"
    DOT_SMALL = "·"
    DOT_MEDIUM = "•"
    RING = "◎"
    
    # Arrows and pointers
    ARROW_RIGHT = "→"
    ARROW_CURVED = "↳"
    CHEVRON_RIGHT = "›"
    CHEVRON_DOUBLE = "»"
    TRIANGLE_RIGHT = "▸"
    
    # Box drawing (dreamy style)
    LINE_HORIZONTAL = "─"
    LINE_VERTICAL = "│"
    CORNER_TOP_LEFT = "╭"
    CORNER_TOP_RIGHT = "╮"
    CORNER_BOTTOM_LEFT = "╰"
    CORNER_BOTTOM_RIGHT = "╯"
    
    # Decorative lines
    WAVE = "～"
    SPARKLE_LINE = "・゜・"
    DREAM_DIVIDER = "✧･ﾟ: *✧･ﾟ:*"
    STARS_LINE = "✦ · ✧ · ✦"
    
    # Status indicators
    CHECK = "✓"
    CHECK_FANCY = "✔"
    CROSS = "✗"
    CROSS_FANCY = "✘"
    LOADING_DOTS = "⋯"
    
    # Mood/emotion
    HEART = "♡"
    HEART_FILLED = "♥"
    MOON = "☽"
    MOON_CRESCENT = "🌙"
    CLOUD = "☁"
    
    # Thinking/Reasoning indicators
    THOUGHT_BUBBLE = "💭"
    CRYSTAL_BALL = "🔮"
    BRAIN = "🧠"
    THINKING = "⟐"                 # Diamond with dot (thinking symbol)
    THOUGHT_WAVE = "∿"             # Wavy thinking line
    
    # Brackets and frames
    BRACKET_OPEN = "「"
    BRACKET_CLOSE = "」"
    ANGLE_OPEN = "《"
    ANGLE_CLOSE = "》"


# ═══════════════════════════════════════════════════════════════════════════════
# STYLED TEXT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class DreamText:
    """Helper class for creating themed text elements"""
    
    theme = DreamscapeTheme()
    deco = DreamDecorators()
    
    @classmethod
    def header(cls, text: str, level: int = 1) -> str:
        """Create a styled header"""
        colors = [
            cls.theme.PINK_SOFT,
            cls.theme.PURPLE_MEDIUM,
            cls.theme.BLUE_SOFT,
            cls.theme.PURPLE_SOFT,
        ]
        color = colors[min(level - 1, len(colors) - 1)]
        
        if level == 1:
            return f"[bold {color}]{cls.deco.SPARKLE} {text} {cls.deco.SPARKLE}[/bold {color}]"
        elif level == 2:
            return f"[bold {color}]{cls.deco.DIAMOND} {text}[/bold {color}]"
        else:
            return f"[{color}]{cls.deco.DOT_MEDIUM} {text}[/{color}]"
    
    @classmethod
    def success(cls, text: str) -> str:
        """Success message"""
        return f"[bold {cls.theme.MINT_VIBRANT}]{cls.deco.CHECK_FANCY}[/bold {cls.theme.MINT_VIBRANT}] [{cls.theme.MINT_SOFT}]{text}[/{cls.theme.MINT_SOFT}]"
    
    @classmethod
    def error(cls, text: str) -> str:
        """Error message"""
        return f"[bold {cls.theme.CORAL_VIBRANT}]{cls.deco.CROSS_FANCY}[/bold {cls.theme.CORAL_VIBRANT}] [{cls.theme.CORAL_SOFT}]{text}[/{cls.theme.CORAL_SOFT}]"
    
    @classmethod
    def warning(cls, text: str) -> str:
        """Warning message"""
        return f"[bold {cls.theme.AMBER_GLOW}]![/bold {cls.theme.AMBER_GLOW}] [{cls.theme.PEACH_SOFT}]{text}[/{cls.theme.PEACH_SOFT}]"
    
    @classmethod
    def info(cls, text: str) -> str:
        """Info message"""
        return f"[{cls.theme.BLUE_SOFT}]{cls.deco.RHOMBUS}[/{cls.theme.BLUE_SOFT}] [{cls.theme.TEXT_SECONDARY}]{text}[/{cls.theme.TEXT_SECONDARY}]"
    
    @classmethod
    def dim(cls, text: str) -> str:
        """Dimmed/muted text"""
        return f"[dim {cls.theme.TEXT_DIM}]{text}[/dim {cls.theme.TEXT_DIM}]"
    
    @classmethod
    def highlight(cls, text: str, color: str = None) -> str:
        """Highlighted text"""
        c = color or cls.theme.PURPLE_GLOW
        return f"[bold {c}]{text}[/bold {c}]"
    
    @classmethod  
    def prompt_prefix(cls, label: str = "Reverie") -> str:
        """Create the command prompt prefix"""
        return (
            f"[bold {cls.theme.PINK_SOFT}]{cls.deco.SPARKLE}[/bold {cls.theme.PINK_SOFT}] "
            f"[bold {cls.theme.PURPLE_SOFT}]{label}[/bold {cls.theme.PURPLE_SOFT}]"
            f"[{cls.theme.BLUE_SOFT}]{cls.deco.CHEVRON_RIGHT}[/{cls.theme.BLUE_SOFT}] "
        )
    
    @classmethod
    def tool_header(cls, tool_name: str) -> str:
        """Create a tool execution header"""
        return (
            f"[bold {cls.theme.PINK_SOFT}]{cls.deco.RHOMBUS}[/bold {cls.theme.PINK_SOFT}] "
            f"[bold {cls.theme.PURPLE_GLOW}]{tool_name}[/bold {cls.theme.PURPLE_GLOW}]"
        )
    
    @classmethod
    def thinking_header(cls) -> str:
        """Create a thinking process header"""
        return (
            f"[italic {cls.theme.THINKING_SOFT}]{cls.deco.THOUGHT_BUBBLE}[/italic {cls.theme.THINKING_SOFT}] "
            f"[italic bold {cls.theme.THINKING_MEDIUM}]Thinking...[/italic bold {cls.theme.THINKING_MEDIUM}]"
        )
    
    @classmethod
    def thinking_content(cls, text: str) -> str:
        """Format thinking/reasoning content with special styling"""
        return f"[italic {cls.theme.THINKING_SOFT}]{text}[/italic {cls.theme.THINKING_SOFT}]"
    
    @classmethod
    def thinking_line(cls, text: str) -> str:
        """Format a single line of thinking content"""
        return (
            f"[{cls.theme.THINKING_DIM}]{cls.deco.LINE_VERTICAL}[/{cls.theme.THINKING_DIM}] "
            f"[italic {cls.theme.THINKING_SOFT}]{text}[/italic {cls.theme.THINKING_SOFT}]"
        )
    
    @classmethod
    def divider(cls, width: int = 40, style: str = "simple") -> str:
        """Create a themed divider line"""
        if style == "sparkle":
            return f"[{cls.theme.PURPLE_MEDIUM}]{cls.deco.SPARKLE_LINE * (width // 8)}[/{cls.theme.PURPLE_MEDIUM}]"
        elif style == "stars":
            return f"[{cls.theme.PURPLE_MEDIUM}]{cls.deco.STARS_LINE}[/{cls.theme.PURPLE_MEDIUM}]"
        elif style == "dream":
            return f"[{cls.theme.PURPLE_MEDIUM}]{cls.deco.DREAM_DIVIDER}[/{cls.theme.PURPLE_MEDIUM}]"
        else:
            return f"[{cls.theme.PURPLE_MEDIUM}]{cls.deco.LINE_HORIZONTAL * width}[/{cls.theme.PURPLE_MEDIUM}]"
    
    @classmethod
    def gradient_text(cls, text: str, colors: List[str] = None) -> Text:
        """Create gradient-colored text using Rich Text"""
        if colors is None:
            colors = cls.theme.get_gradient_pink_purple()
        
        result = Text()
        text_len = len(text)
        color_len = len(colors)
        
        for i, char in enumerate(text):
            color_idx = int((i / text_len) * color_len)
            color_idx = min(color_idx, color_len - 1)
            result.append(char, style=colors[color_idx])
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# BOX STYLES FOR PANELS
# ═══════════════════════════════════════════════════════════════════════════════

class DreamBoxes:
    """Custom box styles for Rich panels"""
    
    @staticmethod
    def get_dream_box():
        """Get a dreamy rounded box style"""
        from rich import box
        return box.ROUNDED
    
    @staticmethod
    def get_minimal_box():
        """Get a minimal box style"""
        from rich import box
        return box.SIMPLE
    
    @staticmethod
    def get_double_box():
        """Get a double-line box style"""
        from rich import box
        return box.DOUBLE


# ═══════════════════════════════════════════════════════════════════════════════
# THEME INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Global theme instance
THEME = DreamscapeTheme()
DECO = DreamDecorators()
DREAM = DreamText()
