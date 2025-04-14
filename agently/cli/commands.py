"""Command line interface for the Agently framework.

This module defines the CLI commands and subcommands using Click.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
import yaml

from agently.utils.logging import LogLevel, configure_logging
from agently.version import __version__

# Create a logger for this module
logger = logging.getLogger(__name__)

# Import our new modules
from agently.cli import config, formatting, lockfile, plugin_manager
from agently.cli.interactive import interactive_loop


@click.group()
def cli():
    """agently.run - Declarative AI agents without code."""
    # Default to no logging unless explicitly requested
    configure_logging(level=LogLevel.NONE)


# ------------------------------------------------------------------------------
# INITIALIZE COMMAND
# ------------------------------------------------------------------------------


@cli.command(help="Initialize agent and dependencies")
@click.argument("agent_id", required=False)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], case_sensitive=False),
    help="Set the logging level. Overrides the LOG_LEVEL environment variable.",
)
@click.option(
    "--file",
    "-f",
    help="Path to agent configuration file",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force reinstallation of all plugins",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Reduce output verbosity",
)
def init(agent_id=None, log_level=None, file=None, force=False, quiet=False):
    """Initialize agents and dependencies."""
    # Configure logging if specified via CLI
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
    else:
        configure_logging(level=LogLevel.NONE)

    try:
        # Find and validate the configuration file
        config_file = config.find_config_file(file)
        if not config_file:
            click.echo(formatting.format_error("No configuration file found"))
            sys.exit(1)

        click.echo("Initializing agently...")
        click.echo()

        # Load the configuration
        try:
            cfg = config.load_config(config_file)
        except Exception as e:
            click.echo(formatting.format_error(f"Failed to load configuration: {str(e)}"))
            sys.exit(1)

        # Get all agent IDs from the config
        agent_ids = []
        if "agents" in cfg:
            agents_list = cfg["agents"]
            if type(agents_list).__name__ == "list":
                for idx, agent in enumerate(agents_list):
                    if type(agent).__name__ == "dict":
                        agent_id_val = agent.get("id") or f"agent{idx+1}"
                        agent_ids.append(agent_id_val)

        agent_count = len(agent_ids)
        click.echo(formatting.format_success(f"  {agent_count} agents detected"))

        # Validate the configuration
        is_valid, errors = _validate_config_with_schema(cfg, Path(__file__).parent.parent / "config" / "schema.json")
        if not is_valid:
            click.echo(formatting.format_error("Configuration validation failed:"))
            _display_validation_errors(errors, config_file)
            sys.exit(1)

        click.echo(formatting.format_success("  configuration valid"))
        click.echo()

        # Load the lockfile
        lock_data = lockfile.load_lockfile()

        # Clean up agents that are no longer in the config
        config_agent_ids = set(agent_ids)  # Convert to set for efficient membership testing
        lockfile.cleanup_agents(lock_data, config_agent_ids, quiet)

        click.echo("Setting up agents...")

        # Get initial state of plugins in the lockfile
        old_lock_data = {}
        if "agents" in lock_data:
            for agent_id_key, agent_data in lock_data.get("agents", {}).items():
                if "plugins" in agent_data:
                    old_lock_data[agent_id_key] = {
                        "plugins": [p.copy() if isinstance(p, dict) else p for p in agent_data.get("plugins", [])]
                    }

        # Run the plugin initialization with quiet=True to suppress built-in output
        stats = plugin_manager.sync_plugins(config_file, cfg, lock_data, agent_id, True, force)

        # Save the updated lockfile
        lockfile.save_lockfile(lock_data)

        # Display agent info with plugin status
        for idx, agent_config in enumerate(cfg.get("agents", [])):
            if type(agent_config).__name__ != "dict":
                continue

            current_agent_id = agent_config.get("id") or f"agent{idx+1}"
            agent_name = agent_config.get("name", f"Agent {idx+1}")
            agent_desc = agent_config.get("description", "")

            # Show a summary of the agent (truncate description if too long)
            desc_preview = agent_desc[:50] + "..." if len(agent_desc) > 50 else agent_desc
            click.echo(f"{agent_name} ({current_agent_id}): {desc_preview}")

            # Display plugin information for this agent with status
            old_agent_data = old_lock_data.get(current_agent_id, {})
            _display_agent_plugins(cfg, current_agent_id, lock_data, old_agent_data)

        # Show success message
        click.echo()
        click.echo(formatting.format_success("Agently has been successfully initialized!"))
        click.echo()

        if agent_id:
            click.echo(f"You can now run the agent with: agently run {agent_id}")
        else:
            click.echo("You can now run Agently with: agently run")

        # Don't exit with error code for plugin failures
        # We've already shown failed plugins in the output

    except Exception as e:
        click.echo(formatting.format_error(f"Initialization error: {str(e)}"))
        logger.exception("Error during initialization")
        sys.exit(1)


def _display_agent_plugins(cfg, agent_id, lock_data, old_agent_data=None):
    """Display information about plugins for an agent.

    Args:
        cfg: Configuration object
        agent_id: ID of the agent
        lock_data: The lockfile data
        old_agent_data: Previous state of the agent in the lockfile
    """
    # Find the agent in the config
    agent_config = None
    for idx, agent in enumerate(cfg.get("agents", [])):
        if type(agent).__name__ != "dict":
            continue

        current_id = agent.get("id") or f"agent{idx+1}"
        if current_id == agent_id:
            agent_config = agent
            break

    if not agent_config:
        return

    # Process plugins for this agent
    plugins = agent_config.get("plugins", [])
    if not plugins:
        click.echo("  no plugins configured")
        return

    # Get the agent from lockfile
    agent_lock_data = None
    if "agents" in lock_data and agent_id in lock_data["agents"]:
        agent_lock_data = lock_data["agents"][agent_id]

    # Get old plugin data
    old_plugins = []
    if old_agent_data and "plugins" in old_agent_data:
        old_plugins = old_agent_data.get("plugins", [])

    for plugin_config in plugins:
        if type(plugin_config).__name__ != "dict":
            continue

        # Get plugin details
        plugin_type = plugin_config.get("type", "unknown")
        plugin_source = plugin_config.get("source", "unknown")

        # Get source-specific details
        plugin_location = ""
        if plugin_source == "local":
            plugin_path = plugin_config.get("path", "")
            if plugin_path:
                plugin_location = f"@ {plugin_path}"
        elif plugin_source == "github":
            plugin_url = plugin_config.get("url", "")
            if plugin_url:
                plugin_location = f"@ {plugin_url}"
                plugin_branch = plugin_config.get("branch")
                plugin_version = plugin_config.get("version")
                if plugin_branch:
                    plugin_location += f" ({plugin_branch})"
                elif plugin_version:
                    plugin_location += f" (v{plugin_version})"

        # Find matching plugin in current lockfile
        current_plugin = None
        if agent_lock_data and "plugins" in agent_lock_data:
            for p in agent_lock_data.get("plugins", []):
                # Match based on type, namespace/source, and path/url
                if (
                    p.get("plugin_type") == plugin_type
                    and _plugin_source_matches(p, plugin_source)
                    and _plugin_path_matches(p, plugin_config)
                ):
                    current_plugin = p
                    break

        # Find matching plugin in old lockfile
        old_plugin = None
        for p in old_plugins:
            # Match based on type, namespace/source, and path/url
            if (
                p.get("plugin_type") == plugin_type
                and _plugin_source_matches(p, plugin_source)
                and _plugin_path_matches(p, plugin_config)
            ):
                old_plugin = p
                break

        # Determine real plugin status
        status_text = "is up-to-date"
        status_style = formatting.styles.dim

        if not old_plugin and current_plugin:
            # Plugin wasn't in old lockfile but is in current: added
            status_text = "was added"
            status_style = formatting.styles.green
        elif old_plugin and current_plugin:
            # Plugin was in old lockfile and is in current: check if updated
            old_sha = old_plugin.get("sha", "")
            current_sha = current_plugin.get("sha", "")
            if old_sha != current_sha:
                status_text = "was updated"
                status_style = formatting.styles.yellow
        elif not current_plugin:
            # Plugin is in config but not in lockfile: failed
            status_text = "failed to initialize"
            status_style = formatting.styles.red

        # Display the plugin with status - ensure base text is plain, path is dimmed
        plugin_text = f"{plugin_source}/{plugin_type}"
        path_text = formatting.styles.dim(plugin_location)
        click.echo(f"  {plugin_text} {path_text} {status_style(status_text)}")


def _plugin_source_matches(lock_plugin, source):
    """Check if the plugin source in lockfile matches the source in config."""
    namespace = lock_plugin.get("namespace", "")
    source_type = lock_plugin.get("source_type", "")

    # Local plugin with namespace "local" matches source "local"
    if namespace == "local" and source == "local":
        return True

    # GitHub plugins can have different namespaces (user or org names)
    # but they all have source_type "github" in the lockfile
    if source_type == "github" and source == "github":
        return True

    return False


def _plugin_path_matches(lock_plugin, plugin_config):
    """Check if the plugin path in lockfile matches the one in config."""
    # For local plugins, compare the basename of the path
    if "path" in plugin_config:
        lock_name = lock_plugin.get("name", "")
        path = plugin_config["path"]
        return lock_name == os.path.basename(path)

    # For GitHub plugins, check if the URL matches
    if "url" in plugin_config:
        url = plugin_config["url"]
        repo_url = lock_plugin.get("repo_url", "")

        # Clean up the URLs for comparison
        clean_url = url.replace("github.com/", "").strip("/")
        clean_repo_url = repo_url.replace("github.com/", "").strip("/")

        # Compare the URLs directly (namespace/repo format)
        if clean_url == clean_repo_url:
            return True

        # If they don't match directly, check if the repo name matches
        # This handles the case where the URL format might differ but repo is the same
        lock_name = lock_plugin.get("name", "")
        url_parts = clean_url.split("/")
        if len(url_parts) > 1 and url_parts[-1] == lock_name:
            return True

    return False


# ------------------------------------------------------------------------------
# VALIDATE COMMAND
# ------------------------------------------------------------------------------


@cli.command(help="Validate agent configuration")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], case_sensitive=False),
    help="Set the logging level. Overrides the LOG_LEVEL environment variable.",
)
@click.option(
    "--file",
    "-f",
    help="Path to agent configuration file",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit with error code on validation failures",
)
def validate(log_level, file, strict=False):
    """Validate agent configuration without initializing."""
    # Configure logging if specified via CLI
    level = getattr(LogLevel, (log_level or "NONE").upper())
    configure_logging(level=level)

    has_errors = False
    try:
        # Find configuration file
        config_file = config.find_config_file(file)
        if not config_file:
            click.echo(formatting.format_error("No configuration file found"))
            sys.exit(1)

        click.echo(f"Validating configuration: {config_file}")
        click.echo()

        # Load the config first
        try:
            cfg = config.load_config(config_file)
            logger.debug(f"Loaded configuration: {cfg}")
        except Exception as e:
            click.echo(formatting.format_error(f"Failed to load configuration: {str(e)}"))
            sys.exit(1)

        # Try validating with json schema
        schema_path = Path(__file__).parent.parent / "config" / "schema.json"
        logger.debug(f"Schema path: {schema_path}")

        try:
            logger.debug("Validating with schema...")
            is_valid, errors = _validate_config_with_schema(cfg, schema_path)
            logger.debug(f"Validation result: valid={is_valid}, errors={errors}")

            if not is_valid:
                _display_validation_errors(errors, config_file)
                has_errors = True

            # Additional validation with our custom validator
            if not config.validate_config(cfg):
                if not has_errors:
                    click.echo(formatting.format_error("Configuration validation failed"))
                has_errors = True

            if not has_errors:
                # Success message for validation
                agent_count = ""
                if "agents" in cfg and cfg["agents"]:
                    num_agents = len(cfg["agents"])
                    agent_count = f" ({num_agents} agents defined)"

                click.echo(formatting.format_success(f"Success! The configuration is valid{agent_count}."))
            elif not strict:
                # Don't show warning or info - just continue without exit code
                pass
            else:
                # In strict mode, exit with error code
                sys.exit(1)

        except Exception as e:
            logger.exception("Error during schema validation")
            click.echo(formatting.format_error(f"Validation error: {str(e)}"))
            sys.exit(1)

    except Exception as e:
        logger.exception("Error during validation")
        click.echo(formatting.format_error(str(e)))
        sys.exit(1)

    # Only exit with error in strict mode
    if has_errors and strict:
        sys.exit(1)


# ------------------------------------------------------------------------------
# RUN COMMAND
# ------------------------------------------------------------------------------


@cli.command(help="Run agent in REPL mode")
@click.argument("agent_id", required=False)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NONE"], case_sensitive=False),
    help="Set the logging level. Overrides the LOG_LEVEL environment variable.",
)
@click.option(
    "--file",
    "-f",
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
        config_file = config.find_config_file(file)
        if not config_file:
            click.echo(formatting.format_error("No configuration file found"))
            sys.exit(1)

        # Load specific agent or first agent
        agent_config = config.load_agent_config(config_file, agent_id)

        # Verify agent is initialized unless --force is used
        if not force:
            lock = lockfile.load_lockfile()

            if not lockfile.get_lockfile_path().exists():
                click.echo(formatting.format_warning("Agent not initialized."))
                click.echo(
                    f"Please run '{click.style('agently init', bold=True)}' first to ensure all dependencies are available."
                )
                click.echo(f"Or use '{click.style('agently run --force', bold=True)}' to skip this check.")
                sys.exit(1)

            agent_initialized = False
            agent_id_to_check = agent_config.id  # ID from the loaded config

            # Check if agent exists in the lockfile
            agent_data = lockfile.get_agent_from_lockfile(lock, agent_id_to_check)
            if agent_data and "plugins" in agent_data and agent_data["plugins"]:
                agent_initialized = True

            if not agent_initialized:
                click.echo(
                    formatting.format_warning(f"Agent '{agent_config.name}' ({agent_id_to_check}) is not initialized.")
                )
                if agent_id:
                    click.echo(f"Please run '{click.style(f'agently init {agent_id}', bold=True)}' first.")
                else:
                    click.echo(f"Please run '{click.style('agently init', bold=True)}' first.")
                click.echo(f"Or use '{click.style('agently run --force', bold=True)}' to skip this check.")
                sys.exit(1)

        click.echo(f"Running agent: {agent_config.name}")

        # Run interactive loop
        interactive_loop(agent_config)

    except KeyboardInterrupt:
        click.echo("\nExiting...")
    except Exception as e:
        click.echo(formatting.format_error(str(e)))
        logger.exception("Error running agent")
        sys.exit(1)


# ------------------------------------------------------------------------------
# LIST COMMAND GROUP
# ------------------------------------------------------------------------------


@cli.group(help="List resources")
def list():
    """List resources like agents and plugins."""
    pass


@list.command(name="agents", help="List configured agents")
@click.argument("agent_id", required=False)
@click.option(
    "--file",
    "-f",
    help="Path to agent configuration file",
)
def list_agents(agent_id, file):
    """List all agents or detailed info for a specific agent."""
    try:
        # Find configuration file
        config_file = config.find_config_file(file)
        if not config_file:
            click.echo(formatting.format_error("No configuration file found"))
            sys.exit(1)

        # Get all agents from config
        agents = config.get_all_agents(config_file)

        if not agent_id:
            # Summary view of all agents
            click.echo(f"Configured agents ({len(agents)}):")
            click.echo("-" * 60)
            for agent in agents:
                click.echo(f"🤖 {agent['name']} ({agent['id']})")
                if agent.get("description"):
                    click.echo(f"  Description: {agent['description']}")
                click.echo(f"  Model: {agent['model']['provider']} {agent['model']['model']}")
                # Count plugins in the flat array
                plugin_count = len(agent.get("plugins", []))
                if plugin_count:
                    click.echo(f"  Plugins: {plugin_count}")
                click.echo("-" * 60)
        else:
            # Detailed view of specific agent
            agent = next((a for a in agents if a["id"] == agent_id), None)
            if not agent:
                click.echo(formatting.format_error(f"Agent with ID '{agent_id}' not found"))
                sys.exit(1)

            click.echo(f"Agent: {agent['name']} ({agent['id']})")
            click.echo("=" * 60)
            if agent.get("description"):
                click.echo(f"Description: {agent['description']}")
            click.echo(f"Model: {agent['model']['provider']} {agent['model']['model']}")

            # Display system prompt snippet if present
            if agent.get("system_prompt"):
                prompt = agent["system_prompt"]
                click.echo(f"System prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

            # Display features if present
            if agent.get("features"):
                click.echo("\nFeatures:")
                features = agent["features"]
                if features.get("deep_reasoning"):
                    click.echo(f"  Deep reasoning: {features['deep_reasoning']}")

            # Display plugins using the flat array structure
            plugins = agent.get("plugins", [])

            if plugins:
                click.echo("\nPlugins:")
                click.echo("-" * 60)

                for plugin in plugins:
                    source_type = plugin["source"]
                    plugin_type = plugin["type"]

                    if source_type == "local":
                        click.echo(f"📦 Local: {plugin['path']} ({plugin_type.upper()})")
                    elif source_type == "github":
                        version = plugin.get("version", plugin.get("branch", "main"))
                        click.echo(f"📦 GitHub: {plugin['url']} ({version}) ({plugin_type.upper()})")

    except Exception as e:
        click.echo(formatting.format_error(str(e)))
        logger.exception(f"Error listing agents: {e}")
        sys.exit(1)


# ------------------------------------------------------------------------------
# VERSION COMMAND
# ------------------------------------------------------------------------------


@cli.command()
def version():
    """Display the version of Agently."""
    click.echo(f"Agently version {__version__}")


def _validate_config_with_schema(cfg, schema_path):
    """Validate configuration with JSON schema and return all errors found.

    Args:
        cfg: Configuration to validate
        schema_path: Path to the schema file

    Returns:
        Tuple of (is_valid, errors), where errors is a list of error dictionaries with helpful messages
    """
    try:
        import jsonschema
        from jsonschema import validators

        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Create a validator
        validator_cls = validators.validator_for(schema)
        validator = validator_cls(schema)

        # Collect all errors
        all_errors = []
        for error in validator.iter_errors(cfg):
            # Format error path
            error_path = ".".join(str(p) for p in error.path) if error.path else "root"

            # Create a user-friendly error object
            error_detail = {
                "path": error_path,
                "message": error.message,
                "instance": repr(error.instance)[:100],  # Truncate long instances
            }

            all_errors.append(error_detail)

        if not all_errors:
            return True, []

        return False, all_errors

    except Exception as e:
        import traceback

        logger.error(f"Schema validation error: {e}")
        logger.error(traceback.format_exc())
        return False, [{"path": "schema", "message": str(e)}]


def _display_validation_errors(errors, config_file=None):
    """Display formatted validation errors to the user.

    Args:
        errors: List of error details from _validate_config_with_schema
        config_file: Path to the configuration file for context
    """
    file_name = config_file.name if config_file else "configuration file"

    for error in errors:
        try:
            path = error.get("path", "")
            message = error.get("message", "Unknown error")

            # Determine the error type
            error_type = "Validation error"
            if "is a required property" in message:
                error_type = "Missing required property"
                required_prop = message.split("'")[1]
            elif "anyOf" in message or "oneOf" in message:
                error_type = "Invalid configuration"

            # Output the error with location context
            location = f"in {file_name}"
            if path and path != "root":
                location += f" in {path}"

            click.echo(formatting.format_error(f"{error_type} {location}:"))
            click.echo()

            # Format specific error messages
            if "is a required property" in message:
                required_prop = message.split("'")[1]
                click.echo(f'The property "{required_prop}" is required but was not found.')

                # Add specific guidance based on the property
                if required_prop == "model":
                    click.echo()
                    click.echo("The 'model' property must be an object with 'provider' and 'model' fields. Example:")
                    click.echo()
                    click.echo("  model:")
                    click.echo('    provider: "openai"')
                    click.echo('    model: "gpt-4o"')
                elif required_prop == "type" and "plugins" in path:
                    click.echo()
                    click.echo("Each plugin must have a 'type' field with one of these values: 'sk', 'mcp', or 'agently'")
            elif "anyOf" in message or "oneOf" in message:
                # Complex constraint errors
                if "plugins" in path:
                    click.echo("Invalid plugin configuration")
                    click.echo()
                    click.echo("Each plugin must have the following fields based on its type:")
                    click.echo()
                    click.echo("  - 'sk' plugins: source, path/url, type")
                    click.echo("  - 'mcp' plugins: source, path/url, type, command, args")
                    click.echo("  - 'agently' plugins: source, path/url, type, variables")
                else:
                    click.echo(message)
            else:
                # General error display
                click.echo(message)

            # Add a blank line between errors
            click.echo()
        except Exception as e:
            # Fallback for error display
            logger.debug(f"Error displaying validation error: {e}")
            click.echo(
                formatting.format_error(f"Error parsing validation message: {message if 'message' in locals() else str(e)}")
            )
            click.echo()
