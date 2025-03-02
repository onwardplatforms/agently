"""Command line interface for the agent runtime."""

import json
import logging
import os
import sys
from pathlib import Path

import click
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource
from agently.utils.logging import LogLevel, configure_logging
from agently.utils.cli_format import (
    PluginStatus, 
    format_plugin_status, 
    format_section_header, 
    format_plan_summary,
    format_apply_summary,
    Color
)

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

    # Check if initialization is needed
    agent_path = Path(agent)
    if not agent_path.exists():
        click.echo(f"Error: Agent configuration file not found: {agent_path}")
        sys.exit(1)

    # Check if lockfile exists and is valid
    lockfile_path = Path.cwd() / "agently.lockfile.json"
    if not lockfile_path.exists():
        click.echo(f"{Color.RED}Error: Plugins not initialized.{Color.RESET}")
        click.echo(f"Run {Color.BOLD}agently init{Color.RESET} to initialize plugins first.")
        sys.exit(1)

    # Load the agent config and lockfile to compare
    try:
        # Parse YAML but don't load full agent config yet
        with open(agent_path, "r") as f:
            yaml_config = yaml.safe_load(f)

        # Read lockfile
        with open(lockfile_path, "r") as f:
            try:
                lockfile = json.load(f)
            except json.JSONDecodeError:
                click.echo(f"{Color.RED}Error: Invalid lockfile.{Color.RESET}")
                click.echo(f"Run {Color.BOLD}agently init{Color.RESET} to fix.")
                sys.exit(1)

        # Check if all configured plugins are in the lockfile
        plugins_yaml = yaml_config.get("plugins", {})
        github_plugins = plugins_yaml.get("github", [])
        local_plugins = plugins_yaml.get("local", [])

        # Get the set of plugins that should be in the lockfile
        expected_plugins = set()

        # Check GitHub plugins
        for plugin_config in github_plugins:
            source = plugin_config["source"]

            # Create a temporary source object to parse the namespace/name
            source_obj = GitHubPluginSource(
                repo_url=source,
                version=plugin_config.get("version", "main"),
                plugin_path=plugin_config.get("plugin_path", ""),
                namespace=plugin_config.get("namespace", ""),
                name=plugin_config.get("name", ""),
            )

            # Add to expected plugins
            expected_plugins.add(f"{source_obj.namespace}/{source_obj.name}")

        # Check local plugins
        for plugin_config in local_plugins:
            source_path = plugin_config["source"]
            plugin_path = Path(source_path)
            if not plugin_path.is_absolute():
                # Resolve relative to the config file
                plugin_path = (agent_path.parent / plugin_path).resolve()
            plugin_name = plugin_path.name

            # Add to expected plugins
            expected_plugins.add(f"local/{plugin_name}")

        # Get the set of plugins in the lockfile
        installed_plugins = set(lockfile.get("plugins", {}).keys())

        # Check if any expected plugins are missing from the lockfile
        missing_plugins = expected_plugins - installed_plugins
        if missing_plugins:
            click.echo(f"{Color.RED}Error: Some plugins are not initialized:{Color.RESET}")
            for plugin in missing_plugins:
                click.echo(f"  - {plugin}")
            click.echo(f"\nRun {Color.BOLD}agently init{Color.RESET} to initialize all plugins.")
            sys.exit(1)

        # Check if there are plugins in the lockfile that aren't in the config
        extra_plugins = installed_plugins - expected_plugins
        if extra_plugins:
            click.echo(f"{Color.YELLOW}Warning: Some installed plugins are not in your configuration:{Color.RESET}")
            for plugin in extra_plugins:
                click.echo(f"  - {plugin}")
            click.echo(f"\nYou may want to run {Color.BOLD}agently init{Color.RESET} to clean up unused plugins.")
            # Don't exit, just warn

        # Now load the full agent config
        agent_config = load_agent_config(agent_path)
        logger.info(f"Loaded agent configuration for: {agent_config.name}")

        # Check for required OpenAI API key if using OpenAI provider
        if agent_config.model.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            click.echo(f"{Color.RED}Error: OPENAI_API_KEY environment variable not set{Color.RESET}")
            click.echo("Please set it with: export OPENAI_API_KEY=your_key_here")
            sys.exit(1)

        # Display agent configuration summary
        click.echo(f"\nThe agent {Color.BOLD}{agent_config.name}{Color.RESET} has been initialized using {Color.CYAN}{agent_config.model.provider}{Color.RESET} {Color.CYAN}{agent_config.model.model}{Color.RESET}")
        if agent_config.description:
            click.echo(f"{agent_config.description}")
        
        # Display loaded plugins
        if agent_config.plugins:
            click.echo(f"\n{Color.BOLD}Loaded plugins:{Color.RESET}")
            for plugin_config in agent_config.plugins:
                plugin_key = f"{plugin_config.source.namespace}/{plugin_config.source.name}"
                click.echo(f"  • {plugin_key}")
        
        click.echo("\nType a message to begin. Type exit to quit.\n")

        # Run interactive loop
        interactive_loop(agent_config)
    except Exception as e:
        click.echo(f"{Color.RED}Error: {e}{Color.RESET}")
        logger.exception(f"Error running agent: {e}")
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


