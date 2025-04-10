"""Configuration type definitions for the Agently framework.

This module defines the dataclasses used for configuring various components
of the Agently framework, including models, plugins, capabilities, agents,
and conversations.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from agently.utils.logging import LogLevel

# Forward references for type hints
if TYPE_CHECKING:
    from agently.plugins.sources import GitHubPluginSource, LocalPluginSource

    PluginSourceType = Union["LocalPluginSource", "GitHubPluginSource"]
else:
    PluginSourceType = Any


@dataclass
class ModelConfig:
    """Configuration for a model provider."""

    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


@dataclass
class PluginConfig:
    """Configuration for a plugin."""

    source: PluginSourceType  # Can be LocalPluginSource or GitHubPluginSource
    variables: Optional[Dict[str, Any]] = None


@dataclass
class CapabilityConfig:
    """Configuration for an agent capability."""

    type: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    description: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "local"  # "local" or "github"
    source_path: Optional[str] = None  # Local path if source_type is "local"
    repo_url: Optional[str] = None  # GitHub repo URL if source_type is "github"
    version: Optional[str] = None  # GitHub version/tag if source_type is "github"
    server_path: str = ""  # Path within GitHub repo if source_type is "github"


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    id: str
    name: str
    description: str
    system_prompt: str
    model: ModelConfig
    plugins: List[PluginConfig] = field(default_factory=list)
    mcp_servers: List[MCPServerConfig] = field(default_factory=list)
    capabilities: List[CapabilityConfig] = field(default_factory=list)
    log_level: int = LogLevel.NONE  # Default to no logging
    continuous_reasoning: bool = False  # Enable/disable continuous reasoning mode


@dataclass
class ConversationConfig:
    """Configuration for a conversation."""

    id: str
    memory_enabled: bool = True
    memory_window: int = 10
    turn_strategy: str = "single_agent"  # or "round_robin", etc.
