"""Configuration parsing and validation module."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import jsonschema
import yaml
from dotenv import load_dotenv

from agently.config.types import AgentConfig, MCPServerConfig, ModelConfig, PluginConfig, PluginSourceType
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource
from agently.utils.logging import LogLevel

logger = logging.getLogger(__name__)

# Environment variable pattern: ${{ env.VARIABLE_NAME }}
ENV_VAR_PATTERN = re.compile(r"\$\{\{\s*env\.([A-Za-z0-9_]+)\s*\}\}")


def find_config_file(file_path: Optional[str] = None) -> Optional[Path]:
    """Find the agent configuration file.

    Checks for:
    1. Explicit file path if provided
    2. agently.yaml in current directory
    3. agently.yml in current directory

    Args:
        file_path: Optional explicit path to configuration file

    Returns:
        Path to configuration file if found, None otherwise
    """
    # Check explicit path first
    if file_path and Path(file_path).exists():
        logger.debug(f"Using specified config file: {file_path}")
        return Path(file_path)

    # Check default paths
    for ext in ["yaml", "yml"]:
        default_path = Path.cwd() / f"agently.{ext}"
        if default_path.exists():
            logger.debug(f"Found config file: {default_path}")
            return default_path

    logger.debug("No config file found")
    return None


def load_agent_config(file_path: Union[str, Path], agent_id: Optional[str] = None) -> AgentConfig:
    """Load agent configuration from YAML.

    Args:
        file_path: Path to the YAML configuration file
        agent_id: Optional ID of specific agent to load from multi-agent config

    Returns:
        AgentConfig instance

    Raises:
        FileNotFoundError: If the configuration file doesn't exist
        jsonschema.exceptions.ValidationError: If the configuration is invalid
        ValueError: If agent_id is specified but not found in config
    """
    file_path = Path(file_path)
    logger.info(f"Loading agent configuration from {file_path}")

    if not file_path.exists():
        logger.error(f"Configuration file not found: {file_path}")
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    # 1. Load YAML file
    try:
        with open(file_path, "r") as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded YAML configuration: {config}")
    except Exception as e:
        logger.error(f"Error loading YAML: {e}")
        raise ValueError(f"Error loading YAML configuration: {e}")

    # 2. Validate against schema
    schema_path = Path(__file__).parent / "schema.json"
    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)
        jsonschema.validate(config, schema)
        logger.debug("Configuration validated successfully")
    except jsonschema.exceptions.ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise ValueError(f"Error validating configuration: {e}")

    # 3. Resolve environment variables
    load_dotenv()  # Load .env file if exists
    config = resolve_environment_variables(config)

    # 4. Check if we have a multi-agent config (we always do now with the new schema)
    if "agents" in config and config["agents"]:
        # Multi-agent configuration
        if agent_id:
            # Find the specific agent by ID
            for agent_config in config["agents"]:
                # Generate ID if not provided
                if "id" not in agent_config:
                    agent_config["id"] = f"agent-{uuid4().hex[:8]}"

                if agent_config["id"] == agent_id:
                    return create_agent_config(agent_config, file_path)

            # Agent ID not found
            logger.error(f"Agent with ID '{agent_id}' not found in configuration")
            raise ValueError(f"Agent with ID '{agent_id}' not found in configuration")
        else:
            # Use the first agent if no ID specified
            first_agent = config["agents"][0]
            # Generate ID if not provided
            if "id" not in first_agent:
                first_agent["id"] = f"agent-{uuid4().hex[:8]}"

            return create_agent_config(first_agent, file_path)
    else:
        # This should not happen with the new schema, as agents is required
        logger.error("No agents found in configuration")
        raise ValueError("No agents found in configuration")


def get_all_agents(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Get all agents from a configuration file.

    Args:
        file_path: Path to the configuration file

    Returns:
        List of agent configurations

    Raises:
        FileNotFoundError: If the configuration file doesn't exist
    """
    file_path = Path(file_path)
    logger.info(f"Loading all agents from {file_path}")

    if not file_path.exists():
        logger.error(f"Configuration file not found: {file_path}")
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    # Load YAML file
    try:
        with open(file_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading YAML: {e}")
        raise ValueError(f"Error loading YAML configuration: {e}")

    # With the new schema, we always expect an agents array
    if "agents" in config and config["agents"]:
        # Multi-agent configuration
        agents = config["agents"]

        # Ensure each agent has an ID
        for agent in agents:
            if "id" not in agent:
                agent["id"] = f"agent-{uuid4().hex[:8]}"

        return agents
    else:
        # This should not happen with the new schema, but handle it just in case
        logger.error("No agents found in configuration")
        raise ValueError("No agents found in configuration")


def resolve_environment_variables(config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve environment variables in configuration.

    Args:
        config: Configuration dictionary

    Returns:
        Configuration with environment variables resolved
    """
    if isinstance(config, dict):
        # Special handling for env section - skip env var resolution for keys
        if "env" in config and isinstance(config["env"], dict):
            # Create a copy of the env section and resolve env vars in values
            env_section = config["env"].copy()
            for key, value in env_section.items():
                if isinstance(value, str):
                    # Only resolve env vars in values, not keys
                    env_section[key] = resolve_env_vars_in_string(value)

            # Update other keys normally
            result = {k: resolve_environment_variables(v) for k, v in config.items() if k != "env"}
            result["env"] = env_section
            return result
        else:
            return {k: resolve_environment_variables(v) for k, v in config.items()}

    elif isinstance(config, list):
        return [resolve_environment_variables(item) for item in config]
    elif isinstance(config, str):
        return resolve_env_vars_in_string(config)
    else:
        return config


def resolve_env_vars_in_string(text: str) -> str:
    """Resolve environment variables in a string.

    Args:
        text: String that may contain environment variable references

    Returns:
        String with environment variables resolved
    """
    if not isinstance(text, str):
        return text

    def replace_env_var(match):
        var_name = match.group(1)
        var_value = os.environ.get(var_name)
        if var_value is None:
            logger.warning(f"Environment variable not found: {var_name}")
            return f"${{{{{var_name}}}}}"  # Return original if not found
        return var_value

    return ENV_VAR_PATTERN.sub(replace_env_var, text)


def create_agent_config(yaml_config: Dict[str, Any], config_path: Path) -> AgentConfig:
    """Convert YAML configuration to AgentConfig object.

    Args:
        yaml_config: Parsed YAML configuration
        config_path: Path to the configuration file (for resolving relative paths)

    Returns:
        AgentConfig instance
    """
    logger.debug("Creating AgentConfig from YAML")

    # Generate agent ID if not provided
    agent_id = yaml_config.get("id", f"agent-{uuid4().hex[:8]}")

    # Create model config
    model_config = ModelConfig(
        provider=yaml_config["model"]["provider"],
        model=yaml_config["model"]["model"],
        temperature=yaml_config["model"].get("temperature", 0.7),
        max_tokens=yaml_config["model"].get("max_tokens"),
        top_p=yaml_config["model"].get("top_p"),
        frequency_penalty=yaml_config["model"].get("frequency_penalty"),
        presence_penalty=yaml_config["model"].get("presence_penalty"),
    )

    # Process features if present
    features = yaml_config.get("features", {})
    deep_reasoning = features.get("deep_reasoning", False) if features else False

    # Create plugin configs
    plugin_configs = []

    # Create MCP server configs
    mcp_server_configs = []

    # Process plugins (flat array in the new schema)
    for plugin in yaml_config.get("plugins", []):
        # Get the source type (local or github)
        source_type = plugin["source"]
        # Get the plugin type (sk, mcp, or agently)
        plugin_type = plugin["type"]

        if source_type == "local":
            # Handle local plugin
            plugin_path = plugin["path"]
            if not os.path.isabs(plugin_path):
                plugin_path = (config_path.parent / plugin_path).resolve()

            local_source: PluginSourceType = LocalPluginSource(path=Path(plugin_path), plugin_type=plugin_type)

            # For MCP type plugins, create additional MCP server config
            if plugin_type == "mcp":
                # Get the name for the MCP server (use path basename if not specified)
                name = plugin.get("name", Path(plugin_path).stem)

                if "command" in plugin and "args" in plugin:
                    mcp_server_configs.append(
                        MCPServerConfig(
                            name=name,
                            command=plugin["command"],
                            args=plugin.get("args", []),
                            description=plugin.get("description", ""),
                            variables=plugin.get("variables", {}),
                            source_type="local",
                            source_path=str(plugin_path),
                        )
                    )

            # Add to plugin_configs
            plugin_configs.append(PluginConfig(source=local_source, variables=plugin.get("variables", {})))

        elif source_type == "github":
            # Handle GitHub plugin
            github_source: PluginSourceType = GitHubPluginSource(
                repo_url=plugin["url"],
                version=plugin.get("version", plugin.get("branch", "main")),
                plugin_path=plugin.get("plugin_path", ""),
                namespace=plugin.get("namespace", ""),
                name=plugin.get("name", ""),
                plugin_type=plugin_type,
            )

            # If it's an MCP server, create additional MCP server config
            if plugin_type == "mcp":
                setattr(github_source, "command", plugin.get("command", "python"))
                setattr(github_source, "args", plugin.get("args", []))
                setattr(github_source, "description", plugin.get("description", ""))
                setattr(github_source, "server_path", plugin.get("server_path", ""))

                name = github_source.name or plugin.get("name", "")
                # Extract name from URL if not specified
                if not name and hasattr(github_source, "repo_url"):
                    repo_url = github_source.repo_url
                    if "/" in repo_url:
                        name = repo_url.split("/")[-1]
                        # Remove agently-mcp- prefix if it exists
                        if name.startswith("agently-mcp-"):
                            name = name[len("agently-mcp-") :]

                mcp_server_configs.append(
                    MCPServerConfig(
                        name=name,
                        command=plugin.get("command", "python"),
                        args=plugin.get("args", []),
                        description=plugin.get("description", ""),
                        variables=plugin.get("variables", {}),
                        source_type="github",
                        repo_url=github_source.repo_url if hasattr(github_source, "repo_url") else None,
                        version=github_source.version if hasattr(github_source, "version") else None,
                        server_path=plugin.get("server_path", ""),
                    )
                )

            # Add to plugin_configs
            plugin_configs.append(PluginConfig(source=github_source, variables=plugin.get("variables", {})))

    # Set log level
    log_level = LogLevel.NONE  # Default

    # Create agent config with system_prompt now optional
    return AgentConfig(
        id=agent_id,
        name=yaml_config["name"],
        description=yaml_config.get("description", ""),
        system_prompt=yaml_config.get("system_prompt", ""),  # Now optional
        model=model_config,
        plugins=plugin_configs,
        mcp_servers=mcp_server_configs,
        log_level=log_level,
        continuous_reasoning=deep_reasoning,  # Use the deep_reasoning feature
    )
