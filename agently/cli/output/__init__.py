"""
CLI output module for Agently.

This module provides a centralized system for managing CLI output,
including colors, styles, and formatting.
"""

from .manager import OutputManager
from .formatters import (
    format_action,
    format_file_header,
    format_function_message,
    format_result,
    PluginStatus,
)

# Create a singleton instance
cli = OutputManager()

# Export commonly used functions for convenience
echo = cli.echo
error = cli.error
success = cli.success
warning = cli.warning
info = cli.info
muted = cli.muted
header = cli.header
stream = cli.stream
register_function_call = cli.register_function_call
register_plugin_function = cli.register_plugin_function

# Context manager
class context:
    """Context manager for CLI output contexts."""
    
    def __init__(self, context_name):
        self.context_name = context_name
    
    def __enter__(self):
        cli.enter_context(self.context_name)
        return cli
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        cli.exit_context()

# Define public interface
__all__ = [
    'cli',
    'echo',
    'error',
    'success',
    'warning',
    'info',
    'muted',
    'header',
    'stream',
    'register_function_call',
    'register_plugin_function',
    'context',
    'format_action',
    'format_file_header',
    'format_function_message',
    'format_result',
    'PluginStatus',
] 