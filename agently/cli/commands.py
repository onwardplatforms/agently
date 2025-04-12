"""Command line interface for the agent runtime."""

import json
import logging
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import click
import yaml
from agently_sdk import styles  # Import styles directly from SDK

from agently.config.parser import find_config_file, get_all_agents, load_agent_config
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource
from agently.utils.logging import LogLevel, configure_logging
from agently.version import __version__

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
def format_plugin_status(
    status: PluginStatus, plugin_key: str, details: Optional[str] = None, plugin_type: str = "sk"
) -> str:
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
    status_icons = {
        PluginStatus.ADDED: styles.green("+ "),
        PluginStatus.UPDATED: styles.yellow("↻ "),
        PluginStatus.UNCHANGED: styles.dim("· "),
        PluginStatus.REMOVED: styles.red("- "),
        PluginStatus.FAILED: styles.red("✗ "),
    }

    # Extract version from details if available
    version = "latest"
    if details:
        if details.startswith("version="):
            version = details.split("=")[1]
        elif details.startswith("path="):
            version = "local"

    # Format output with name, version, and type
    output = f"{status_icons.get(status, '')}{plugin_key} {styles.dim(version)} {styles.dim(f'({plugin_type.upper()})')}"

    return output


def format_section_header(title: str) -> str:
    """Format a section header."""
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
    added + updated + unchanged + removed

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


@click.group()
def cli():
    """agently.run - Declarative AI agents without code."""
    # Default to no logging unless explicitly requested
    configure_logging(level=LogLevel.NONE)


@cli.command(help="Initialize agent and dependencies")
@click.argument("agent_id", required=False)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], case_sensitive=False),
    help="Set the logging level. Overrides the LOG_LEVEL environment variable.",
)
@click.option(
    "--file", "-f",
    help="Path to agent configuration file",
)
def init(agent_id, log_level, file):
    """Initialize agent and dependencies."""
    # Configure logging if specified via CLI
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)

    try:
        # Find configuration file
        config_file = find_config_file(file)
        if not config_file:
            click.echo("Error: No configuration file found")
            sys.exit(1)

        click.echo("Initializing Agently...")
        click.echo()

        # First step: Validate configuration
        click.echo("Validating agent configuration...")
        # Just loading the config validates it
        config = yaml.safe_load(open(config_file, "r"))
        if "agents" in config and config["agents"]:
            num_agents = len(config["agents"])
            click.echo(f"{styles.green('✓')} Configuration validated ({num_agents} agents defined)")
        else:
            click.echo(f"{styles.green('✓')} Configuration validated (single agent)")
        click.echo()

        # Second step: Initialize plugins
        click.echo("Initializing plugins...")
        
        # Initialize plugins and MCP servers
        stats = _initialize_plugins(config_file, agent_id=agent_id)

        # Final success message
        click.echo()
        click.echo(f"{styles.green('Agently has been successfully initialized!')}")
        click.echo()
        
        if agent_id:
            click.echo(f"You can now run the agent with: agently run {agent_id}")
        else:
            click.echo("You can now run Agently with: agently run")
            click.echo("To list available agents, use: agently list agents")
        
    except Exception as e:
        click.echo(f"{styles.red('Error:')} {str(e)}")
        logger.exception("Error during initialization")
        sys.exit(1)


