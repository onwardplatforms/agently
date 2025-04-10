"""Command line interface for the agent runtime."""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import click
import yaml
from agently_sdk import styles  # Import styles directly from SDK

from agently.agents.agent import Agent
from agently.config.parser import load_agent_config
from agently.conversation.context import ConversationContext, Message
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource
from agently.utils.logging import LogLevel, configure_logging

from .interactive import interactive_loop

logger = logging.getLogger(__name__)

# Define pass decorators for Click
def pass_client(f):
    """Decorator to pass a client to a command."""
    def wrapper(*args, **kwargs):
        # For now, just pass through
        return f(*args, **kwargs)
    return wrapper

def pass_config(f):
    """Decorator to pass a config to a command."""
    def wrapper(*args, **kwargs):
        # For now, just pass through
        return f(*args, **kwargs)
    return wrapper

# Define client and config classes
class Client:
    """Client for interacting with the agent."""
    def __init__(self):
        pass

class Config:
    """Configuration for the agent."""
    def __init__(self):
        self.agent_config_file = None
    
    def get_agent_config_file(self):
        """Get the agent configuration file path."""
        return self.agent_config_file

# Define plugin status enum directly here
class PluginStatus(Enum):
    """Status of a plugin during initialization."""

    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"


# Define the formatters directly here using SDK styles
def format_plugin_status(status: PluginStatus, plugin_key: str, details: Optional[str] = None, plugin_type: str = "sk") -> str:
    """Format a plugin status message.

    Args:
        status: Status of the plugin
        plugin_key: Plugin key (namespace/name)
        details: Additional details about the plugin
        plugin_type: Type of plugin (sk or mcp)

    Returns:
        Formatted status message
    """
    # Color-coded status indicators
    status_colors = {
        PluginStatus.ADDED: styles.green("+ "),
        PluginStatus.UPDATED: styles.yellow("~ "),
        PluginStatus.UNCHANGED: styles.dim("- "),
        PluginStatus.REMOVED: styles.red("- "),
        PluginStatus.FAILED: styles.red("✗ "),
    }

    # Text for status
    status_text = {
        PluginStatus.ADDED: "(new)",
        PluginStatus.UPDATED: "(updated)",
        PluginStatus.UNCHANGED: "(unchanged)",
        PluginStatus.REMOVED: "(removed)",
        PluginStatus.FAILED: "(failed)",
    }

    # Type indicator
    type_indicator = "[MCP]" if plugin_type == "mcp" else "[SK]"
    
    # Format output with type indicator
    output = f"{status_colors.get(status, '')}{plugin_key} {styles.dim(type_indicator)} {styles.dim(status_text.get(status, ''))}"
    
    if details:
        output += f" {styles.dim(details)}"
        
    return output


def format_section_header(title: str) -> str:
    """Format a section header."""
    return styles.bold(title) + ":"


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
    parts = []
    if added > 0:
        parts.append(f"+{added} new")
    if updated > 0:
        parts.append(f"~{updated} updated")
    if unchanged > 0:
        parts.append(f"-{unchanged} unchanged")
    if removed > 0:
        parts.append(f"-{removed} removed")
    
    if not parts:
        return "No changes"
    
    return f"Found {added + updated + unchanged + removed} plugins: {', '.join(parts)}"


def format_apply_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0, prefix: str = "plugins") -> str:
    """Format a validation result summary.
    
    Args:
        added: Number of items added
        updated: Number of items updated
        unchanged: Number of unchanged items
        removed: Number of items removed
        failed: Number of failed items
        prefix: The type of item (plugins or MCP servers)
    """
    total = added + updated + unchanged + removed

    # Special case for all items up-to-date
    if added == 0 and updated == 0 and removed == 0 and failed == 0 and unchanged > 0:
        return f"All {prefix} ({unchanged}) are ready and up-to-date"

    parts = []

    if added > 0:
        parts.append(styles.green(f"{added} added"))
    if updated > 0:
        parts.append(styles.yellow(f"{updated} updated"))
    if unchanged > 0:
        parts.append(styles.dim(f"{unchanged} unchanged"))
    if removed > 0:
        parts.append(styles.red(f"{removed} removed"))
    if failed > 0:
        parts.append(styles.red(f"{failed} failed"))

    return f"Validation complete: {total} {prefix} processed" + (", " + ", ".join(parts) if parts else "")


