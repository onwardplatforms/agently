"""
Utility functions for Agently.
"""

# Import styles directly from the SDK
from agently_sdk import styles

# For backward compatibility
format_action = lambda msg: styles.blue.bold("Action:") + " " + msg
format_result = lambda msg, success=True: styles.success(msg) if success else styles.error(msg)
format_file_header = lambda path, start_line=None, end_line=None: styles.cyan.bold(f"● {path}")

# Export for convenience
__all__ = [
    "styles",
    "format_action",
    "format_result",
    "format_file_header",
]
