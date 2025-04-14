"""Formatting utilities for the Agently CLI.

This module provides functions for formatting output in the CLI.
"""

from typing import List

from agently_sdk import styles


def format_section_header(title: str) -> str:
    """Format a section header.

    Args:
        title (str): The title text

    Returns:
        str: Formatted header text
    """
    return f"{styles.bold(title)}"


def format_plan_summary(added: int, updated: int, unchanged: int, removed: int) -> str:
    """Format a summary of the plugin plan.

    Args:
        added: Number of plugins to add
        updated: Number of plugins to update
        unchanged: Number of plugins that are unchanged
        removed: Number of plugins to remove

    Returns:
        Formatted summary
    """
    total = added + updated + unchanged + removed

    if total == 0:
        return "No plugins found"

    # If no changes, just report the unchanged count
    if added == 0 and updated == 0 and removed == 0:
        return f"{styles.dim(f'• {total} plugins')} (no changes)"

    # Create a list of changes
    changes = []
    if added > 0:
        changes.append(f"{styles.green(f'+{added}')}")
    if updated > 0:
        changes.append(f"{styles.yellow(f'~{updated}')}")
    if removed > 0:
        changes.append(f"{styles.red(f'-{removed}')}")

    # Format the output like Terraform does
    return f"{styles.bold(f'• {total} plugins')} ({' '.join(changes)})"


def format_apply_summary(
    added: int, updated: int, unchanged: int, removed: int, failed: int = 0, prefix: str = "agents"
) -> str:
    """Format a validation result summary.

    Args:
        added: Number of items added
        updated: Number of items updated
        unchanged: Number of unchanged items
        removed: Number of items removed
        failed: Number of failed items
        prefix: The type of item (plugins or MCP servers)
    """
    # Special case for all items up-to-date
    if added == 0 and updated == 0 and removed == 0 and failed == 0 and unchanged > 0:
        return f"{styles.green('✓')} {unchanged} {prefix} ready"

    parts = []

    if added > 0:
        parts.append(f"{styles.green(f'+{added}')} added")
    if updated > 0:
        parts.append(f"{styles.yellow(f'~{updated}')} updated")
    if unchanged > 0:
        parts.append(f"{unchanged} unchanged")
    if removed > 0:
        parts.append(f"{styles.red(f'-{removed}')} removed")
    if failed > 0:
        parts.append(f"{styles.red(f'!{failed}')} failed")

    # Format in a compact way
    return f"{styles.green('✓')} {' · '.join(parts)}"


def format_validation_success(message: str) -> str:
    """Format a validation success message.

    Args:
        message (str): The success message

    Returns:
        str: Formatted success message
    """
    return f"{styles.green('✓')} {message}"


def format_validation_hint(message: str) -> str:
    """Format a validation hint message.

    Args:
        message (str): The hint message

    Returns:
        str: Formatted hint message
    """
    return f"  {styles.blue('•')} {message}"


def format_error(message: str) -> str:
    """Format an error message.

    Args:
        message (str): The error message

    Returns:
        str: Formatted error message
    """
    return f"{styles.red('Error:')} {message}"


def format_info(message: str) -> str:
    """Format an informational message.

    Args:
        message (str): The info message

    Returns:
        str: Formatted info message
    """
    return f"{styles.blue('Info:')} {message}"


def format_warning(message: str) -> str:
    """Format a warning message.

    Args:
        message (str): The warning message

    Returns:
        str: Formatted warning message
    """
    return f"{styles.yellow('Warning:')} {message}"


def format_success(message: str) -> str:
    """Format a success message.

    Args:
        message (str): The success message

    Returns:
        str: Formatted success message
    """
    return f"{styles.green(message)}"