@click.group()
def cli():
    """agently.run - Declarative AI agents without code."""
    # Default to no logging unless explicitly requested
    configure_logging(level=LogLevel.NONE)


@cli.command(help="Initialize agent and dependencies")
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE'], case_sensitive=False), 
              help="Set the logging level. Overrides the LOG_LEVEL environment variable.")
def init(log_level):
    """Initialize agent and dependencies."""
    # Configure logging if specified via CLI
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
        
    try:
        # Load configuration
        config_file = Path("agently.yaml")
        if not config_file.exists():
            click.echo("Error: agently.yaml not found in current directory")
            sys.exit(1)
        
        click.echo(f"Reading configuration from {config_file}")
        
        # Initialize plugins and MCP servers - this will download and set up plugins
        _initialize_plugins(config_file)
        
        # Load and validate configuration
        config = load_agent_config(config_file)
        
        click.echo("Validation complete!")
        click.echo()
        click.echo("Agently is ready to run")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        logger.exception("Error during initialization")
        sys.exit(1)


@cli.command(help="Run agent in REPL mode")
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE'], case_sensitive=False), 
              help="Set the logging level. Overrides the LOG_LEVEL environment variable.")
def run(log_level):
    """Run agent in REPL mode."""
    # Configure logging if specified via CLI
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
        
    try:
        # Load configuration
        config_file = Path("agently.yaml")
        if not config_file.exists():
            click.echo("Error: agently.yaml not found in current directory")
            sys.exit(1)
        
        # Load and validate configuration
        config = load_agent_config(config_file)
        
        # Run interactive loop
        interactive_loop(config)
        
    except KeyboardInterrupt:
        click.echo("\nExiting...")
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        logger.exception("Error running agent")
        sys.exit(1)


@cli.command()
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE'], case_sensitive=False), 
              help="Set the logging level. Overrides the LOG_LEVEL environment variable.")
def list(log_level):
    """List installed plugins and MCP servers."""
    # Configure logging with INFO by default for this command since it's read-only
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
    else:
        configure_logging(level=LogLevel.INFO)

    try:
        # Determine lockfile path (at the same level as .agently folder)
        lockfile_path = Path.cwd() / "agently.lockfile.json"

        if not lockfile_path.exists():
            click.echo("No plugins installed")
            return

        # Read lockfile
        try:
            with open(lockfile_path, "r") as f:
                lockfile = json.load(f)
        except json.JSONDecodeError:
            click.echo("Error: Invalid lockfile")
            sys.exit(1)

        # Extract plugins from both SK and MCP categories
        sk_plugins = lockfile.get("plugins", {}).get("sk", {})
        mcp_plugins = lockfile.get("plugins", {}).get("mcp", {})
        
        # Handle old-style lockfiles if needed
        if "mcp_servers" in lockfile:
            # Merge old-style MCP servers into mcp_plugins
            mcp_plugins.update(lockfile.get("mcp_servers", {}))
        
        # Check if there are any plugins
        if not sk_plugins and not mcp_plugins:
            click.echo("No plugins installed")
            return

        # Display all plugins in a unified view
        total_plugins = len(sk_plugins) + len(mcp_plugins)
        click.echo(f"Installed plugins ({total_plugins}):")
        click.echo("-" * 60)

        # Display SK plugins
        for plugin_key, plugin_info in sk_plugins.items():
            click.echo(f"📦 {plugin_key} {styles.dim('[SK]')}")
            click.echo(f"  Version: {plugin_info['version']}")
            click.echo(f"  Commit: {plugin_info['commit_sha'][:8] if plugin_info.get('commit_sha') else 'unknown'}")
            click.echo(f"  Installed: {plugin_info.get('installed_at', 'unknown')}")
            click.echo(f"  Source: {plugin_info.get('repo_url') or plugin_info.get('source_path', 'unknown')}")
            click.echo("-" * 60)
        
        # Display MCP plugins
        for plugin_key, plugin_info in mcp_plugins.items():
            click.echo(f"🔌 {plugin_key} {styles.dim('[MCP]')}")
            click.echo(f"  Version: {plugin_info['version']}")
            if plugin_info.get('source_type') == 'github':
                click.echo(f"  Commit: {plugin_info['commit_sha'][:8] if plugin_info.get('commit_sha') else 'unknown'}")
            click.echo(f"  Command: {plugin_info.get('command', 'N/A')}")
            if plugin_info.get('args'):
                click.echo(f"  Args: {' '.join(plugin_info.get('args', []))}")
            click.echo(f"  Installed: {plugin_info.get('installed_at', 'unknown')}")
            click.echo(f"  Source: {plugin_info.get('repo_url') or plugin_info.get('source_path', 'unknown')}")
            click.echo("-" * 60)

    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error listing plugins: {e}")
        sys.exit(1)


