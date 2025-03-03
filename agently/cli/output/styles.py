"""
Style definitions for CLI output.

This module defines colors, styles, and other visual elements for CLI output.
"""

import os
import sys


class Color:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    GRAY = "\033[90m"
    MAGENTA = "\033[35m"


class Style:
    """Predefined styles for different types of output."""
    NORMAL = {}
    ERROR = {"color": "red"}
    SUCCESS = {"color": "green"}
    WARNING = {"color": "yellow"}
    INFO = {"color": "blue"}
    MUTED = {"color": "gray"}
    HEADER = {"color": "cyan", "bold": True}
    HIGHLIGHT = {"color": "magenta", "bold": True}


def should_use_colors():
    """Determine if colors should be used based on terminal capabilities."""
    # Check if stdout is a TTY
    if not sys.stdout.isatty():
        return False
    
    # Check for NO_COLOR environment variable
    if "NO_COLOR" in os.environ:
        return False
    
    # Check for FORCE_COLOR environment variable
    if "FORCE_COLOR" in os.environ:
        return True
    
    # Default to using colors
    return True


def get_color_code(color_name):
    """Get the ANSI color code for a named color."""
    return getattr(Color, color_name.upper(), "") if color_name else ""


def apply_style(text, style=None, **kwargs):
    """Apply a style to text.
    
    Args:
        text: The text to style
        style: A predefined style name or dict of style attributes
        **kwargs: Override style attributes
        
    Returns:
        Styled text
    """
    # Get the base style
    if isinstance(style, str):
        base_style = getattr(Style, style.upper(), Style.NORMAL)
    elif isinstance(style, dict):
        base_style = style
    else:
        base_style = Style.NORMAL
    
    # Override with kwargs
    final_style = {**base_style, **kwargs}
    
    # Apply the style
    return format_text(text, **final_style)


def format_text(text, color=None, bold=False, italic=False, underline=False):
    """Format text with colors and styles.
    
    Args:
        text: The text to format
        color: Color name (e.g., "red", "green")
        bold: Whether to make the text bold
        italic: Whether to make the text italic
        underline: Whether to underline the text
        
    Returns:
        Formatted text
    """
    if not should_use_colors():
        return str(text)
    
    result = ""
    
    # Apply styles
    if bold:
        result += Color.BOLD
    if italic:
        result += Color.ITALIC
    if underline:
        result += Color.UNDERLINE
    
    # Apply color
    if color:
        color_code = get_color_code(color)
        result += color_code
    
    # Add text and reset
    result += str(text) + Color.RESET
    return result 