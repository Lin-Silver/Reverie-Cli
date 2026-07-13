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
    
    TEXT_PRIMARY = "#f8fbff"       # Crisp white for main transcript text
    TEXT_SECONDARY = "#dde7f5"     # Brighter secondary copy
    TEXT_DIM = "#a7b6cb"           # Muted but readable status text
    TEXT_MUTED = "#73839b"         # Low-priority metadata
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SEMANTIC COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    SUCCESS = "#66bb6a"
    WARNING = "#ffb86c"
    ERROR = "#ff5252"
    INFO = "#81d4fa"
    
    # ═══════════════════════════════════════════════════════════════════════════
    # GAME DEVELOPMENT SPECIFIC COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Tool categories
    TOOL_GDD = "#ffb8d1"           # GDD Manager (pink)
    TOOL_STORY = "#e4b0ff"         # Story Design (purple)
    TOOL_ASSET = "#81d4fa"         # Asset Manager (blue)
    TOOL_BALANCE = "#66bb6a"       # Balance Analyzer (green)
    TOOL_LEVEL = "#ffcc80"         # Level Design (peach)
    TOOL_CONFIG = "#ce93d8"        # Config Editor (purple)
    
    # Task phases
    PHASE_DESIGN = "#ffb8d1"       # Design phase (pink)
    PHASE_IMPLEMENTATION = "#81d4fa"  # Implementation (blue)
    PHASE_CONTENT = "#e4b0ff"      # Content creation (purple)
    PHASE_TESTING = "#66bb6a"      # Testing (green)
    PHASE_RELEASE = "#ffcc80"      # Release (peach)
    
    # Priority levels
    PRIORITY_LOW = "#9e9e9e"       # Low priority (gray)
    PRIORITY_MEDIUM = "#81d4fa"    # Medium priority (blue)
    PRIORITY_HIGH = "#ffcc80"      # High priority (peach)
    PRIORITY_CRITICAL = "#ff5252"  # Critical priority (red)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UI ELEMENT COLORS
    # ═══════════════════════════════════════════════════════════════════════════
    
    BORDER_PRIMARY = "#8ec5ff"      # Primary border for important panels
    BORDER_SECONDARY = "#c7a8ff"    # Secondary border
    BORDER_SUBTLE = "#6f89ad"       # Subtle borders
    
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
    SEARCH = "🔍"  # Search icon for selector
    
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

_BASE_DECO_VALUES = {
    name: getattr(DECO, name)
    for name in (
        "SPARKLE", "SPARKLE_FILLED", "TWINKLE", "DIAMOND", "DIAMOND_FILLED", "RHOMBUS",
        "DOT_SMALL", "DOT_MEDIUM", "CHEVRON_RIGHT", "LINE_HORIZONTAL", "LINE_VERTICAL",
        "CHECK", "CHECK_FANCY", "CROSS", "CROSS_FANCY", "SEARCH", "THOUGHT_BUBBLE",
    )
}

_BASE_THEME_VALUES = {
    name: getattr(THEME, name)
    for name in (
        "PINK_SOFT", "PINK_MEDIUM", "PINK_VIBRANT", "PINK_GLOW",
        "PURPLE_SOFT", "PURPLE_MEDIUM", "PURPLE_VIBRANT", "PURPLE_DEEP", "PURPLE_GLOW",
        "BLUE_SOFT", "BLUE_MEDIUM", "BLUE_VIBRANT", "BLUE_DEEP", "BLUE_GLOW",
        "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_DIM", "TEXT_MUTED",
        "BORDER_PRIMARY", "BORDER_SECONDARY", "BORDER_SUBTLE",
    )
}

