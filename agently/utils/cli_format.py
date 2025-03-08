"""CLI formatting utilities for Agently.

This module provides formatting functions for CLI output,
including colored text and function call formatting.

Note: This module is being deprecated in favor of agently.cli.output.
It is maintained for backward compatibility.
"""

import sys
from enum import Enum
from typing import Dict, List, Optional, Set

# Import the new centralized output system
from agently.cli.output import cli

# Track function call state for formatting
_function_calls: List[str] = []
_function_state_reset: bool = True


def reset_function_state():
    """Reset the function call state to start fresh for each interaction."""
    cli.reset_function_state()


def get_formatted_output():
    """Get all formatted output based on current state.

    Returns:
        str: Properly formatted output with all function calls
    """
    return cli.get_formatted_output()


def register_function_call(message):
    """Register a function call to be formatted later.

    Args:
        message: The function call message

    Returns:
        str: Empty string as we don't output immediately
    """
    return cli.register_function_call(message)


# ANSI color codes
class Color:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    GRAY = "\033[90m"


class PluginStatus(Enum):
    """Status of a plugin during initialization."""

    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"


def format_plugin_status(status: PluginStatus, plugin_key: str, details: Optional[str] = None) -> str:
    """Format a plugin status message in Terraform-like style.

    Args:
        status: The status of the plugin
        plugin_key: The plugin identifier (namespace/name)
        details: Optional details about the plugin (version, path, etc.)

    Returns:
        Formatted status message
    """
    prefix = "  "

    if status == PluginStatus.ADDED:
        status_str = f"{Color.GREEN}+ {plugin_key}{Color.RESET}"
    elif status == PluginStatus.UPDATED:
        status_str = f"{Color.YELLOW}~ {plugin_key}{Color.RESET}"
    elif status == PluginStatus.UNCHANGED:
        status_str = f"{Color.GRAY}  {plugin_key}{Color.RESET}"
    elif status == PluginStatus.REMOVED:
        status_str = f"{Color.RED}- {plugin_key}{Color.RESET}"
    elif status == PluginStatus.FAILED:
        status_str = f"{Color.RED}× {plugin_key}{Color.RESET}"
    else:
        status_str = f"  {plugin_key}"

    if details:
        return f"{prefix}{status_str} ({details})"
    else:
        return f"{prefix}{status_str}"


def format_section_header(title: str) -> str:
    """Format a section header in Terraform-like style.

    Args:
        title: The section title

    Returns:
        Formatted section header
    """
    return f"{Color.BOLD}{title}:{Color.RESET}"


def format_plan_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format a plan summary in Terraform-like style.

    Args:
        added: Number of plugins to be added
        updated: Number of plugins to be updated
        unchanged: Number of plugins that are unchanged
        removed: Number of plugins to be removed
        failed: Number of plugins that failed to process

    Returns:
        Formatted plan summary
    """
    parts = []

    if added > 0:
        parts.append(f"{Color.GREEN}+{added} to add{Color.RESET}")

    if updated > 0:
        parts.append(f"{Color.YELLOW}~{updated} to update{Color.RESET}")

    if unchanged > 0:
        parts.append(f"{unchanged} unchanged")

    if removed > 0:
        parts.append(f"{Color.RED}-{removed} to remove{Color.RESET}")

    if failed > 0:
        parts.append(f"{Color.RED}{failed} failed{Color.RESET}")

    if not parts:
        return "No changes. Your plugin configuration is up to date."

    return "Plan: " + ", ".join(parts)


def format_apply_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format an apply summary in Terraform-like style.

    Args:
        added: Number of plugins added
        updated: Number of plugins updated
        unchanged: Number of plugins that were unchanged
        removed: Number of plugins removed
        failed: Number of plugins that failed to process

    Returns:
        Formatted apply summary
    """
    parts = []

    if added > 0:
        parts.append(f"{Color.GREEN}{added} added{Color.RESET}")

    if updated > 0:
        parts.append(f"{Color.YELLOW}{updated} updated{Color.RESET}")

    if unchanged > 0:
        parts.append(f"{unchanged} unchanged")

    if removed > 0:
        parts.append(f"{Color.RED}{removed} removed{Color.RESET}")

    if failed > 0:
        parts.append(f"{Color.RED}{failed} failed{Color.RESET}")

    if not parts:
        return "No changes applied. Your plugin configuration is up to date."

    return "Apply complete! Resources: " + ", ".join(parts)


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
        result += Color.BOLD
    if italic:
        result += Color.ITALIC
    if underline:
        result += Color.UNDERLINE
    if color:
        result += color

    result += str(text) + Color.RESET
    return result


def gray(text):
    """Format text in gray color.

    Args:
        text (str): The text to format

    Returns:
        str: Gray-colored text
    """
    return format_text(text, color=Color.GRAY)


def green(text):
    """Format text in green color.

    Args:
        text (str): The text to format

    Returns:
        str: Green-colored text
    """
    return format_text(text, color=Color.GREEN)


def yellow(text):
    """Format text in yellow color.

    Args:
        text (str): The text to format

    Returns:
        str: Yellow-colored text
    """
    return format_text(text, color=Color.YELLOW)


def red(text):
    """Format text in red color.

    Args:
        text (str): The text to format

    Returns:
        str: Red-colored text
    """
    return format_text(text, color=Color.RED)


def blue(text):
    """Format text in blue color.

    Args:
        text (str): The text to format

    Returns:
        str: Blue-colored text
    """
    return format_text(text, color=Color.BLUE)


def cyan(text):
    """Format text in cyan color.

    Args:
        text (str): The text to format

    Returns:
        str: Cyan-colored text
    """
    return format_text(text, color=Color.CYAN)


def magenta(text):
    """Format text in magenta color.

    Args:
        text (str): The text to format

    Returns:
        str: Magenta-colored text
    """
    return format_text(text, color=Color.MAGENTA)


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
