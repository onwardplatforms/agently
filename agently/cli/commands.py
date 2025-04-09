"""Command line interface for the agent runtime."""

import json
import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import click
import yaml
from agently_sdk import styles  # Import styles directly from SDK

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource
from agently.utils.logging import LogLevel, configure_logging

from .interactive import interactive_loop

logger = logging.getLogger(__name__)


# Define plugin status enum directly here
class PluginStatus(Enum):
    """Status of a plugin during initialization."""

    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"


# Define the formatters directly here using SDK styles
def format_plugin_status(status: PluginStatus, plugin_key: str, details: Optional[str] = None) -> str:
    """Format a plugin status message."""
    icon = {
        PluginStatus.ADDED: styles.green("+ "),
        PluginStatus.UPDATED: styles.yellow("~ "),
        PluginStatus.UNCHANGED: styles.dim("- "),
        PluginStatus.REMOVED: styles.red("- "),
        PluginStatus.FAILED: styles.red("✗ "),
    }[status]

    status_text = {
        PluginStatus.ADDED: "(new)",
        PluginStatus.UPDATED: "(updated)",
        PluginStatus.UNCHANGED: "(unchanged)",
        PluginStatus.REMOVED: "(removed)",
        PluginStatus.FAILED: "(failed)",
    }[status]

    text = f"{icon}{plugin_key} {styles.dim(status_text)}"
    if details:
        text += f" {styles.dim(details)}"
    return text


def format_section_header(title: str) -> str:
    """Format a section header."""
    return styles.bold(title) + ":"