@cli.command(help="Run agent in REPL mode")
@click.argument("agent_id", required=False)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], case_sensitive=False),
    help="Set the logging level. Overrides the LOG_LEVEL environment variable.",
)
@click.option(
    "--file", "-f",
    help="Path to agent configuration file",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force run without checking initialization status",
)
def run(agent_id, log_level, file, force):
    """Run agent in REPL mode."""
    # Configure logging if specified via CLI
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)

    try:
        # Find configuration file
        config_file = find_config_file(file)
        if not config_file:
            click.echo("Error: No configuration file found")
            sys.exit(1)

        # Load specific agent or first agent
        config = load_agent_config(config_file, agent_id)
        
        # Verify agent is initialized unless --force is used
        if not force:
            # Check lockfile for agent initialization
            lockfile_path = Path.cwd() / "agently.lockfile.json"
            
            if not lockfile_path.exists():
                click.echo(f"{styles.yellow('Warning:')} Agent not initialized.")
                click.echo(f"Please run '{styles.bold('agently init')}' first to ensure all dependencies are available.")
                click.echo(f"Or use '{styles.bold('agently run --force')}' to skip this check.")
                sys.exit(1)
                
            try:
                with open(lockfile_path, "r") as f:
                    lockfile = json.load(f)
                    
                agent_initialized = False
                agent_id_to_check = config.id  # Get the ID from the loaded config
                
                # Check if agent exists in the lockfile
                if "agents" in lockfile and agent_id_to_check in lockfile["agents"]:
                    agent_data = lockfile["agents"][agent_id_to_check]
                    # Check if the agent has plugins
                    if agent_data.get("plugins"):
                        agent_initialized = True
                
                if not agent_initialized:
                    click.echo(f"{styles.yellow('Warning:')} Agent '{config.name}' ({agent_id_to_check}) is not initialized.")
                    if agent_id:
                        click.echo(f"Please run '{styles.bold(f'agently init {agent_id}')}' first to ensure all dependencies are available.")
                    else:
                        click.echo(f"Please run '{styles.bold('agently init')}' first to ensure all dependencies are available.")
                    click.echo(f"Or use '{styles.bold('agently run --force')}' to skip this check.")
                    sys.exit(1)
            except (json.JSONDecodeError, IOError):
                click.echo(f"{styles.yellow('Warning:')} Could not verify agent initialization status.")
                click.echo(f"Please run '{styles.bold('agently init')}' to ensure all dependencies are available.")
                click.echo(f"Or use '{styles.bold('agently run --force')}' to skip this check.")
                sys.exit(1)

        click.echo(f"Running agent: {config.name}")

        # Run interactive loop
        interactive_loop(config)

    except KeyboardInterrupt:
        click.echo("\nExiting...")
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        logger.exception("Error running agent")
        sys.exit(1)


@cli.group(help="List resources")
def list():
    """List resources like agents and plugins."""
    pass


