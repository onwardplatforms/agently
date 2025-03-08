"""Utility functions for Agently."""

# Import styles directly from the SDK
from agently_sdk import styles


# For backward compatibility
def format_action(msg):
    """Format an action message with blue bold styling."""
    return styles.blue.bold("Action:") + " " + msg


def format_result(msg, success=True):
    """Format a result message with success or error styling."""
    return styles.success(msg) if success else styles.error(msg)


def format_file_header(path, start_line=None, end_line=None):
    """Format a file header with cyan bold styling."""
    return styles.cyan.bold(f"● {path}")


# Export for convenience
__all__ = [
    "styles",
    "format_action",
    "format_result",
    "format_file_header",
]