THEME_PRESETS = {
    "default": {},
    "dark": {
        "PINK_SOFT": "#f38ba8", "PURPLE_SOFT": "#cba6f7", "PURPLE_MEDIUM": "#b4befe",
        "BLUE_SOFT": "#89b4fa", "TEXT_PRIMARY": "#cdd6f4", "TEXT_SECONDARY": "#bac2de",
        "TEXT_DIM": "#a6adc8", "TEXT_MUTED": "#7f849c", "BORDER_PRIMARY": "#89b4fa",
        "BORDER_SECONDARY": "#cba6f7", "BORDER_SUBTLE": "#6c7086",
    },
    "light": {
        "PINK_SOFT": "#9d174d", "PURPLE_SOFT": "#6d28d9", "PURPLE_MEDIUM": "#7c3aed",
        "BLUE_SOFT": "#075985", "TEXT_PRIMARY": "#111827", "TEXT_SECONDARY": "#374151",
        "TEXT_DIM": "#4b5563", "TEXT_MUTED": "#6b7280", "BORDER_PRIMARY": "#0369a1",
        "BORDER_SECONDARY": "#7c3aed", "BORDER_SUBTLE": "#64748b",
    },
    "ocean": {
        "PINK_SOFT": "#67e8f9", "PURPLE_SOFT": "#5eead4", "PURPLE_MEDIUM": "#2dd4bf",
        "BLUE_SOFT": "#38bdf8", "TEXT_PRIMARY": "#ecfeff", "TEXT_SECONDARY": "#cffafe",
        "TEXT_DIM": "#a5f3fc", "TEXT_MUTED": "#67e8f9", "BORDER_PRIMARY": "#22d3ee",
        "BORDER_SECONDARY": "#2dd4bf", "BORDER_SUBTLE": "#0e7490",
    },
    "high-contrast": {
        "PINK_SOFT": "#ffff00", "PURPLE_SOFT": "#ffffff", "PURPLE_MEDIUM": "#ffff00",
        "BLUE_SOFT": "#00ffff", "TEXT_PRIMARY": "#ffffff", "TEXT_SECONDARY": "#ffffff",
        "TEXT_DIM": "#e5e5e5", "TEXT_MUTED": "#cfcfcf", "BORDER_PRIMARY": "#ffffff",
        "BORDER_SECONDARY": "#ffff00", "BORDER_SUBTLE": "#cfcfcf",
    },
    "minimal": {
        "PINK_SOFT": "#d0d0d0", "PURPLE_SOFT": "#d0d0d0", "PURPLE_MEDIUM": "#a8a8a8",
        "BLUE_SOFT": "#d0d0d0", "TEXT_PRIMARY": "#eeeeee", "TEXT_SECONDARY": "#d0d0d0",
        "TEXT_DIM": "#a8a8a8", "TEXT_MUTED": "#808080", "BORDER_PRIMARY": "#666666",
        "BORDER_SECONDARY": "#666666", "BORDER_SUBTLE": "#555555",
    },
}


def apply_theme(name: str) -> str:
    """Mutate the shared theme object so existing UI components update immediately."""
    selected = str(name or "default").strip().lower()
    if selected not in THEME_PRESETS:
        selected = "default"
    values = dict(_BASE_THEME_VALUES)
    values.update(THEME_PRESETS[selected])
    for key, value in values.items():
        setattr(THEME, key, value)
        setattr(DreamText.theme, key, value)
    for key, value in _BASE_DECO_VALUES.items():
        setattr(DECO, key, value)
        setattr(DreamText.deco, key, value)
    if selected == "minimal":
        minimal_decorators = {
            "SPARKLE": "", "SPARKLE_FILLED": "", "TWINKLE": "", "DIAMOND": "-",
            "DIAMOND_FILLED": ">", "RHOMBUS": "-", "DOT_SMALL": ".", "DOT_MEDIUM": "·",
            "CHEVRON_RIGHT": ">", "LINE_HORIZONTAL": "-", "LINE_VERTICAL": "|",
            "CHECK": "OK", "CHECK_FANCY": "OK", "CROSS": "X", "CROSS_FANCY": "X",
            "SEARCH": "?", "THOUGHT_BUBBLE": "",
        }
        for key, value in minimal_decorators.items():
            setattr(DECO, key, value)
            setattr(DreamText.deco, key, value)
    return selected