def _initialize_plugins(config_path, quiet=False, force=False):
    """Initialize plugins and MCP servers based on a configuration file.

    Args:
        config_path: Path to the agent configuration file
        quiet: Whether to reduce output verbosity
        force: Force reinstallation of all plugins and MCP servers

    Returns:
        Set of installed plugin keys

    Raises:
        FileNotFoundError: If the configuration file does not exist
    """
    # Load the agent configuration
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    if force and not quiet:
        click.echo("Force mode enabled: reinstalling all plugins and MCP servers")

    if not quiet:
        click.echo("Scanning plugin and MCP server dependencies...")

    # Parse YAML configuration to extract plugins and MCP servers
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")

    # Get plugin and MCP server configurations
    plugins_config = config.get("plugins", {})
    mcp_servers_config = config.get("mcp_servers", {})

    # Determine lockfile path (at the same level as .agently folder)
    lockfile_path = Path.cwd() / "agently.lockfile.json"

    # Create empty lockfile if it doesn't exist
    if not lockfile_path.exists():
        logger.info("Creating new lockfile")
        lockfile = {
            "plugins": {
                "sk": {},
                "mcp": {}
            }
        }
        with open(lockfile_path, "w") as f:
            json.dump(lockfile, f, indent=2)
    else:
        # Load existing lockfile
        with open(lockfile_path, "r") as f:
            try:
                lockfile = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid lockfile, creating new one")
                lockfile = {
                    "plugins": {
                        "sk": {},
                        "mcp": {}
                    }
                }

        # Ensure the lockfile has the correct structure
        if "plugins" not in lockfile:
            lockfile["plugins"] = {}
        if "sk" not in lockfile["plugins"]:
            lockfile["plugins"]["sk"] = {}
        if "mcp" not in lockfile["plugins"]:
            lockfile["plugins"]["mcp"] = {}
            
        # If we have old-style lockfile, migrate the data
        if "mcp_servers" in lockfile:
            for key, value in lockfile["mcp_servers"].items():
                lockfile["plugins"]["mcp"][key] = value
            # Remove the old key
            del lockfile["mcp_servers"]
            
        # If we have old top-level plugins, migrate them to sk
        if isinstance(lockfile.get("plugins", {}), dict) and not any(k in lockfile["plugins"] for k in ["sk", "mcp"]):
            old_plugins = lockfile["plugins"]
            lockfile["plugins"] = {
                "sk": old_plugins,
                "mcp": {}
            }

    # Remove mcp_servers field if it exists - it's deprecated in favor of plugins.mcp
    if "mcp_servers" in lockfile:
        del lockfile["mcp_servers"]

    # Process the plugin configuration
    github_plugins = []
    local_plugins = []
    github_mcp_servers = []
    local_mcp_servers = []

    # Extract configured plugins
    if "github" in plugins_config:
        github_plugins = plugins_config["github"]

    if "local" in plugins_config:
        local_plugins = plugins_config["local"]

    # Extract configured MCP servers
    if "github" in mcp_servers_config:
        github_mcp_servers = mcp_servers_config["github"]

    if "local" in mcp_servers_config:
        local_mcp_servers = mcp_servers_config["local"]

    # Gather plugin details for consistent formatting
    plugin_details = {}
    mcp_server_details = {}

    # Determine which plugins to add, update, and remove
    to_add = set()
    to_update = set()
    unchanged = set()
    to_remove = set()

    # Track successfully installed plugins
    installed_plugins = set()
    failed = set()

    # Same for MCP servers
    mcp_to_add = set()
    mcp_to_update = set()
    mcp_unchanged = set()
    mcp_to_remove = set()
    installed_mcp_servers = set()
    mcp_failed = set()

    # Process GitHub plugins
    for github_plugin_config in github_plugins:
        repo_url = github_plugin_config["source"]
        version = github_plugin_config.get("version", "main")
        plugin_path = github_plugin_config.get("plugin_path", "")
        plugin_type = github_plugin_config.get("type", "sk")  # Get plugin type from config

        # Create a GitHubPluginSource
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=plugin_path,
            force_reinstall=False,  # We'll handle force flag separately
            plugin_type=plugin_type,  # Pass plugin type from config
        )

        plugin_key = f"{source.namespace}/{source.name}"
        plugin_details[plugin_key] = f"version={version}"

        # Determine where to check based on plugin type
        target_section = "mcp" if plugin_type == "mcp" else "sk"
        
        # Add this plugin to the appropriate sets based on plugin type
        if plugin_type == "mcp":
            if plugin_key in lockfile.get("plugins", {}).get("mcp", {}):
                # MCP plugin exists in lockfile, check if it needs updating
                lockfile_sha = lockfile["plugins"]["mcp"][plugin_key].get("commit_sha", "")
                if force or source.needs_update(lockfile_sha):
                    mcp_to_update.add(plugin_key)
                else:
                    mcp_unchanged.add(plugin_key)
            else:
                # New MCP plugin
                mcp_to_add.add(plugin_key)
        else:
            # Standard plugin
            if plugin_key in lockfile.get("plugins", {}).get("sk", {}):
                # Plugin exists in lockfile, check if it needs updating
                lockfile_sha = lockfile["plugins"]["sk"][plugin_key].get("commit_sha", "")
                if force or source.needs_update(lockfile_sha):
                    to_update.add(plugin_key)
                else:
                    unchanged.add(plugin_key)
            else:
                # New plugin
                to_add.add(plugin_key)

    # Process local plugins
    for local_plugin_config in local_plugins:
        source_path = local_plugin_config["source"]
        abs_source_path = config_path.parent / source_path

        # Use the same naming approach as during detection
        plugin_name = os.path.basename(source_path)
        local_source = LocalPluginSource(
            path=Path(abs_source_path),
            namespace="local",
            name=plugin_name,
            force_reinstall=force,  # Pass the force flag to control reinstallation
        )

        plugin_key = f"{local_source.namespace}/{local_source.name}"
        plugin_details[plugin_key] = f"path={source_path}"

        # Determine where to check based on plugin type
        target_section = "mcp" if local_source.plugin_type == "mcp" else "sk"

        if plugin_key in lockfile.get("plugins", {}).get(target_section, {}):
            # Plugin exists in lockfile, check if it needs updating
            lockfile_sha = lockfile["plugins"][target_section][plugin_key].get("sha256", "")
            if force or local_source.needs_update(lockfile_sha):
                to_update.add(plugin_key)
            else:
                unchanged.add(plugin_key)
        else:
            # New plugin
            to_add.add(plugin_key)

    # Process GitHub MCP servers
    for github_mcp_config in github_mcp_servers:
        repo_url = github_mcp_config["source"]
        version = github_mcp_config.get("version", "main")
        server_path = github_mcp_config.get("server_path", "")
        name = github_mcp_config.get("name", "")

        # Create a GitHubPluginSource for the MCP server
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=server_path,
            force_reinstall=force,
            cache_dir=Path.cwd() / ".agently" / "plugins" / "mcp",
            name=name,
            plugin_type="mcp",  # Specify that this is an MCP server
        )

        mcp_key = f"{source.namespace}/{source.name}"
        mcp_server_details[mcp_key] = f"version={version}"

        if mcp_key in lockfile.get("plugins", {}).get("mcp", {}):
            # MCP server exists in lockfile, check if it needs updating
            lockfile_sha = lockfile["plugins"]["mcp"][mcp_key].get("commit_sha", "")
            if force or source.needs_update(lockfile_sha):
                mcp_to_update.add(mcp_key)
            else:
                mcp_unchanged.add(mcp_key)
        else:
            # New MCP server
            mcp_to_add.add(mcp_key)

    # Process local MCP servers
    for local_mcp_config in local_mcp_servers:
        name = local_mcp_config.get("name", "")
        source_path = local_mcp_config.get("source", "")
        
        if source_path:
            abs_source_path = config_path.parent / source_path
            # Use the same naming approach as during detection
            if not name:
                name = os.path.basename(source_path)
            
            # Create a local MCP source similar to plugin sources
            local_source = LocalPluginSource(
                path=Path(abs_source_path),
                namespace="local",
                name=name,
                force_reinstall=force,
                cache_dir=Path.cwd() / ".agently" / "plugins" / "mcp",
                plugin_type="mcp",  # Specify that this is an MCP server
            )

            mcp_key = f"{local_source.namespace}/{name}"
            mcp_server_details[mcp_key] = f"path={source_path}"

            if mcp_key in lockfile.get("plugins", {}).get("mcp", {}):
                # MCP server exists in lockfile, check if it needs updating
                lockfile_sha = lockfile["plugins"]["mcp"][mcp_key].get("sha256", "")
                if force or local_source.needs_update(lockfile_sha):
                    mcp_to_update.add(mcp_key)
                else:
                    mcp_unchanged.add(mcp_key)
            else:
                # New MCP server
                mcp_to_add.add(mcp_key)
        else:
            # For local MCP servers without source files, just use the name
            mcp_key = f"local/{name}"
            mcp_server_details[mcp_key] = "command-only"
            
            if mcp_key in lockfile.get("plugins", {}).get("mcp", {}):
                # For command-only MCP servers, only update if forced
                if force:
                    mcp_to_update.add(mcp_key)
                else:
                    mcp_unchanged.add(mcp_key)
            else:
                # New MCP server
                mcp_to_add.add(mcp_key)

    # Find plugins in lockfile that aren't in the config
    lockfile_plugins = set(lockfile.get("plugins", {}).get("sk", {}).keys())
    config_plugins = set()
    for plugin_key in to_add | to_update | unchanged:
        config_plugins.add(plugin_key)

    # Plugins to remove are those in the lockfile but not in the config
    for plugin_key in lockfile_plugins - config_plugins:
        to_remove.add(plugin_key)

    # Do the same for MCP servers
    lockfile_mcp_servers = set(lockfile.get("plugins", {}).get("mcp", {}).keys())
    config_mcp_servers = set()
    for mcp_key in mcp_to_add | mcp_to_update | mcp_unchanged:
        config_mcp_servers.add(mcp_key)

    # MCP servers to remove are those in the lockfile but not in the config
    for mcp_key in lockfile_mcp_servers - config_mcp_servers:
        mcp_to_remove.add(mcp_key)

    # Display plugin statuses
    total_plugins = len(to_add) + len(to_update) + len(unchanged) + len(to_remove)
    total_mcp_plugins = len(mcp_to_add) + len(mcp_to_update) + len(mcp_unchanged) + len(mcp_to_remove)
    
    if total_plugins + total_mcp_plugins > 0:
        if total_plugins > 0:
            logger.info(f"--- Semantic Kernel Plugins ---")
            for plugin_key in to_add:
                logger.info(format_plugin_status(PluginStatus.ADDED, plugin_key, plugin_details.get(plugin_key, ""), plugin_type="sk"))
            for plugin_key in to_update:
                logger.info(format_plugin_status(PluginStatus.UPDATED, plugin_key, plugin_details.get(plugin_key, ""), plugin_type="sk"))
            for plugin_key in unchanged:
                logger.info(format_plugin_status(PluginStatus.UNCHANGED, plugin_key, plugin_details.get(plugin_key, ""), plugin_type="sk"))
            for plugin_key in to_remove:
                logger.info(format_plugin_status(PluginStatus.REMOVED, plugin_key, plugin_details.get(plugin_key, ""), plugin_type="sk"))
        
        if total_mcp_plugins > 0:
            logger.info(f"--- MCP Plugins ---")
            for plugin_key in mcp_to_add:
                logger.info(format_plugin_status(PluginStatus.ADDED, plugin_key, mcp_server_details.get(plugin_key, ""), plugin_type="mcp"))
            for plugin_key in mcp_to_update:
                logger.info(format_plugin_status(PluginStatus.UPDATED, plugin_key, mcp_server_details.get(plugin_key, ""), plugin_type="mcp"))
            for plugin_key in mcp_unchanged:
                logger.info(format_plugin_status(PluginStatus.UNCHANGED, plugin_key, mcp_server_details.get(plugin_key, ""), plugin_type="mcp"))
            for plugin_key in mcp_to_remove:
                logger.info(format_plugin_status(PluginStatus.REMOVED, plugin_key, mcp_server_details.get(plugin_key, ""), plugin_type="mcp"))

    # Now perform the actual installation

    # Install GitHub plugins
    for github_plugin_config in github_plugins:
        repo_url = github_plugin_config["source"]
        version = github_plugin_config.get("version", "main")
        plugin_path = github_plugin_config.get("plugin_path", "")
        plugin_type = github_plugin_config.get("type", "sk")  # Get plugin type from config

        # Create a GitHubPluginSource
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=plugin_path,
            force_reinstall=force,  # Pass the force flag to control reinstallation
            plugin_type=plugin_type,  # Pass plugin type from config
        )

        plugin_key = f"{source.namespace}/{source.name}"

        # Skip if unchanged and not forced
        if plugin_key in unchanged and not force:
            installed_plugins.add(plugin_key)
            continue

        try:
            # Load plugin
            plugin_class = source.load()

            # Get plugin info for lockfile
            plugin_info = source._get_plugin_info(plugin_class)

            # Add to installed plugins
            installed_plugins.add(plugin_key)

            # Update lockfile with plugin info
            if plugin_info.get("plugin_type") == "mcp":
                lockfile["plugins"]["mcp"][plugin_key] = plugin_info
            else:
                lockfile["plugins"]["sk"][plugin_key] = plugin_info

            # Plugins are loaded silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e), plugin_type="sk"))

    # Install local plugins
    for local_plugin_config in local_plugins:
        source_path = local_plugin_config["source"]
        abs_source_path = config_path.parent / source_path

        # Use the same naming approach as during detection
        plugin_name = os.path.basename(source_path)
        local_source = LocalPluginSource(
            path=Path(abs_source_path),
            namespace="local",
            name=plugin_name,
            force_reinstall=force,  # Pass the force flag to control reinstallation
        )

        plugin_key = f"{local_source.namespace}/{local_source.name}"

        # Skip if unchanged and not forced
        if plugin_key in unchanged and not force:
            installed_plugins.add(plugin_key)
            continue

        try:
            # Load plugin
            plugin_class = local_source.load()

            # Get plugin info for lockfile
            plugin_info = local_source._get_plugin_info(plugin_class)

            # Add to installed plugins
            installed_plugins.add(plugin_key)

            # Update lockfile with plugin info
            if plugin_info.get("plugin_type") == "mcp":
                lockfile["plugins"]["mcp"][plugin_key] = plugin_info
            else:
                lockfile["plugins"]["sk"][plugin_key] = plugin_info

            # Plugins are loaded silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install local plugin {source_path}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e), plugin_type="sk"))

    # Install GitHub MCP servers
    for github_mcp_config in github_mcp_servers:
        repo_url = github_mcp_config["source"]
        version = github_mcp_config.get("version", "main")
        server_path = github_mcp_config.get("server_path", "")
        name = github_mcp_config.get("name", "")
        command = github_mcp_config.get("command", "")
        args = github_mcp_config.get("args", [])
        description = github_mcp_config.get("description", "")
        variables = github_mcp_config.get("variables", {})

        # Create a GitHubPluginSource for the MCP server
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=server_path,
            force_reinstall=force,
            cache_dir=Path.cwd() / ".agently" / "plugins" / "mcp",
            name=name,
            plugin_type="mcp",  # Specify that this is an MCP server
        )

        mcp_key = f"{source.namespace}/{source.name}"

        # Skip if unchanged and not forced
        if mcp_key in mcp_unchanged and not force:
            installed_mcp_servers.add(mcp_key)
            continue

        try:
            # For MCP servers, we don't need to load a plugin class
            # We just need to clone/update the repository
            source._clone_or_update_repo(source.cache_dir / source.name)
            
            # Get current timestamp in ISO format
            current_time = datetime.utcnow().isoformat()
            
            # Get the MCP server directory
            mcp_dir = source.cache_dir / source.name
            
            # Get the commit SHA
            commit_sha = source._get_repo_sha(mcp_dir)
            
            # Create MCP server info for lockfile
            mcp_info = {
                "namespace": source.namespace,
                "name": source.name,
                "full_name": f"{source.namespace}/{source.name}",
                "version": version,
                "source_type": "github",
                "repo_url": source.repo_url,
                "server_path": server_path,
                "command": command,
                "args": args,
                "description": description,
                "variables": variables,
                "commit_sha": commit_sha,
                "installed_at": current_time,
            }

            # Add to installed MCP servers
            installed_mcp_servers.add(mcp_key)

            # Update lockfile with MCP server info
            if mcp_info.get("plugin_type") == "mcp":
                lockfile["plugins"]["mcp"][mcp_key] = mcp_info
            else:
                lockfile["plugins"]["sk"][mcp_key] = mcp_info

            # MCP servers are installed silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install GitHub MCP server {repo_url}: {e}")
            mcp_failed.add(mcp_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, mcp_key, str(e), plugin_type="mcp"))

    # Install local MCP servers
    for local_mcp_config in local_mcp_servers:
        name = local_mcp_config.get("name", "")
        source_path = local_mcp_config.get("source", "")
        command = local_mcp_config.get("command", "")
        args = local_mcp_config.get("args", [])
        description = local_mcp_config.get("description", "")
        variables = local_mcp_config.get("variables", {})
        
        mcp_key = f"local/{name}"
        
        # Skip if unchanged and not forced
        if mcp_key in mcp_unchanged and not force:
            installed_mcp_servers.add(mcp_key)
            continue
        
        try:
            # Create directory structure for MCP servers
            mcp_servers_dir = Path.cwd() / ".agently" / "plugins" / "mcp"
            mcp_servers_dir.mkdir(parents=True, exist_ok=True)
            
            # Get current timestamp in ISO format
            current_time = datetime.utcnow().isoformat()
            
            # For local MCP servers with source files, calculate a SHA
            plugin_sha = ""
            if source_path:
                abs_source_path = config_path.parent / source_path
                local_source = LocalPluginSource(
                    path=Path(abs_source_path),
                    namespace="local",
                    name=name,
                    force_reinstall=force,
                    cache_dir=Path.cwd() / ".agently" / "plugins" / "mcp",
                    plugin_type="mcp",  # Specify that this is an MCP server
                )
                plugin_sha = local_source._calculate_plugin_sha()
            
            # Create MCP server info for lockfile
            mcp_info = {
                "namespace": "local",
                "name": name,
                "full_name": name,
                "version": "local",
                "source_type": "local",
                "source_path": source_path,
                "command": command,
                "args": args,
                "description": description,
                "variables": variables,
                "sha256": plugin_sha,
                "installed_at": current_time,
            }
            
            # Add to installed MCP servers
            installed_mcp_servers.add(mcp_key)
            
            # Update lockfile with MCP server info
            if mcp_info.get("plugin_type") == "mcp":
                lockfile["plugins"]["mcp"][mcp_key] = mcp_info
            else:
                lockfile["plugins"]["sk"][mcp_key] = mcp_info
            
            # MCP servers are installed silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install local MCP server {name}: {e}")
            mcp_failed.add(mcp_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, mcp_key, str(e), plugin_type="mcp"))

    # Remove plugins that are no longer in the config
    for plugin_key in to_remove:
        # Plugins are removed silently since the status is already shown
        lockfile["plugins"]["sk"].pop(plugin_key, None)
    
    # Remove MCP servers that are no longer in the config
    for mcp_key in mcp_to_remove:
        # MCP servers are removed silently since the status is already shown
        lockfile["plugins"]["mcp"].pop(mcp_key, None)

    # Write updated lockfile
    with open(lockfile_path, "w") as f:
        json.dump(lockfile, f, indent=2)

    # Check if there were any failures
    if failed:
        if not quiet:
            click.echo(f"\nWarning: {len(failed)} plugins failed to install.")
        logger.warning(f"Failed to install plugins: {', '.join(failed)}")
    
    if mcp_failed:
        if not quiet:
            click.echo(f"\nWarning: {len(mcp_failed)} MCP servers failed to install.")
        logger.warning(f"Failed to install MCP servers: {', '.join(mcp_failed)}")

    # Display plugin status summaries
    if not quiet:
        click.echo("\nPlugin status:")
        click.echo(format_apply_summary(
            len(to_add), len(to_update), len(unchanged), len(to_remove), len(failed), "plugins"))
        
        click.echo("\nMCP server status:")
        click.echo(format_apply_summary(
            len(mcp_to_add), len(mcp_to_update), len(mcp_unchanged), len(mcp_to_remove), len(mcp_failed), "MCP servers"))

    return installed_plugins


