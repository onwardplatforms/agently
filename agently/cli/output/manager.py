"""
Output manager for CLI output.

This module provides the OutputManager class, which centralizes
all CLI output formatting and display.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import click

from .formatters import format_function_message
from .styles import apply_style, should_use_colors

logger = logging.getLogger(__name__)


class OutputManager:
    """Centralized manager for all CLI output."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the output manager.

        Args:
            config: Optional configuration for output behavior
        """
        self.config = config or {}
        self.color_enabled = self.config.get("colors", should_use_colors())
        self.stream_mode = False
        self.function_calls: List[str] = []
        self.context_stack: List[str] = []
        self.last_output_type: Optional[str] = None

    @property
    def current_context(self) -> str:
        """Get the current output context."""
        return self.context_stack[-1] if self.context_stack else "default"

    def enter_context(self, context: str):
        """Enter a new output context.

        Args:
            context: The context name

        Returns:
            Self for method chaining
        """
        self.context_stack.append(context)

        # Set context-specific options
        if context == "interactive":
            self.stream_mode = True

        return self

    def exit_context(self):
        """Exit the current context.

        Returns:
            Self for method chaining
        """
        if self.context_stack:
            context = self.context_stack.pop()

            # Reset context-specific options
            if context == "interactive":
                self.stream_mode = False

        return self

    def echo(self, message: str, nl: bool = True, color: Optional[str] = None, bold: bool = False):
        """Echo a message with formatting.

        Args:
            message: The message to echo
            nl: Whether to add a newline
            color: Optional color name
            bold: Whether to make the text bold
        """
        if not message:
            click.echo("", nl=nl)
            return

        formatted = apply_style(message, color=color, bold=bold)
        self._handle_spacing()
        click.echo(formatted, nl=nl)
        self.last_output_type = "text"

    def error(self, message: str, nl: bool = True):
        """Echo an error message.

        Args:
            message: The error message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="red")

    def success(self, message: str, nl: bool = True):
        """Echo a success message.

        Args:
            message: The success message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="green")

    def warning(self, message: str, nl: bool = True):
        """Echo a warning message.

        Args:
            message: The warning message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="yellow")

    def info(self, message: str, nl: bool = True):
        """Echo an informational message.

        Args:
            message: The informational message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="blue")

    def muted(self, message: str, nl: bool = True):
        """Echo a muted/secondary message.

        Args:
            message: The muted message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="gray")

    def header(self, message: str, nl: bool = True):
        """Echo a header message.

        Args:
            message: The header message
            nl: Whether to add a newline
        """
        self.echo(message, nl=nl, color="cyan", bold=True)

    def stream(self, chunk: str):
        """Echo a streaming chunk.

        Args:
            chunk: The chunk to echo
        """
        if chunk:
            click.echo(chunk, nl=False)

    def register_function_call(self, message: str) -> str:
        """Register a function call for display.

        Args:
            message: The function call message

        Returns:
            Empty string (for compatibility with existing code)
        """
        self.function_calls.append(message)

        if self.stream_mode:
            self._display_function_call(message)

        return ""

    def register_plugin_function(self, plugin_name: str, function_name: str, args: Optional[Dict[str, Any]] = None) -> str:
        """Register a plugin function call.

        Args:
            plugin_name: The name of the plugin
            function_name: The name of the function
            args: Optional function arguments

        Returns:
            Empty string (for compatibility with existing code)
        """
        message = format_function_message(function_name, args)
        return self.register_function_call(message)

    def reset_function_state(self):
        """Reset the function call state."""
        self.function_calls = []

    def get_formatted_output(self) -> str:
        """Get all formatted output based on current state.

        Returns:
            Properly formatted output with all function calls
        """
        if not self.function_calls:
            return ""

        # Format function calls without adding surrounding newlines
        function_lines = []
        for call in self.function_calls:
            function_lines.append(f"{apply_style('ƒ(x) ' + call + ' ...', 'muted')}")

        # Return function calls with a single newline between content
        return "\n".join(function_lines)

    def _display_function_call(self, message: str):
        """Display a function call in real-time.

        Args:
            message: The function call message
        """
        if self.last_output_type != "function":
            click.echo("\n", nl=False)

        click.echo(f"{apply_style('ƒ(x) ' + message + ' ...', 'muted')}", nl=False)
        self.last_output_type = "function"

    def _handle_spacing(self):
        """Handle spacing between different output types."""
        if self.last_output_type == "function":
            click.echo("\n", nl=False)

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        self.exit_context()
