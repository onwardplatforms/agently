"""Configuration handling for the Agently CLI.

This module provides functions to find, load, and validate configuration files.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import yaml

# Import existing helper functions
from agently.config.parser import find_config_file as _find_config_file
from agently.config.parser import get_all_agents as _get_all_agents
from agently.config.parser import load_agent_config as _load_agent_config

logger = logging.getLogger(__name__)


def find_config_file(file_path: Optional[str] = None) -> Optional[Path]:
    """Find the agent configuration file.

    Args:
        file_path (Optional[str], optional): Explicit path to the configuration file. Defaults to None.

    Returns:
        Optional[Path]: Path to the configuration file, or None if not found
    """
    return _find_config_file(file_path)


def load_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load and validate a configuration file.

    Args:
        config_path (Union[str, Path]): Path to the configuration file

    Returns:
        Dict[str, Any]: The loaded configuration

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the YAML is invalid
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in configuration file: {e}")


def get_all_agents(config_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Get all agents from a configuration file.

    Args:
        config_path (Union[str, Path]): Path to the configuration file

    Returns:
        List[Dict[str, Any]]: List of agent configurations
    """
    return _get_all_agents(config_path)


def load_agent_config(config_path: Union[str, Path], agent_id: Optional[str] = None):
    """Load a specific agent configuration.

    Args:
        config_path (Union[str, Path]): Path to the configuration file
        agent_id (Optional[str], optional): Specific agent ID to load. Defaults to None.

    Returns:
        The loaded agent configuration
    """
    return _load_agent_config(config_path, agent_id)


def get_agent_ids_from_config(config: Dict[str, Any]) -> Set[str]:
    """Extract agent IDs from a configuration.

    Args:
        config (Dict[str, Any]): The loaded configuration

    Returns:
        Set[str]: Set of agent IDs
    """
    if "agents" in config and config["agents"]:
        return {agent.get("id") for agent in config["agents"] if agent.get("id")}
    return set()


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate the configuration structure.

    Args:
        config (Dict[str, Any]): The loaded configuration

    Returns:
        bool: True if valid, False otherwise
    """
    # Basic validation - ensure we have agents
    if not config:
        logger.error("Empty configuration")
        return False

    if "agents" not in config or not config["agents"]:
        logger.error("No agents defined in configuration")
        return False

    # Check each agent has required fields
    for i, agent in enumerate(config["agents"]):
        if "id" not in agent:
            logger.error(f"Agent at index {i} is missing an ID")
            return False

        if "name" not in agent:
            logger.warning(f"Agent '{agent['id']}' is missing a name")

        if "model" not in agent:
            logger.error(f"Agent '{agent['id']}' is missing model configuration")
            return False

        model = agent["model"]
        if "provider" not in model:
            logger.error(f"Agent '{agent['id']}' model is missing provider")
            return False

        if "model" not in model:
            logger.error(f"Agent '{agent['id']}' model is missing model name")
            return False

    return True
