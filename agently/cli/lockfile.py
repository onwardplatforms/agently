"""Lockfile management for the Agently CLI.

This module provides functions to load, save, and manipulate the lockfile.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def get_lockfile_path() -> Path:
    """Get the path to the lockfile in the current directory.

    Returns:
        Path: Path to the lockfile
    """
    return Path.cwd() / "agently.lockfile.json"


def load_lockfile() -> Dict[str, Any]:
    """Load the lockfile from the current directory.

    Returns:
        Dict[str, Any]: The lockfile data, or a new empty structure if no lockfile exists
    """
    lockfile_path = get_lockfile_path()

    # Create or load the lockfile
    if not lockfile_path.exists():
        logger.info("Creating new lockfile")
        lockfile = {"agents": {}}
    else:
        with open(lockfile_path, "r", encoding="utf-8") as f:
            try:
                lockfile = json.load(f)
            except json.JSONDecodeError:
                logger.error("Invalid lockfile, creating new one")
                lockfile = {"agents": {}}

    # Ensure lockfile has correct structure
    if "agents" not in lockfile:
        lockfile["agents"] = {}

    # Remove legacy plugins section if it exists
    if "plugins" in lockfile:
        logger.info("Removing legacy plugins section from lockfile")
        del lockfile["plugins"]

    return lockfile


def save_lockfile(lockfile: Dict[str, Any]) -> None:
    """Save the lockfile to disk.

    Args:
        lockfile (Dict[str, Any]): The lockfile data to save
    """
    lockfile_path = get_lockfile_path()
    with open(lockfile_path, "w", encoding="utf-8") as f:
        json.dump(lockfile, f, indent=2)
    logger.debug("Lockfile saved to %s", lockfile_path)


def cleanup_agents(lockfile: Dict[str, Any], config_agent_ids: Set[str], quiet: bool = False) -> List[str]:
    """Remove agents from the lockfile that are no longer in the configuration.

    Args:
        lockfile (Dict[str, Any]): The lockfile data
        config_agent_ids (Set[str]): Set of agent IDs from the configuration
        quiet (bool, optional): Whether to suppress console output. Defaults to False.

    Returns:
        List[str]: List of agent IDs that were removed
    """
    removed_agents = []
    old_agent_ids = list(lockfile["agents"].keys())  # copy since we'll modify

    for old_id in old_agent_ids:
        if old_id not in config_agent_ids:
            old_name = lockfile["agents"][old_id].get("name", "unknown")
            if not quiet:
                print(f"Removing old agent '{old_name}' ({old_id}) from lockfile...")
            del lockfile["agents"][old_id]
            removed_agents.append(old_id)

    return removed_agents


def get_agent_from_lockfile(lockfile: Dict[str, Any], agent_id: str) -> Optional[Dict[str, Any]]:
    """Get an agent from the lockfile by ID.

    Args:
        lockfile (Dict[str, Any]): The lockfile data
        agent_id (str): The agent ID to look for

    Returns:
        Optional[Dict[str, Any]]: The agent data, or None if not found
    """
    if "agents" in lockfile and agent_id in lockfile["agents"]:
        return lockfile["agents"][agent_id]
    return None


def ensure_agent_in_lockfile(lockfile: Dict[str, Any], agent_id: str, agent_name: str) -> None:
    """Ensure an agent exists in the lockfile with the correct structure.

    Args:
        lockfile (Dict[str, Any]): The lockfile data
        agent_id (str): The agent ID
        agent_name (str): The agent name
    """
    if agent_id not in lockfile["agents"]:
        lockfile["agents"][agent_id] = {"name": agent_name, "plugins": []}
    elif "plugins" not in lockfile["agents"][agent_id]:
        lockfile["agents"][agent_id]["plugins"] = []

    # Update the name in case it changed
    lockfile["agents"][agent_id]["name"] = agent_name
