"""Utility modules for Agently."""

# Import from cli_format for backward compatibility
# These functions now delegate to the new centralized output system
from .cli_format import (  # Basic color functions; Function call formatting; Plugin action formatting
    blue,
    bold,
    cyan,
    format_action,
    format_file_header,
    format_function_call,
    format_function_result,
    format_result,
    get_formatted_output,
    gray,
    green,
    magenta,
    print_agent_message,
    red,
    reset_function_state,
    yellow,
)
