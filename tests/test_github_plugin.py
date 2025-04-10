"""Tests for GitHub plugin source functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource


@pytest.fixture
def temp_github_yaml_config():
    """Create a temporary YAML config file with GitHub plugin for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "GitHub Plugin Test Agent"
description: "An agent that tests GitHub plugins"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  github:
    - source: "testuser/hello"
      version: "main"
      variables:
        default_name: "TestFriend"
    - source: "github.com/testuser/agently-plugin-world"
      version: "v1.0.0"
    - source: "https://github.com/testuser/agently-plugin-advanced"
      version: "main"
      plugin_path: "plugins/advanced"
    - source: "testuser/mcp-hello"
      type: "mcp"
      version: "main"
      command: "python"
      args:
        - "server.py"
      variables:
        default_name: "MCPFriend"
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

    # Verify plugins were loaded correctly
    assert len(config.plugins) == 4

    # Check first plugin (short format)
    plugin1 = config.plugins[0]
    assert plugin1.source.namespace == "testuser"
    assert plugin1.source.name == "hello"
    assert plugin1.source.repo_url == "github.com/testuser/agently-plugin-hello"
    assert plugin1.source.version == "main"
    assert plugin1.variables == {"default_name": "TestFriend"}
    assert plugin1.source.plugin_type == "sk"  # Default type is "sk"

    # Check second plugin (github.com format)
    plugin2 = config.plugins[1]
    assert plugin2.source.namespace == "testuser"
    assert plugin2.source.name == "world"
    assert plugin2.source.repo_url == "github.com/testuser/agently-plugin-world"
    assert plugin2.source.version == "v1.0.0"
    assert plugin2.source.plugin_type == "sk"

    # Check third plugin (https URL format with plugin_path)
    plugin3 = config.plugins[2]
    assert plugin3.source.namespace == "testuser"
    assert plugin3.source.name == "advanced"
    assert plugin3.source.repo_url == "github.com/testuser/agently-plugin-advanced"
    assert plugin3.source.version == "main"
    assert plugin3.source.plugin_path == "plugins/advanced"
    assert plugin3.source.plugin_type == "sk"
    
    # Check fourth plugin (MCP server type)
    plugin4 = config.plugins[3]
    assert plugin4.source.namespace == "testuser"
    assert plugin4.source.name == "mcp-hello"
    assert plugin4.source.repo_url.endswith("testuser/mcp-hello")
    assert plugin4.source.version == "main"
    assert plugin4.source.plugin_type == "mcp"
    assert plugin4.variables == {"default_name": "MCPFriend"}