@list.command(name="agents", help="List configured agents")
@click.argument("agent_id", required=False)
@click.option(
    "--file", "-f",
    help="Path to agent configuration file",
)
def list_agents(agent_id, file):
    """List all agents or detailed info for a specific agent."""
    try:
        # Find configuration file
        config_file = find_config_file(file)
        if not config_file:
            click.echo("Error: No configuration file found")
            sys.exit(1)

        # Get all agents from config
        agents = get_all_agents(config_file)

        if not agent_id:
            # Summary view of all agents
            click.echo(f"Configured agents ({len(agents)}):")
            click.echo("-" * 60)
            for agent in agents:
                click.echo(f"🤖 {agent['name']} ({agent['id']})")
                if agent.get('description'):
                    click.echo(f"  Description: {agent['description']}")
                click.echo(f"  Model: {agent['model']['provider']} {agent['model']['model']}")
                plugin_count = len(agent.get('plugins', {}).get('local', [])) + len(agent.get('plugins', {}).get('github', []))
                if plugin_count:
                    click.echo(f"  Plugins: {plugin_count}")
                click.echo("-" * 60)
        else:
            # Detailed view of specific agent
            agent = next((a for a in agents if a['id'] == agent_id), None)
            if not agent:
                click.echo(f"Error: Agent with ID '{agent_id}' not found")
                sys.exit(1)
                
            click.echo(f"Agent: {agent['name']} ({agent['id']})")
            click.echo("=" * 60)
            if agent.get('description'):
                click.echo(f"Description: {agent['description']}")
            click.echo(f"Model: {agent['model']['provider']} {agent['model']['model']}")
            
            # Display system prompt snippet
            if agent.get('system_prompt'):
                prompt = agent['system_prompt']
                click.echo(f"System prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
                
            # Display plugins
            local_plugins = agent.get('plugins', {}).get('local', [])
            github_plugins = agent.get('plugins', {}).get('github', [])
            
            if local_plugins or github_plugins:
                click.echo("\nPlugins:")
                click.echo("-" * 60)
                
                for plugin in local_plugins:
                    click.echo(f"📦 Local: {plugin['source']}")
                    if plugin.get('type') == 'mcp':
                        click.echo(f"  Type: MCP")
                    
                for plugin in github_plugins:
                    click.echo(f"📦 GitHub: {plugin['source']} ({plugin['version']})")
                    if plugin.get('type') == 'mcp':
                        click.echo(f"  Type: MCP")

    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error listing agents: {e}")
        sys.exit(1)


@cli.command()
def version():
    """Display the version of Agently."""
    click.echo(f"Agently version {__version__}")


def _initialize_plugins(config_path, quiet=False, force=False, agent_id=None):
    """Initialize plugins and MCP servers based on a configuration file.

    Args:
        config_path: Path to the agent configuration file
        quiet: Whether to reduce output verbosity
        force: Force reinstallation of all plugins and MCP servers
        agent_id: Optional ID of specific agent to initialize

    Returns:
        Dict with plugin statistics

    Raises:
        FileNotFoundError: If the configuration file does not exist
    """
    # Load the agent configuration
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    if force and not quiet:
        click.echo("Force mode enabled: reinstalling all plugins")

    # Parse YAML configuration to extract plugins
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")

    # Determine lockfile path (at the same level as .agently folder)
    lockfile_path = Path.cwd() / "agently.lockfile.json"

    # Create empty lockfile if it doesn't exist or load existing one
    if not lockfile_path.exists():
        logger.info("Creating new lockfile")
        lockfile = {
            "agents": {},
            "plugins": {"sk": {}, "mcp": {}}  # Keep the shared plugins section for backward compatibility
        }
    else:
        # Load existing lockfile
        with open(lockfile_path, "r") as f:
            try:
                lockfile = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid lockfile, creating new one")
                lockfile = {
                    "agents": {},
                    "plugins": {"sk": {}, "mcp": {}}
                }

        # Ensure lockfile has correct structure
        if "agents" not in lockfile:
            lockfile["agents"] = {}
        if "plugins" not in lockfile:
            lockfile["plugins"] = {"sk": {}, "mcp": {}}
        elif "sk" not in lockfile["plugins"]:
            lockfile["plugins"]["sk"] = {}
        elif "mcp" not in lockfile["plugins"]:
            lockfile["plugins"]["mcp"] = {}

    # Check if we have a multi-agent or single-agent config
    if "agents" in config and config["agents"]:
        # Multi-agent configuration
        agents_to_process = []
        
        if agent_id:
            # Find specific agent
            agent = next((a for a in config["agents"] if a.get("id") == agent_id), None)
            if not agent:
                raise ValueError(f"Agent with ID '{agent_id}' not found in configuration")
            
            agents_to_process.append(agent)
            if not quiet:
                click.echo(f"Initializing plugins for agent: {agent.get('name')} ({agent_id})")
        else:
            # Initialize all agents
            agents_to_process = config["agents"]
            if not quiet:
                click.echo(f"Initializing plugins for {len(agents_to_process)} agents")
    else:
        # Single-agent configuration - treat as one agent
        if not quiet:
            click.echo(f"Initializing plugins for agent: {config.get('name', 'default')}")
        agents_to_process = [config]

    # Stats counters
    stats = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "removed": 0,
        "failed": 0,
    }

    # Process each agent
    for agent in agents_to_process:
        agent_id = agent.get("id", f"agent-{uuid4().hex[:8]}")
        agent_name = agent.get("name", "default")
        
        if not quiet:
            click.echo(f"\nProcessing agent: {agent_name} ({agent_id})")
        
        # Ensure agent exists in lockfile
        if agent_id not in lockfile["agents"]:
            lockfile["agents"][agent_id] = {
                "name": agent_name,
                "plugins": {"sk": {}, "mcp": {}}
            }
        
        # Get plugins for this agent
        plugins_config = agent.get("plugins", {})
        
        # Process local plugins
        local_plugins = plugins_config.get("local", [])
        github_plugins = plugins_config.get("github", [])
        
        # Display plugin statuses in Terraform-like format
        total_plugins = len(local_plugins) + len(github_plugins)
        
        if not quiet and total_plugins > 0:
            click.echo(f"Found {total_plugins} plugins for agent {agent_name}")
        
        # Track which plugins are installed and which to remove
        installed_plugins = {"sk": set(), "mcp": set()}
        to_add = {"sk": set(), "mcp": set()}
        to_update = {"sk": set(), "mcp": set()}
        unchanged = {"sk": set(), "mcp": set()}
        failed = {"sk": set(), "mcp": set()}
        
        # Process local plugins
        for local_plugin_config in local_plugins:
            source_path = local_plugin_config["source"]
            plugin_type = local_plugin_config.get("type", "sk")  # Default to "sk" if not specified
            
            abs_source_path = config_path.parent / source_path if not os.path.isabs(source_path) else Path(source_path)
            
            # Use the same naming approach as during detection
            plugin_name = os.path.basename(source_path)
            local_source = LocalPluginSource(
                path=abs_source_path,
                namespace="local",
                name=plugin_name,
                force_reinstall=force,
                plugin_type=plugin_type
            )
            
            plugin_key = f"{local_source.namespace}/{local_source.name}"
            
            # Determine if plugin needs to be added/updated
            agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
            if plugin_key in agent_plugin_section:
                # Check if update needed
                lockfile_sha = agent_plugin_section[plugin_key].get("sha", "")
                if force or local_source.needs_update(lockfile_sha):
                    to_update[plugin_type].add(plugin_key)
                    if not quiet:
                        click.echo(f"- Updating {plugin_key} from local path...")
                else:
                    unchanged[plugin_type].add(plugin_key)
                    if not quiet:
                        click.echo(f"- {plugin_key} is up to date")
            else:
                to_add[plugin_type].add(plugin_key)
                if not quiet:
                    click.echo(f"- Installing {plugin_key}...")
            
            try:
                # Load plugin
                plugin_class = local_source.load()
                
                # Get plugin info for lockfile
                plugin_info = local_source._get_plugin_info(plugin_class)
                
                # Add variables from config if present
                if "variables" in local_plugin_config:
                    plugin_info["variables"] = local_plugin_config["variables"]
                
                # Add to installed plugins
                installed_plugins[plugin_type].add(plugin_key)
                
                # Update lockfile with plugin info
                lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                # Also update shared plugins (backward compatibility)
                lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                
                if plugin_key in to_add[plugin_type]:
                    stats["added"] += 1
                elif plugin_key in to_update[plugin_type]:
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
                
            except Exception as e:
                logger.error(f"Failed to install local plugin {source_path}: {e}")
                failed[plugin_type].add(plugin_key)
                stats["failed"] += 1
                if not quiet:
                    click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
        
        # Process GitHub plugins
        for github_plugin_config in github_plugins:
            repo_url = github_plugin_config["source"]
            version = github_plugin_config.get("version", "main")
            plugin_type = github_plugin_config.get("type", "sk")  # Default to "sk" if not specified
            
            # Create a GitHubPluginSource
            source = GitHubPluginSource(
                repo_url=repo_url,
                plugin_path=github_plugin_config.get("plugin_path", ""),
                namespace="",  # Will be extracted from repo_url
                name="",  # Will be extracted from repo_url
                version=version,
                force_reinstall=False,
                plugin_type=plugin_type
            )
            
            plugin_key = f"{source.namespace}/{source.name}"
            
            # Determine if plugin needs to be added/updated
            agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
            if plugin_key in agent_plugin_section:
                # Check if update needed
                lockfile_sha = agent_plugin_section[plugin_key].get("sha", "")
                if force or source.needs_update(lockfile_sha):
                    to_update[plugin_type].add(plugin_key)
                    if not quiet:
                        click.echo(f"- Updating {plugin_key} to {version}...")
                else:
                    unchanged[plugin_type].add(plugin_key)
                    if not quiet:
                        click.echo(f"- {plugin_key} is up to date")
            else:
                to_add[plugin_type].add(plugin_key)
                if not quiet:
                    click.echo(f"- Installing {plugin_key} {version}...")
            
            try:
                # Load plugin
                plugin_class = source.load()
                
                # Get plugin info for lockfile
                plugin_info = source._get_plugin_info(plugin_class)
                
                # Add variables from config if present
                if "variables" in github_plugin_config:
                    plugin_info["variables"] = github_plugin_config["variables"]
                
                # Add to installed plugins
                installed_plugins[plugin_type].add(plugin_key)
                
                # Update lockfile with plugin info
                lockfile["agents"][agent_id]["plugins"][plugin_type][plugin_key] = plugin_info
                # Also update shared plugins (backward compatibility)
                lockfile["plugins"][plugin_type][plugin_key] = plugin_info
                
                if plugin_key in to_add[plugin_type]:
                    stats["added"] += 1
                elif plugin_key in to_update[plugin_type]:
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
                
            except Exception as e:
                logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
                failed[plugin_type].add(plugin_key)
                stats["failed"] += 1
                if not quiet:
                    click.echo(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
        
        # Remove plugins that are no longer in the config for this agent
        for plugin_type in ["sk", "mcp"]:
            agent_plugin_section = lockfile["agents"][agent_id]["plugins"][plugin_type]
            current_plugins = set(agent_plugin_section.keys())
            config_plugins = installed_plugins[plugin_type]
            
            for plugin_key in current_plugins - config_plugins:
                agent_plugin_section.pop(plugin_key, None)
                if not quiet:
                    click.echo(f"- Removing {plugin_key}...")
                stats["removed"] += 1
    
    # Write updated lockfile
    with open(lockfile_path, "w") as f:
        json.dump(lockfile, f, indent=2)
    
    # Display summary
    if not quiet:
        click.echo("\nAgent initialization summary:")
        click.echo(format_apply_summary(
            stats["added"],
            stats["updated"],
            stats["unchanged"],
            stats["removed"],
            stats["failed"]
        ))
    
    return stats


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