def interactive_loop_with_reasoning(agent, config, context):
    """Run the interactive agent loop with continuous reasoning enabled.

    Args:
        agent: The Agent instance
        config: The agent configuration
        context: The conversation context
    """
    try:
        import asyncio
        
        logger.info("Starting interactive loop with reasoning")
        
        # Display welcome message
        provider = config.model.provider if hasattr(config.model, "provider") else "unknown"
        model_name = config.model.model if hasattr(config.model, "model") else str(config.model)
        
        click.echo(f"\nThe agent {config.name} has been initialized using {provider} {model_name}")
        if config.description:
            click.echo(config.description)
            
        click.echo("\nType a message to begin. Type exit to quit.\n")
        
        # Main interaction loop
        while True:
            try:
                # Get user input
                user_input = click.prompt("You", prompt_suffix="> ")
                logger.debug(f"User input: {user_input}")
                
                # Check for exit
                if user_input.lower() in ["exit", "quit"]:
                    logger.info("User requested exit")
                    break
                    
                # Create message object
                from agently.conversation.context import Message
                message = Message(content=user_input, role="user")
                
                # Process with continuous reasoning
                click.echo("\nAssistant (thinking)> ", nl=False)
                
                # Use our new continuous reasoning method
                reasoning_chunks = []
                
                # Define the async process function that we'll use with the event loop
                async def process_message():
                    async for chunk in agent.process_continuous_reasoning(message, context):
                        reasoning_chunks.append(chunk)
                        click.echo(chunk, nl=False)
                
                # Run the coroutine inside the current event loop
                loop = asyncio.get_event_loop()
                loop.run_until_complete(process_message())
                
                click.echo("\n")  # Add a newline after response
                
            except KeyboardInterrupt:
                logger.info("User interrupted with Ctrl+C")
                click.echo("\nExiting...")
                break
            except Exception as e:
                logger.exception(f"Error in interactive loop: {e}")
                click.echo(f"\nError: {e}")
        
        logger.info("Interactive loop with reasoning completed")
    except Exception as e:
        logger.exception(f"Error in interactive loop: {e}")
        click.echo(f"\nError: {e}")