def _initialize_plugins(config_path, quiet=False, force=False):
    """Initialize plugins based on configuration file.

    Args:
        config_path: Path to the agent configuration file
        quiet: Whether to reduce output verbosity
        force: Whether to force reinstallation of all plugins

    Raises:
        FileNotFoundError: If the configuration file does not exist
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Logging is now configured by the calling function

    if force and not quiet:
        click.echo("Force mode enabled: reinstalling all plugins")

    # Parse YAML
    with open(config_path, "r") as f:
        yaml_config = yaml.safe_load(f)

    plugins_yaml = yaml_config.get("plugins", {})
    github_plugins = plugins_yaml.get("github", [])
    local_plugins = plugins_yaml.get("local", [])

    if not quiet:
        click.echo(f"Agently will initialize plugins based on your configuration.")

    # Create lockfile directory if it doesn't exist
    lockfile_path = Path.cwd() / "agently.lockfile.json"
    lockfile_dir = lockfile_path.parent
    lockfile_dir.mkdir(parents=True, exist_ok=True)

    # Read existing lockfile or create a new one
    existing_plugins = {}
    if lockfile_path.exists():
        with open(lockfile_path, "r") as f:
            try:
                lockfile = json.load(f)
                existing_plugins = lockfile.get("plugins", {})
            except json.JSONDecodeError:
                if not quiet:
                    click.echo("Invalid lockfile, creating a new one")
                lockfile = {"plugins": {}}
    else:
        if not quiet:
            click.echo("Creating new lockfile")
        lockfile = {"plugins": {}}

    # Ensure plugins section exists
    if "plugins" not in lockfile:
        lockfile["plugins"] = {}
    
    # Track plugin status for reporting
    to_add = set()
    to_update = set()
    unchanged = set()
    to_remove = set()
    failed = set()
    
    # Track plugin details for reporting
    plugin_details = {}
    
    # Track successfully installed plugins
    installed_plugins = set()
    
    # First, identify plugins to be added, updated, or removed
    # GitHub plugins
    for github_plugin_config in github_plugins:
        repo_url = github_plugin_config["source"]
        version = github_plugin_config.get("version", "main")
        plugin_path = github_plugin_config.get("plugin_path", "")
        
        # Create a GitHubPluginSource to parse the namespace/name
        source = GitHubPluginSource(
            repo_url=repo_url,
            version=version,
            plugin_path=plugin_path,
            force_reinstall=force,
        )
        
        plugin_key = f"{source.namespace}/{source.name}"
        plugin_details[plugin_key] = f"version={version}"
        
        # Check if plugin exists in lockfile
        if plugin_key in existing_plugins:
            # Check if version has changed
            if existing_plugins[plugin_key].get("version") != version or force:
                to_update.add(plugin_key)
            else:
                unchanged.add(plugin_key)
        else:
            to_add.add(plugin_key)
    
    # Local plugins
    for local_plugin_config in local_plugins:
        source_path = local_plugin_config["source"]
        
        # Resolve relative paths
        if not os.path.isabs(source_path):
            source_path = os.path.abspath(os.path.join(os.path.dirname(config_path), source_path))
        
        plugin_name = os.path.basename(source_path)
        plugin_key = f"local/{plugin_name}"
        plugin_details[plugin_key] = f"path={source_path}"
        
        # Check if plugin exists in lockfile
        if plugin_key in existing_plugins:
            # For local plugins, check if SHA has changed or force is enabled
            if force:
                to_update.add(plugin_key)
            else:
                # We'll check SHA during installation
                unchanged.add(plugin_key)
        else:
            to_add.add(plugin_key)
    
    # Identify plugins to remove (in lockfile but not in config)
    for plugin_key in existing_plugins:
        if plugin_key not in to_add and plugin_key not in to_update and plugin_key not in unchanged:
            to_remove.add(plugin_key)
    
    # Print plan
    if not quiet:
        click.echo("\nAgently will perform the following actions:")
        
        if to_add or to_update or to_remove:
            if to_add:
                click.echo(f"\n{format_section_header('Plugins to add')}")
                for plugin_key in sorted(to_add):
                    click.echo(format_plugin_status(PluginStatus.ADDED, plugin_key, plugin_details.get(plugin_key)))
            
            if to_update:
                click.echo(f"\n{format_section_header('Plugins to update')}")
                for plugin_key in sorted(to_update):
                    click.echo(format_plugin_status(PluginStatus.UPDATED, plugin_key, plugin_details.get(plugin_key)))
            
            if unchanged:
                click.echo(f"\n{format_section_header('Plugins unchanged')}")
                for plugin_key in sorted(unchanged):
                    click.echo(format_plugin_status(PluginStatus.UNCHANGED, plugin_key, plugin_details.get(plugin_key)))
            
            if to_remove:
                click.echo(f"\n{format_section_header('Plugins to remove')}")
                for plugin_key in sorted(to_remove):
                    click.echo(format_plugin_status(PluginStatus.REMOVED, plugin_key))
            
            click.echo(f"\n{format_plan_summary(len(to_add), len(to_update), len(unchanged), len(to_remove))}")
        else:
            click.echo("\nNo changes. Your plugin configuration is up to date.")
        
        click.echo("\nApplying changes...")
    
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
            
            if not quiet:
                if plugin_key in to_add:
                    click.echo(format_plugin_status(PluginStatus.ADDED, plugin_key, f"version={version}"))
                elif plugin_key in to_update:
                    click.echo(format_plugin_status(PluginStatus.UPDATED, plugin_key, f"version={version}"))
        except Exception as e:
            logger.error(f"Failed to install GitHub plugin {repo_url}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e)))
    
    # Install local plugins
    for local_plugin_config in local_plugins:
        source_path = local_plugin_config["source"]
        
        # Resolve relative paths
        if not os.path.isabs(source_path):
            source_path = os.path.abspath(os.path.join(os.path.dirname(config_path), source_path))
        
        # Create a LocalPluginSource with the resolved path
        local_source = LocalPluginSource(
            path=Path(source_path),
            namespace="local",  # Fixed namespace for local plugins
            name=os.path.basename(source_path),  # Use directory name as plugin name
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
            
            if not quiet:
                if plugin_key in to_add:
                    click.echo(format_plugin_status(PluginStatus.ADDED, plugin_key, f"path={source_path}"))
                elif plugin_key in to_update:
                    click.echo(format_plugin_status(PluginStatus.UPDATED, plugin_key, f"path={source_path}"))
        except Exception as e:
            logger.error(f"Failed to install local plugin {source_path}: {e}")
            failed.add(plugin_key)
            if not quiet:
                click.echo(format_plugin_status(PluginStatus.FAILED, plugin_key, str(e)))
    
    # Remove plugins that are no longer in the config
    for plugin_key in to_remove:
        if not quiet:
            click.echo(format_plugin_status(PluginStatus.REMOVED, plugin_key))
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
            click.echo(f"Initializing Agently configuration from {agent}")
        
        installed_plugins = _initialize_plugins(agent, quiet=quiet, force=force)
        
        if not quiet:
            click.echo("\nAgently initialization complete!")
            click.echo("To run your agent, use: agently run")
    except Exception as e:
        click.echo(f"Error: {e}")
        logger.exception(f"Error initializing plugins: {e}")
        sys.exit(1)