def format_plan_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format a plugin status summary."""
    total = added + updated + unchanged + removed

    if added == 0 and updated == 0 and removed == 0 and failed == 0 and unchanged > 0:
        return f"All plugins ({unchanged}) are ready and up-to-date"

    parts = []

    if added > 0:
        parts.append(styles.green(f"+{added} new"))
    if updated > 0:
        parts.append(styles.yellow(f"~{updated} updated"))
    if unchanged > 0:
        parts.append(styles.dim(f"-{unchanged} unchanged"))
    if removed > 0:
        parts.append(styles.red(f"-{removed} removed"))
    if failed > 0:
        parts.append(styles.red(f"✗{failed} failed"))

    return f"Found {total} plugins: " + ", ".join(parts)


def format_apply_summary(added: int, updated: int, unchanged: int, removed: int, failed: int = 0) -> str:
    """Format a validation result summary."""
    total = added + updated + unchanged + removed

    # Special case for all plugins up-to-date
    if added == 0 and updated == 0 and removed == 0 and failed == 0 and unchanged > 0:
        return f"All plugins ({unchanged}) are ready and up-to-date"

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

    return f"Validation complete: {total} plugins processed" + (", " + ", ".join(parts) if parts else "")


@click.group()
def cli():
    """agently.run - Declarative AI agents without code."""


@cli.command()
@click.option("--agent", "-a", default="agently.yaml", help="Path to agent configuration file")
@click.option(
    "--log-level",
    type=click.Choice(["none", "debug", "info", "warning", "error", "critical"], case_sensitive=False),
    help="Override the log level",
)
@click.option(
    "--continuous-reasoning",
    is_flag=True,
    help="Enable continuous reasoning mode to show agent's step-by-step thought process",
)
def run(agent, log_level, continuous_reasoning):
    """Run an agent with the specified configuration."""
    try:
        # Override log level if specified
        if log_level:
            # Convert string to LogLevel enum value
            log_level_value = getattr(LogLevel, log_level.upper())
            configure_logging(level=log_level_value)
        else:
            configure_logging(level=LogLevel.WARNING)

        # Load agent configuration
        logger.info(f"Loading agent configuration from {agent}")
        config = load_agent_config(agent)

        # Override continuous reasoning if specified
        if continuous_reasoning:
            config.continuous_reasoning = True
            logger.info("Continuous reasoning mode enabled")

        # Initialize the agent
        from agently.agents.agent import Agent

        click.echo(f"Initializing agent: {config.name}")
        agent_instance = Agent(config)
        # Initial setup for the agent is done, now we'll run it

        # Set up the event loop to run the agent
        async def init_and_run():
            # Initialize the agent asynchronously
            await agent_instance.initialize()
            click.echo("Agent initialized successfully")

            # Create a conversation context
            from agently.conversation.context import ConversationContext

            context = ConversationContext(conversation_id=f"cli-{config.id}")
            
            # Run the appropriate interactive loop based on continuous reasoning setting
            if config.continuous_reasoning:
                click.echo("Running in continuous reasoning mode")
                click.echo("The agent will show its step-by-step thought process\n")
                # We don't await this function because it contains its own event loop
                # for handling the interactive session
                return context, agent_instance
            else:
                click.echo("Running in standard mode\n")
                interactive_loop(config, context)
                return None, None

        # Run the initialization and interactive loop
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            context, agent = loop.run_until_complete(init_and_run())
            
            # If we're using continuous reasoning, run its interactive loop separately
            if context and agent:
                interactive_loop_with_reasoning(agent, config, context)
        except KeyboardInterrupt:
            click.echo("\nExiting...")
            
    except Exception as e:
        logger.exception(f"Error: {e}")
        click.echo(f"Error: {e}")


@cli.command()
def list():
    """List installed plugins."""
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

        plugins = lockfile.get("plugins", {})

        if not plugins:
            click.echo("No plugins installed")
            return

        # Display installed plugins
        click.echo(f"Installed plugins ({len(plugins)}):")
        click.echo("-" * 60)

        for plugin_key, plugin_info in plugins.items():
            click.echo(f"📦 {plugin_key}")
            click.echo(f"  Version: {plugin_info['version']}")
            click.echo(f"  Commit: {plugin_info['commit_sha'][:8] if plugin_info.get('commit_sha') else 'unknown'}")
            click.echo(f"  Installed: {plugin_info.get('installed_at', 'unknown')}")
            click.echo(f"  Source: {plugin_info.get('repo_url', 'unknown')}")
            click.echo("-" * 60)

    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error listing plugins: {e}")
        sys.exit(1)


def _initialize_plugins(config_path, quiet=False, force=False):
    """Initialize plugins based on a configuration file.

    Args:
        config_path: Path to the agent configuration file
        quiet: Whether to reduce output verbosity
        force: Force reinstallation of all plugins

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
        click.echo("Force mode enabled: reinstalling all plugins")

    if not quiet:
        click.echo("Scanning plugin dependencies...")

    # Parse YAML configuration to extract plugins
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")

    # Get plugin configurations
    plugins_config = config.get("plugins", {})

    # Determine lockfile path (at the same level as .agently folder)
    lockfile_path = Path.cwd() / "agently.lockfile.json"

    # Read existing lockfile
    try:
        if lockfile_path.exists():
            with open(lockfile_path, "r") as f:
                try:
                    lockfile = json.load(f)
                except json.JSONDecodeError:
                    # Invalid lockfile, create a new one
                    if not quiet:
                        click.echo("Invalid lockfile, creating a new one")
                    lockfile = {"plugins": {}}
        else:
            if not quiet:
                click.echo("Creating new lockfile")
            lockfile = {"plugins": {}}
    except Exception:
        # Failed to read lockfile, create a new one
        lockfile = {"plugins": {}}

    # Process the plugin configuration
    github_plugins = []
    local_plugins = []

    # Extract configured plugins
    if "github" in plugins_config:
        github_plugins = plugins_config["github"]

    if "local" in plugins_config:
        local_plugins = plugins_config["local"]

    # Gather plugin details for consistent formatting
    plugin_details = {}

    # Determine which plugins to add, update, and remove
    to_add = set()
    to_update = set()
    unchanged = set()
    to_remove = set()

    # Track successfully installed plugins
    installed_plugins = set()
    failed = set()

    # Process GitHub plugins
    for github_plugin_config in github_plugins:
        repo_url = github_plugin_config["source"]
        version = github_plugin_config.get("version", "main")
        plugin_path = github_plugin_config.get("plugin_path", "")

        # Create a GitHubPluginSource
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=plugin_path,
            force_reinstall=False,  # We'll handle force flag separately
        )

        plugin_key = f"{source.namespace}/{source.name}"
        plugin_details[plugin_key] = f"version={version}"

        if plugin_key in lockfile.get("plugins", {}):
            # Plugin exists in lockfile, check if it needs updating
            lockfile_sha = lockfile["plugins"][plugin_key].get("commit_sha", "")
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

        if plugin_key in lockfile.get("plugins", {}):
            # Plugin exists in lockfile, check if it needs updating
            lockfile_sha = lockfile["plugins"][plugin_key].get("sha256", "")
            if force or local_source.needs_update(lockfile_sha):
                to_update.add(plugin_key)
            else:
                unchanged.add(plugin_key)
        else:
            # New plugin
            to_add.add(plugin_key)

    # Find plugins in lockfile that aren't in the config
    lockfile_plugins = set(lockfile.get("plugins", {}).keys())
    config_plugins = set()
    for plugin_key in to_add | to_update | unchanged:
        config_plugins.add(plugin_key)

    # Plugins to remove are those in the lockfile but not in the config
    for plugin_key in lockfile_plugins - config_plugins:
        to_remove.add(plugin_key)

    # Print plan
    if not quiet:
        click.echo("\nPlugin status:")

        if to_add or to_update or to_remove:
            all_plugins = sorted(to_add) + sorted(to_update) + sorted(unchanged) + sorted(to_remove)
            for plugin_key in all_plugins:
                status = None
                if plugin_key in to_add:
                    status = PluginStatus.ADDED
                elif plugin_key in to_update:
                    status = PluginStatus.UPDATED
                elif plugin_key in unchanged:
                    status = PluginStatus.UNCHANGED
                elif plugin_key in to_remove:
                    status = PluginStatus.REMOVED

                if status:
                    click.echo(format_plugin_status(status, plugin_key, plugin_details.get(plugin_key)))

            click.echo(f"\n{format_plan_summary(len(to_add), len(to_update), len(unchanged), len(to_remove))}")
        else:
            click.echo("All plugins are ready and up-to-date")

    # Now perform the actual installation

    # Install GitHub plugins
    for github_plugin_config in github_plugins:
        repo_url = github_plugin_config["source"]
        version = github_plugin_config.get("version", "main")
        plugin_path = github_plugin_config.get("plugin_path", "")

        # Create a GitHubPluginSource
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=plugin_path,
            force_reinstall=force,  # Pass the force flag to control reinstallation
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
            lockfile["plugins"][plugin_key] = plugin_info

            # Plugins are loaded silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e)))

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
            lockfile["plugins"][plugin_key] = plugin_info

            # Plugins are loaded silently since the status is already shown
        except Exception as e:
            logger.error(f"Failed to install local plugin {source_path}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e)))

    # Remove plugins that are no longer in the config
    for plugin_key in to_remove:
        # Plugins are removed silently since the status is already shown
        lockfile["plugins"].pop(plugin_key, None)

    # Write updated lockfile
    with open(lockfile_path, "w") as f:
        json.dump(lockfile, f, indent=2)

    # Print summary
    if not quiet:
        # Count actual changes
        added = len([p for p in to_add if p in installed_plugins and p not in failed])
        updated = len([p for p in to_update if p in installed_plugins and p not in failed])
        removed = len(to_remove)
        failed_count = len(failed)
        unchanged_count = len([p for p in unchanged if p in installed_plugins])

        click.echo(f"\n{format_apply_summary(added, updated, unchanged_count, removed, failed_count)}")

    return installed_plugins


@cli.command()
@click.option("--agent", "-a", default="agently.yaml", help="Path to agent configuration file")
@click.option("--force", is_flag=True, help="Force reinstallation of all plugins")
@click.option("--quiet", is_flag=True, help="Reduce output verbosity")
@click.option(
    "--log-level",
    type=click.Choice(["none", "debug", "info", "warning", "error", "critical"], case_sensitive=False),
    help="Override the log level",
)
def init(agent, force, quiet, log_level):
    """Initialize plugins based on your configuration file.

    This command must be run before 'agently run' to ensure all required plugins are installed.
    """
    try:
        # Set up logging
        if log_level:
            level = getattr(LogLevel, log_level.upper())
            configure_logging(level=level)
            logger.debug(f"Log level set to {log_level.upper()}")
        elif not quiet:
            configure_logging(level=LogLevel.INFO)
        else:
            configure_logging(level=LogLevel.WARNING)

        if not quiet:
            click.echo(f"Reading configuration from {agent}")

        _initialize_plugins(agent, quiet=quiet, force=force)

        if not quiet:
            click.echo("\nValidation complete!")
            click.echo("\nAgently is ready to run")
    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error initializing plugins: {e}")
        sys.exit(1)


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
