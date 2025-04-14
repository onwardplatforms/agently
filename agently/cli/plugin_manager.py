"""Plugin management for the Agently CLI.

This module provides functions to handle plugin installation, updates, and removal.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from agently_sdk import styles

from agently.plugins.sources import GitHubPluginSource, LocalPluginSource

logger = logging.getLogger(__name__)


class PluginStatus:
    """Status of a plugin during initialization."""

    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"


def format_plugin_status(status: str, plugin_key: str, details: Optional[str] = None, plugin_type: str = "sk") -> str:
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


def process_local_plugin(
    agent_id: str,
    plugin_config: Dict[str, Any],
    config_path: Path,
    lockfile: Dict[str, Any],
    quiet: bool = False,
    force: bool = False,
) -> Tuple[str, str, bool]:
    """Process a local plugin for an agent.

    Args:
        agent_id (str): The ID of the agent
        plugin_config (Dict[str, Any]): The plugin configuration
        config_path (Path): Path to the agent configuration file
        lockfile (Dict[str, Any]): The lockfile data
        quiet (bool, optional): Whether to suppress console output. Defaults to False.
        force (bool, optional): Whether to force reinstallation. Defaults to False.

    Returns:
        Tuple[str, str, bool]: (plugin_key, status, success)
    """
    source_path = plugin_config["path"]
    plugin_type = plugin_config["type"]

    # Convert to absolute path if needed
    if not os.path.isabs(source_path):
        abs_source_path = config_path.parent / source_path
    else:
        abs_source_path = Path(source_path)

    # Derive a plugin name from the path
    plugin_name = os.path.basename(source_path)
    local_source = LocalPluginSource(
        path=abs_source_path, namespace="local", name=plugin_name, force_reinstall=force, plugin_type=plugin_type
    )
    plugin_key = f"{local_source.namespace}/{local_source.name}"

    # Check for existing plugin in lockfile
    existing_plugin = None
    for p in lockfile["agents"][agent_id]["plugins"]:
        if p.get("name") == plugin_name and p.get("namespace") == "local" and p.get("plugin_type") == plugin_type:
            existing_plugin = p
            break

    # Decide add/update/unchanged
    status = ""
    if existing_plugin:
        lockfile_sha = existing_plugin.get("sha", "")
        if force or local_source.needs_update(lockfile_sha):
            status = PluginStatus.UPDATED
            if not quiet:
                print(f"- Updating {plugin_key} from local path...")
        else:
            status = PluginStatus.UNCHANGED
            if not quiet:
                print(f"- {plugin_key} is up to date")
    else:
        status = PluginStatus.ADDED
        if not quiet:
            print(f"- Installing {plugin_key}...")

    # Attempt to load the plugin
    try:
        plugin_class = local_source.load()
        plugin_info = local_source._get_plugin_info(plugin_class)
        if "variables" in plugin_config:
            plugin_info["variables"] = plugin_config["variables"]
        plugin_info["plugin_type"] = plugin_type

        # Update or insert in lockfile
        if existing_plugin:
            for i, p in enumerate(lockfile["agents"][agent_id]["plugins"]):
                if p.get("name") == plugin_name and p.get("namespace") == "local" and p.get("plugin_type") == plugin_type:
                    lockfile["agents"][agent_id]["plugins"][i] = plugin_info
                    break
        else:
            lockfile["agents"][agent_id]["plugins"].append(plugin_info)

        return plugin_key, status, True

    except Exception as e:
        import traceback

        logger.error(f"Failed to install local plugin {source_path}: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        logger.error(f"Plugin type: {plugin_type}, Plugin key: {plugin_key}")
        logger.error(f"Plugin config: {plugin_config}")
        if not quiet:
            print(f"{styles.red('✗')} Failed to install {plugin_key}: {e}")
        return plugin_key, PluginStatus.FAILED, False


def process_github_plugin(
    agent_id: str, plugin_config: Dict[str, Any], lockfile: Dict[str, Any], quiet: bool = False, force: bool = False
) -> Tuple[str, str, bool]:
    """Process a GitHub plugin for an agent.

    Args:
        agent_id (str): The ID of the agent
        plugin_config (Dict[str, Any]): The plugin configuration
        lockfile (Dict[str, Any]): The lockfile data
        quiet (bool, optional): Whether to suppress console output. Defaults to False.
        force (bool, optional): Whether to force reinstallation. Defaults to False.

    Returns:
        Tuple[str, str, bool]: (plugin_key, status, success)
    """
    repo_url = plugin_config["url"]
    plugin_type = plugin_config["type"]
    version = plugin_config.get("version", "main")
    branch = plugin_config.get("branch")
    git_reference = branch if branch else version
    namespace = plugin_config.get("namespace", "github")

    logger.debug(
        f"Processing GitHub plugin: repo_url={repo_url}, plugin_type={plugin_type}, "
        f"version={version}, branch={branch}, namespace={namespace}"
    )

    github_source = GitHubPluginSource(
        repo_url=repo_url, version=git_reference, namespace=namespace, force_reinstall=force, plugin_type=plugin_type
    )
    plugin_key = f"{github_source.namespace}/{github_source.name}"

    logger.debug(
        f"Created GitHubPluginSource with: namespace={github_source.namespace}, "
        f"name={github_source.name}, plugin_key={plugin_key}"
    )
    logger.debug(f"Full repo name: {github_source.full_repo_name}, repo_url: {github_source.repo_url}")

    # Check for existing plugins and remove duplicates
    # This ensures we're always working with the most recent configuration
    existing_plugin = None
    plugins_to_remove = []

    for i, p in enumerate(lockfile["agents"][agent_id]["plugins"]):
        # For GitHub plugins, match based on repo URL and plugin type
        # This ensures we identify the same plugin regardless of version/branch changes
        if (
            p.get("plugin_type") == plugin_type
            and p.get("source_type") == "github"
            and p.get("repo_url", "").replace("github.com/", "") == github_source.repo_url.replace("github.com/", "")
        ):
            if existing_plugin is None:
                # Keep the first one we find as the existing plugin to update
                existing_plugin = p
            else:
                # Mark any additional entries for removal
                plugins_to_remove.append(i)

    # Remove duplicate entries from highest index to lowest to avoid index shifting issues
    for i in sorted(plugins_to_remove, reverse=True):
        logger.debug(f"Removing duplicate plugin entry at index {i}")
        lockfile["agents"][agent_id]["plugins"].pop(i)

    # Decide add/update/unchanged
    status = ""
    if existing_plugin:
        logger.debug(f"Found existing plugin in lockfile: {existing_plugin}")
        lockfile_sha = existing_plugin.get("sha", "")
        logger.debug(f"Checking if plugin needs update, lockfile_sha: {lockfile_sha}")
        if force or github_source.needs_update(lockfile_sha):
            status = PluginStatus.UPDATED
            if not quiet:
                print(f"- Updating {plugin_key} from GitHub...")
        else:
            status = PluginStatus.UNCHANGED
            if not quiet:
                print(f"- {plugin_key} is up to date")
    else:
        status = PluginStatus.ADDED
        if not quiet:
            print(f"- Installing {plugin_key} from GitHub...")

    # Attempt to install the plugin
    try:
        logger.debug(f"Loading GitHub plugin: {plugin_key}")
        plugin_class = github_source.load()
        logger.debug(f"Successfully loaded plugin class: {plugin_class.__name__}")

        plugin_info = github_source._get_plugin_info(plugin_class)
        logger.debug(f"Generated plugin info: {plugin_info}")

        if "variables" in plugin_config:
            plugin_info["variables"] = plugin_config["variables"]
            logger.debug(f"Added variables to plugin info: {plugin_config['variables']}")

        plugin_info["plugin_type"] = plugin_type

        # Add command details if MCP
        if plugin_type == "mcp":
            mcp_details = {}
            if "command" in plugin_config:
                mcp_details["command"] = plugin_config["command"]
            if "args" in plugin_config:
                mcp_details["args"] = plugin_config["args"]
            plugin_info["mcp_details"] = mcp_details
            logger.debug(f"Added MCP details to plugin info: {mcp_details}")

            # Update plugin_key to use the correct namespace from plugin_info
            plugin_key = f"{plugin_info['namespace']}/{plugin_info['name']}"
            logger.debug(f"Updated plugin_key for MCP plugin: {plugin_key}")

        # Update or insert in lockfile
        if existing_plugin:
            # Update the existing plugin
            for i, p in enumerate(lockfile["agents"][agent_id]["plugins"]):
                if (
                    p.get("plugin_type") == plugin_type
                    and p.get("source_type") == "github"
                    and p.get("repo_url", "").replace("github.com/", "") == github_source.repo_url.replace("github.com/", "")
                ):
                    lockfile["agents"][agent_id]["plugins"][i] = plugin_info
                    logger.debug(f"Updated existing plugin in lockfile at index {i}")
                    break
        else:
            lockfile["agents"][agent_id]["plugins"].append(plugin_info)
            logger.debug("Added new plugin to lockfile")

        # For MCP plugins, we always consider them successful even if they can't be fully initialized now
        if plugin_type == "mcp":
            if not quiet:
                # Use plugin_info for display to ensure correct namespace
                display_key = f"{plugin_info['namespace']}/{plugin_info['name']}"
                version_display = f" ({plugin_info['version']})" if plugin_info.get("version") else ""

                if status == PluginStatus.ADDED:
                    print(f"  github/mcp @ {display_key}{version_display} was added")
                elif status == PluginStatus.UPDATED:
                    print(f"  github/mcp @ {display_key}{version_display} was updated")
                else:
                    print(f"  github/mcp @ {display_key}{version_display} is up-to-date")

            return plugin_key, status, True

        return plugin_key, status, True

    except Exception as e:
        import traceback

        logger.error(f"Failed to install GitHub plugin {repo_url}: {str(e)}")
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        logger.error(f"Plugin config: {plugin_config}")
        # Debug info to understand the state of the plugin
        logger.error(f"Plugin key: {plugin_key}, plugin_type: {plugin_type}, namespace: {namespace}")
        logger.error(
            f"GitHub source data: namespace={github_source.namespace}, name={github_source.name}, "
            f"repo_url={github_source.repo_url}"
        )

        if not quiet:
            print(f"{styles.red('✗')} Failed to install {plugin_key}: {str(e)}")
        return plugin_key, PluginStatus.FAILED, False


def sync_plugins(
    config_path: Path,
    config: Dict[str, Any],
    lockfile: Dict[str, Any],
    agent_id: Optional[str] = None,
    quiet: bool = False,
    force: bool = False,
) -> Dict[str, int]:
    """Synchronize plugins for one or all agents.

    Args:
        config_path (Path): Path to the agent configuration file
        config (Dict[str, Any]): The loaded configuration
        lockfile (Dict[str, Any]): The loaded lockfile
        agent_id (Optional[str], optional): Specific agent ID to process. Defaults to None (all agents).
        quiet (bool, optional): Whether to suppress console output. Defaults to False.
        force (bool, optional): Whether to force reinstallation. Defaults to False.

    Returns:
        Dict[str, int]: Statistics of what happened (added, updated, unchanged, removed, failed)
    """
    # Track statistics
    stats = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "removed": 0,
        "failed": 0,
    }

    # Identify agents to process
    if "agents" in config:
        if agent_id:
            # Find a single agent in config
            single_agent = next((a for a in config["agents"] if a.get("id") == agent_id), None)
            if not single_agent:
                raise ValueError(f"Agent with ID '{agent_id}' not found in configuration")
            agents_to_process = [single_agent]
            if not quiet:
                print(f"Initializing plugins for agent: {single_agent.get('name')} ({agent_id})")
        else:
            # Process all agents
            agents_to_process = config["agents"]
            if not quiet:
                print(f"Initializing plugins for {len(agents_to_process)} agents")
    else:
        raise ValueError("No agents found in configuration")

    # Process each agent
    for agent in agents_to_process:
        agent_id = agent.get("id", f"agent-{uuid4().hex[:8]}")
        agent_name = agent.get("name", "default")

        # Ensure agent in lockfile
        if agent_id not in lockfile["agents"]:
            lockfile["agents"][agent_id] = {"name": agent_name, "plugins": []}
        elif "plugins" not in lockfile["agents"][agent_id]:
            lockfile["agents"][agent_id]["plugins"] = []

        if not quiet:
            print(f"\nProcessing agent: {agent_name} ({agent_id})")

        # Grab the config's plugin list
        plugins = agent.get("plugins", [])

        # If not quiet, mention how many plugins
        total_plugins = len(plugins)
        if not quiet and total_plugins > 0:
            print(f"Found {total_plugins} plugins for agent {agent_name}")

        # If there are no plugins for this agent, count it as 'unchanged'
        if total_plugins == 0:
            stats["unchanged"] += 1
            continue

        # We'll track plugin keys
        installed_plugins = set()

        # For each plugin in config:
        for plugin_config in plugins:
            source_type = plugin_config["source"]

            if source_type == "local":
                plugin_key, status, success = process_local_plugin(
                    agent_id, plugin_config, config_path, lockfile, quiet, force
                )
            elif source_type == "github":
                plugin_key, status, success = process_github_plugin(agent_id, plugin_config, lockfile, quiet, force)
            else:
                logger.error(f"Unknown plugin source type: {source_type}")
                continue

            # Track for stats
            if success:
                installed_plugins.add(plugin_key)
                if status == PluginStatus.ADDED:
                    stats["added"] += 1
                elif status == PluginStatus.UPDATED:
                    stats["updated"] += 1
                elif status == PluginStatus.UNCHANGED:
                    stats["unchanged"] += 1
            else:
                stats["failed"] += 1

        # Clean up plugins that are no longer in the configuration
        plugins_to_remove = []
        for plugin in lockfile["agents"][agent_id]["plugins"]:
            plugin_key = f"{plugin.get('namespace', 'unknown')}/{plugin.get('name', 'unknown')}"
            if plugin_key not in installed_plugins:
                plugins_to_remove.append(plugin)
                stats["removed"] += 1
                if not quiet:
                    print(f"  {styles.red('- ')} Removed {plugin_key}")

        # Remove the outdated plugins
        for plugin in plugins_to_remove:
            lockfile["agents"][agent_id]["plugins"].remove(plugin)

    return stats
