"""
Specialized formatting functions for CLI output.

This module provides formatters for specific types of output,
such as plugin status, section headers, and function calls.
"""

from enum import Enum
from typing import Optional, Dict, Any, Union, List

from .styles import apply_style


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
        status_str = apply_style(f"+ {plugin_key}", "green")
    elif status == PluginStatus.UPDATED:
        status_str = apply_style(f"~ {plugin_key}", "yellow")
    elif status == PluginStatus.UNCHANGED:
        status_str = apply_style(f"  {plugin_key}", "gray")
    elif status == PluginStatus.REMOVED:
        status_str = apply_style(f"- {plugin_key}", "red")
    elif status == PluginStatus.FAILED:
        status_str = apply_style(f"× {plugin_key}", "red")
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
    return apply_style(f"{title}:", bold=True)


def format_plan_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format a summary of changes planned for plugins.
    
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
        parts.append(apply_style(f"+{added} to add", "green"))
    
    if updated > 0:
        parts.append(apply_style(f"~{updated} to update", "yellow"))
    
    if unchanged > 0:
        parts.append(f"{unchanged} unchanged")
    
    if removed > 0:
        parts.append(apply_style(f"-{removed} to remove", "red"))
    
    if failed > 0:
        parts.append(apply_style(f"{failed} failed", "red"))
    
    if not parts:
        return "No changes. Your plugin configuration is up to date."
    
    return "Plan: " + ", ".join(parts)


def format_apply_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format a summary of changes applied to plugins.
    
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
        parts.append(apply_style(f"{added} added", "green"))
    
    if updated > 0:
        parts.append(apply_style(f"{updated} updated", "yellow"))
    
    if unchanged > 0:
        parts.append(f"{unchanged} unchanged")
    
    if removed > 0:
        parts.append(apply_style(f"{removed} removed", "red"))
    
    if failed > 0:
        parts.append(apply_style(f"{failed} failed", "red"))
    
    if not parts:
        return "No changes applied. Your plugin configuration is up to date."
    
    return "Apply complete! Resources: " + ", ".join(parts)


def format_function_message(function_name: str, args: Optional[Dict[str, Any]] = None) -> str:
    """Create a human-readable message describing a function call.
    
    Args:
        function_name: The name of the function
        args: Optional function arguments
        
    Returns:
        Human-readable message
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

    return message


def format_file_header(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Format a file header with the file path and optional line numbers.
    
    Args:
        path: The file path
        start_line: Optional starting line number
        end_line: Optional ending line number
        
    Returns:
        Formatted file header
    """
    line_info = f" ({start_line}-{end_line})" if start_line and end_line else ""
    header = apply_style(f"● {path}{line_info}", "cyan", bold=True)
    divider = apply_style("─" * (len(path) + len(line_info) + 2), "gray")
    return f"\n{header}\n{divider}"


# Plugin-specific formatting functions
def format_action(message: str) -> str:
    """Format a plugin action message.
    
    Args:
        message: The action message
        
    Returns:
        The formatted message
    """
    return message


def format_result(message: str, success: bool = True) -> str:
    """Format a plugin result message.
    
    Args:
        message: The result message
        success: Whether the action was successful
        
    Returns:
        The formatted message
    """
    if success:
        return ""  # Don't show success results (avoid duplicating the final output)
    return f"✗ {message}" 