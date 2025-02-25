"""Agent runtime v2 package."""

from .agents.agent import Agent
from .config.types import (
    AgentConfig,
    CapabilityConfig,
    ConversationConfig,
    ModelConfig,
    PluginConfig,
)
from .conversation.context import ConversationContext, Message
from .conversation.manager import ConversationManager
from .plugins.base import (
    Plugin,
    PluginVariable,
    VariableValidation,
)
from .plugins.sources import (
    GitHubPluginSource,
    LocalPluginSource,
    PluginSource,
)

__all__ = [
    # Core components
    "Agent",
    "ConversationManager",
    "Message",
    "ConversationContext",
    # Configuration
    "AgentConfig",
    "ModelConfig",
    "PluginConfig",
    "CapabilityConfig",
    "ConversationConfig",
    # Plugin system
    "Plugin",
    "PluginVariable",
    "VariableValidation",
    "PluginSource",
    "LocalPluginSource",
    "GitHubPluginSource",
]
