"""CLI formatting utilities for Agently.

This module provides formatting functions for CLI output,
including colored text and function call formatting.
"""

import sys


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Normal colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"  # Actually bright black

    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


def format_text(text, color=None, bold=False, italic=False, underline=False):
    """Format text with colors and styles.

    Args:
        text (str): The text to format
        color (str, optional): Color code from Colors class
        bold (bool, optional): Whether to make text bold
        italic (bool, optional): Whether to make text italic
        underline (bool, optional): Whether to underline text

    Returns:
        str: Formatted text with ANSI color codes
    """
    # Check if we should use colors (disable for non-TTY output)
    if not sys.stdout.isatty():
        return text

    result = ""
    if bold:
        result += Colors.BOLD
    if italic:
        result += Colors.ITALIC
    if underline:
        result += Colors.UNDERLINE
    if color:
        result += color

    result += str(text) + Colors.RESET
    return result


def gray(text):
    """Format text in gray color.

    Args:
        text (str): The text to format

    Returns:
        str: Gray-colored text
    """
    return format_text(text, color=Colors.GRAY)


def green(text):
    """Format text in green color.

    Args:
        text (str): The text to format

    Returns:
        str: Green-colored text
    """
    return format_text(text, color=Colors.GREEN)


def yellow(text):
    """Format text in yellow color.

    Args:
        text (str): The text to format

    Returns:
        str: Yellow-colored text
    """
    return format_text(text, color=Colors.YELLOW)


def red(text):
    """Format text in red color.

    Args:
        text (str): The text to format

    Returns:
        str: Red-colored text
    """
    return format_text(text, color=Colors.RED)


def blue(text):
    """Format text in blue color.

    Args:
        text (str): The text to format

    Returns:
        str: Blue-colored text
    """
    return format_text(text, color=Colors.BLUE)


def cyan(text):
    """Format text in cyan color.

    Args:
        text (str): The text to format

    Returns:
        str: Cyan-colored text
    """
    return format_text(text, color=Colors.CYAN)


def magenta(text):
    """Format text in magenta color.

    Args:
        text (str): The text to format

    Returns:
        str: Magenta-colored text
    """
    return format_text(text, color=Colors.MAGENTA)


def bold(text):
    """Format text in bold.

    Args:
        text (str): The text to format

    Returns:
        str: Bold text
    """
    return format_text(text, bold=True)


# Plugin status formatting functions
def format_action(message: str) -> str:
    """Format a plugin action message.

    Args:
        message (str): The action message

    Returns:
        str: Formatted action message with prefix
    """
    return f"\n{gray('┌')} {gray(message)}"


def format_subaction(message: str) -> str:
    """Format a plugin sub-action message.

    Args:
        message (str): The sub-action message

    Returns:
        str: Formatted sub-action message with prefix
    """
    return f"{gray('├─')} {gray(message)}"


def format_result(message: str, success: bool = True) -> str:
    """Format a plugin result message.

    Args:
        message (str): The result message
        success (bool): Whether the action was successful

    Returns:
        str: Formatted result message with appropriate color
    """
    color = green if success else red
    symbol = "✓" if success else "✗"
    return f"{gray('└')} {color(f'{symbol} {message}')}\n"


def format_file_header(path: str, start_line: int = None, end_line: int = None) -> str:
    """Format a file header.

    Args:
        path (str): The file path
        start_line (int, optional): Starting line number
        end_line (int, optional): Ending line number

    Returns:
        str: Formatted file header with optional line range
    """
    line_info = f" ({start_line}-{end_line})" if start_line and end_line else ""
    header = f"\n{cyan(bold(f'● {path}{line_info}'))}"
    divider = f"{gray('─' * (len(path) + len(line_info) + 2))}"
    return f"{header}\n{divider}"


def format_function_call(plugin_name, function_name, args=None):
    """Format a function call message for CLI output.

    Args:
        plugin_name (str): The name of the plugin
        function_name (str): The name of the function
        args (dict, optional): Function arguments

    Returns:
        str: Formatted function call message
    """
    args_str = ""
    if args:
        args_parts = []
        for key, value in args.items():
            if isinstance(value, str):
                args_parts.append(f'{key}="{value}"')
            else:
                args_parts.append(f"{key}={value}")
        args_str = ", ".join(args_parts)

    message = f"[Function Call] {plugin_name}.{function_name}({args_str})"
    return gray(message)


def format_function_result(plugin_name, function_name, result):
    """Format a function result message for CLI output.

    Args:
        plugin_name (str): The name of the plugin
        function_name (str): The name of the function
        result (str): The function result

    Returns:
        str: Formatted function result message
    """
    message = f"[Function Result] {plugin_name}.{function_name} → {result}"
    return gray(message)
