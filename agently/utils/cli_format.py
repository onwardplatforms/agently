"""CLI formatting utilities for Agently.

This module provides formatting functions for CLI output,
including colored text and function call formatting.
"""

import sys
from typing import List

# Track function call state for formatting
_function_calls: List[str] = []
_function_state_reset: bool = True


def reset_function_state():
    """Reset the function call state to start fresh for each interaction."""
    global _function_calls, _function_state_reset
    _function_calls = []
    _function_state_reset = True


def get_formatted_output():
    """Get all formatted output based on current state.

    Returns:
        str: Properly formatted output with all function calls
    """
    global _function_calls

    if not _function_calls:
        return ""

    # Format function calls without adding surrounding newlines
    # (newlines are handled in interactive.py)
    function_lines = []
    for call in _function_calls:
        function_lines.append(f"{gray('→ ' + call + ' ...')}")

    # Return function calls with a single newline between content
    # No trailing newline - that's handled in interactive.py
    return "\n".join(function_lines)


def register_function_call(message):
    """Register a function call to be formatted later.

    Args:
        message: The function call message

    Returns:
        str: Empty string as we don't output immediately
    """
    global _function_calls, _function_state_reset

    if _function_state_reset:
        _function_calls = []
        _function_state_reset = False

    _function_calls.append(message)
    return ""  # Don't output anything now, output is handled centrally


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
        str: Empty string, as we just register the call
    """
    return register_function_call(message)


def print_agent_message(message: str) -> str:
    """Print an agent action message with arrow.

    Args:
        message (str): The message content

    Returns:
        str: Empty string, as we just register the call
    """
    return register_function_call(message)


def format_result(message: str, success: bool = True) -> str:
    """Format a plugin result message.

    Args:
        message (str): The result message
        success (bool): Whether the action was successful

    Returns:
        str: Formatted result message with appropriate color
    """
    if success:
        return ""  # Don't show success results (avoid duplicating the final output)
    return register_function_call(f"✗ {message}")


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
        str: Empty string, as we just register the call
    """
    # Create a more conversational message based on function name and args
    message = function_name.replace("_", " ")

    # Add specific details for common functions
    if function_name == "greet":
        message = "saying hello"
    elif function_name == "search" and args and "query" in args:
        message = f"searching for '{args['query']}'"
    elif function_name == "calculate" and args:
        message = "calculating result"
    elif function_name == "remember_name" and args and "name" in args:
        message = "remembering name"
    elif function_name == "time_greeting":
        message = "creating time-based greeting"
    elif function_name == "farewell":
        message = "saying goodbye"

    return register_function_call(message)


def format_function_result(plugin_name, function_name, result):
    """Format a function result message for CLI output.

    Args:
        plugin_name (str): The name of the plugin
        function_name (str): The name of the function
        result: The function result

    Returns:
        str: Empty string, as function results are part of the response
    """
    # Don't show function results to avoid duplicating the final output
    return ""
