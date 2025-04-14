"""Tests for GitHub plugin source functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource
from agently.config.types import AgentConfig


@pytest.fixture
def temp_github_yaml_config():
    """Create a temporary YAML config file with GitHub plugin for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
agents:
  - name: "GitHub Plugin Test Agent"
    description: "An agent that tests GitHub plugins"
    system_prompt: "You are a test assistant."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.7
    plugins:
      - source: "github"
        url: "testuser/hello"
        type: "agently"
        version: "main"
        variables:
          default_name: "TestFriend"
      - source: "github"
        url: "github.com/testuser/agently-plugin-world"
        type: "agently"
        version: "v1.0.0"
      - source: "github"
        url: "https://github.com/testuser/agently-plugin-advanced"
        type: "agently"
        version: "main"
        path: "plugins/advanced"
      - source: "github"
        url: "testuser/mcp-hello"
        type: "mcp"
        version: "main"
        command: "python"
        args:
          - "server.py"
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_github_plugin_source_formats():
    """Test that different GitHub plugin source formats are handled correctly."""
    # Test short format (user/name)
    source1 = GitHubPluginSource(repo_url="testuser/hello")
    assert source1.namespace == "testuser"
    assert source1.name == "hello"
    assert source1.full_repo_name == "agently-plugin-hello"
    assert source1.repo_url == "github.com/testuser/agently-plugin-hello"

    # Test github.com format
    source2 = GitHubPluginSource(repo_url="github.com/testuser/world")
    assert source2.namespace == "testuser"
    assert source2.name == "world"
    assert source2.full_repo_name == "agently-plugin-world"
    assert source2.repo_url == "github.com/testuser/agently-plugin-world"

    # Test https URL format
    source3 = GitHubPluginSource(repo_url="https://github.com/testuser/advanced")
    assert source3.namespace == "testuser"
    assert source3.name == "advanced"
    assert source3.full_repo_name == "agently-plugin-advanced"
    assert source3.repo_url == "github.com/testuser/agently-plugin-advanced"

    # Test with existing prefix
    source4 = GitHubPluginSource(repo_url="testuser/agently-plugin-existing")
    assert source4.namespace == "testuser"
    assert source4.name == "existing"
    assert source4.full_repo_name == "agently-plugin-existing"
    assert source4.repo_url == "github.com/testuser/agently-plugin-existing"
    
    # Test with MCP server type
    source5 = GitHubPluginSource(repo_url="testuser/hello", plugin_type="mcp")
    assert source5.namespace == "testuser"
    assert source5.name == "hello"
    assert source5.full_repo_name == "hello"  # No prefix for MCP servers
    assert source5.repo_url == "github.com/testuser/hello"  # No prefix in URL for MCP
    assert source5.plugin_type == "mcp"
    
    # Test with MCP prefix in name
    source6 = GitHubPluginSource(repo_url="testuser/agently-mcp-hello", plugin_type="mcp")
    assert source6.namespace == "testuser"
    assert source6.name == "hello"  # Strip prefix for storage name
    assert source6.full_repo_name == "agently-mcp-hello"  # Keep prefix in full repo name
    assert source6.repo_url == "github.com/testuser/agently-mcp-hello"
    assert source6.plugin_type == "mcp"


@patch("agently.plugins.sources.GitHubPluginSource.load")
def test_load_github_plugin_config(mock_load, temp_github_yaml_config):
    """Test loading agent config with GitHub plugins."""
    # Mock the load method to avoid actual GitHub operations
    mock_load.return_value = MagicMock()

    # Load the config
    config = load_agent_config(temp_github_yaml_config)

    # Verify agents were loaded correctly
    assert isinstance(config, AgentConfig)
    assert config.name == "GitHub Plugin Test Agent"
    assert config.description == "An agent that tests GitHub plugins"
    assert config.system_prompt == "You are a test assistant."
    assert config.model.provider == "openai"
    assert config.model.model == "gpt-4o"
    
    # Verify plugins
    assert hasattr(config, "plugins")
    assert len(config.plugins) == 4
    
    # Each plugin is a PluginConfig object 
    # The source attribute is the actual source object (GitHubPluginSource)
    
    # Check first plugin (github source)
    plugin1 = config.plugins[0]
    assert isinstance(plugin1.source, GitHubPluginSource)
    assert "github.com/testuser/agently-plugin-hello" in plugin1.source.repo_url
    assert plugin1.source.plugin_type == "agently"
    assert plugin1.source.version == "main"
    assert plugin1.variables == {"default_name": "TestFriend"}
    
    # Check second plugin (github.com format)
    plugin2 = config.plugins[1]
    assert isinstance(plugin2.source, GitHubPluginSource)
    assert "github.com/testuser/agently-plugin-world" in plugin2.source.repo_url
    assert plugin2.source.plugin_type == "agently"
    assert plugin2.source.version == "v1.0.0"
    
    # Check third plugin (https URL format with plugin_path)
    plugin3 = config.plugins[2]
    assert isinstance(plugin3.source, GitHubPluginSource)
    assert "github.com/testuser/agently-plugin-advanced" in plugin3.source.repo_url
    assert plugin3.source.plugin_type == "agently"
    assert plugin3.source.version == "main"
    assert hasattr(plugin3.source, "plugin_path")
    
    # Check fourth plugin (MCP server type)
    plugin4 = config.plugins[3]
    assert isinstance(plugin4.source, GitHubPluginSource)
    assert "github.com/testuser/mcp-hello" in plugin4.source.repo_url
    assert plugin4.source.plugin_type == "mcp"
    assert plugin4.source.version == "main"
    # MCP plugins shouldn't have variables according to the schema
    assert not plugin4.variables

def test_mcp_server_plugin_get_kernel_functions():
    """Test that MCPServerPlugin's get_kernel_functions method returns an empty dict."""
    # Create a GitHub plugin source with MCP type
    source = GitHubPluginSource(
        repo_url="testuser/mcp-server",
        plugin_type="mcp"
    )
    
    # Load the plugin class (which should be MCPServerPlugin)
    with patch("agently.plugins.sources.GitHubPluginSource._clone_or_update_repo"):
        with patch("agently.plugins.sources.GitHubPluginSource._get_repo_sha"):
            plugin_class = source.load()
            
            # Verify that get_kernel_functions returns an empty dictionary, not a list
            kernel_functions = plugin_class.get_kernel_functions()
            assert isinstance(kernel_functions, dict)
            assert len(kernel_functions) == 0
            
            # Explicitly verify it's not a list
            assert not isinstance(kernel_functions, list)
