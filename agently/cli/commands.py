"""Command line interface for the agent runtime."""

import logging
import os
import sys
import json
from pathlib import Path

import click
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource
from agently.utils.logging import LogLevel, configure_logging

from .interactive import interactive_loop

logger = logging.getLogger(__name__)


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
def run(agent, log_level):
    """Run an agent from your configuration."""
    # Set up logging
    if log_level:
        level = getattr(LogLevel, log_level.upper())
        configure_logging(level=level)
        logger.debug(f"Log level set to {log_level.upper()}")
    else:
        configure_logging(level=LogLevel.NONE)

    logger.info(f"Starting agently run with agent config: {agent}")

    # Load agent config
    try:
        agent_path = Path(agent)
        if not agent_path.exists():
            click.echo(f"Error: Agent configuration file not found: {agent_path}")
            sys.exit(1)

        agent_config = load_agent_config(agent_path)
        logger.info(f"Loaded agent configuration for: {agent_config.name}")

        # Check for required OpenAI API key if using OpenAI provider
        if agent_config.model.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            click.echo("Error: OPENAI_API_KEY environment variable not set")
            click.echo("Please set it with: export OPENAI_API_KEY=your_key_here")
            sys.exit(1)

        # Run interactive loop
        interactive_loop(agent_config)
    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error running agent: {e}")
        sys.exit(1)


@cli.command()
@click.argument("plugin", required=False)
@click.option("--version", "-v", help="Specific version to install (tag, branch or commit SHA)")
@click.option("--config", "-c", default="agently.yaml", help="Path to agent configuration file")
def install(plugin, version, config):
    """Install plugins defined in config or a specific plugin.

    If no plugin is specified, installs all plugins from the configuration file.
    If a plugin is specified, installs that specific plugin (format: namespace/name).
    """
    configure_logging(level=LogLevel.INFO)

    try:
        # If a specific plugin is provided
        if plugin:
            click.echo(f"Installing plugin: {plugin}")

            # Parse namespace/name
            if "/" not in plugin:
                click.echo("Error: Plugin must be specified as namespace/name")
                click.echo("Example: agently install username/agently-plugin-hello")
                sys.exit(1)

            namespace, name = plugin.split("/", 1)

            # Construct GitHub URL
            repo_url = f"github.com/{namespace}/{name}"

            # Use specified version or default to main
            plugin_version = version if version else "main"

            # Create and load the plugin
            source = GitHubPluginSource(repo_url=repo_url, version=plugin_version, namespace=namespace, name=name)

            # Actually load (which will clone and cache the plugin)
            try:
                source.load()
                click.echo(f"✅ Successfully installed {plugin} at version {plugin_version}")
            except Exception as e:
                click.echo(f"❌ Failed to install plugin {plugin}: {e}")
                sys.exit(1)

        # Otherwise install all plugins from config
        else:
            config_path = Path(config)
            if not config_path.exists():
                click.echo(f"Error: Configuration file not found: {config_path}")
                sys.exit(1)

            click.echo(f"Installing plugins from {config_path}")

            # Parse YAML but don't load full agent config
            with open(config_path, "r") as f:
                yaml_config = yaml.safe_load(f)

            plugins_yaml = yaml_config.get("plugins", {})
            github_plugins = plugins_yaml.get("github", [])

            if not github_plugins:
                click.echo("No GitHub plugins found in configuration")
                sys.exit(0)

            # Install each plugin
            success_count = 0
            for plugin_config in github_plugins:
                repo = plugin_config["repo"]
                plugin_version = plugin_config.get("version", "main")  # Default to main if not specified

                click.echo(f"Installing {repo} at {plugin_version}...")

                try:
                    # Parse namespace/name from repo URL
                    namespace, name = None, None
                    if "namespace" in plugin_config:
                        namespace = plugin_config["namespace"]
                    if "name" in plugin_config:
                        name = plugin_config["name"]

                    # Create and load the source
                    source = GitHubPluginSource(
                        repo_url=repo,
                        version=plugin_version,
                        plugin_path=plugin_config.get("plugin_path", ""),
                        namespace=namespace,
                        name=name,
                    )

                    # Actually load (which will clone and cache the plugin)
                    source.load()
                    success_count += 1
                    click.echo(f"✅ Successfully installed {repo} at version {plugin_version}")
                except Exception as e:
                    click.echo(f"❌ Failed to install plugin {repo}: {str(e)}")

            click.echo(f"Installed {success_count} of {len(github_plugins)} plugins")

    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error installing plugins: {e}")
        sys.exit(1)


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
