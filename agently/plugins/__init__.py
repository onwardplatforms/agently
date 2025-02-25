"""Plugin system for extending agent capabilities."""

from .base import Plugin, PluginVariable, VariableValidation
from .manager import PluginManager
from .sources import GitHubPluginSource, LocalPluginSource, PluginSource

__all__ = [
    "Plugin",
    "PluginVariable",
    "VariableValidation",
    "PluginSource",
    "LocalPluginSource",
    "GitHubPluginSource",
    "PluginManager",
]
