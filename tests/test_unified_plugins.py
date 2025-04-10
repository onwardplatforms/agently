"""Tests for unified plugin and MCP server management."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import GitHubPluginSource, LocalPluginSource


@pytest.fixture
def temp_unified_yaml_config():
    """Create a temporary YAML config file with unified plugin format for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Unified Plugin Test Agent"
description: "An agent that tests unified plugin format"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  local:
    - source: "./plugins/hello"
      variables:
        default_name: "LocalFriend"
    - source: "./plugins/mcp-server"
      type: "mcp"
      command: "python"
      args:
        - "server.py"
      variables:
        default_name: "LocalMCPFriend"
  github:
    - source: "testuser/hello"
      version: "main"
      variables:
        default_name: "RemoteFriend"
    - source: "testuser/mcp-hello"
      type: "mcp"
      version: "main"
      command: "python"
      args:
        - "server.py"
      variables:
        default_name: "RemoteMCPFriend"
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_github_plugin_source_mcp_type_handling():
    """Test that GitHubPluginSource correctly handles MCP plugin types."""
    # Create a GitHubPluginSource with MCP type
    source = GitHubPluginSource(
        repo_url="testuser/mcp-hello",
        plugin_type="mcp"
    )
    
    # Verify the correct cache directory path is used
    assert str(source.cache_dir).endswith("plugins/mcp")
    
    # Verify repository URL is correctly formed without plugin prefix
    assert source.repo_url == "github.com/testuser/mcp-hello"
    
    # Create another source with SK type (default)
    source_sk = GitHubPluginSource(
        repo_url="testuser/hello"
    )
    
    # Verify the correct cache directory path is used
    assert str(source_sk.cache_dir).endswith("plugins/sk")
    
    # Verify repository URL is correctly formed with plugin prefix
    assert source_sk.repo_url == "github.com/testuser/agently-plugin-hello"


def test_local_plugin_source_mcp_type_handling():
    """Test that LocalPluginSource correctly handles MCP plugin types."""
    # Create a LocalPluginSource with MCP type
    source = LocalPluginSource(
        path=Path("./plugins/mcp-server"),
        plugin_type="mcp"
    )
    
    # Verify the correct cache directory path is used
    assert str(source.cache_dir).endswith("plugins/mcp")
    
    # Create another source with SK type (default)
    source_sk = LocalPluginSource(
        path=Path("./plugins/hello")
    )
    
    # Verify the correct cache directory path is used
    assert str(source_sk.cache_dir).endswith("plugins/sk")


@patch("agently.plugins.sources.GitHubPluginSource.load")
@patch("agently.plugins.sources.LocalPluginSource.load")
def test_unified_config_parsing(mock_local_load, mock_github_load, temp_unified_yaml_config):
    """Test that unified config is parsed correctly with plugin types."""
    # Mock the load methods to avoid actual plugin loading
    mock_local_load.return_value = MagicMock()
    mock_github_load.return_value = MagicMock()
    
    # Load the agent config
    config = load_agent_config(temp_unified_yaml_config)
    
    # Verify the plugins were loaded correctly
    assert len(config.plugins) == 4
    
    # Find and check each plugin
    sk_plugins = [p for p in config.plugins if p.source.plugin_type == "sk"]
    mcp_plugins = [p for p in config.plugins if p.source.plugin_type == "mcp"]
    
    # Verify plugin counts
    assert len(sk_plugins) == 2
    assert len(mcp_plugins) == 2
    
    # Check SK plugins
    github_sk = next((p for p in sk_plugins if isinstance(p.source, GitHubPluginSource)), None)
    local_sk = next((p for p in sk_plugins if isinstance(p.source, LocalPluginSource)), None)
    
    assert github_sk is not None
    assert local_sk is not None
    assert github_sk.source.name == "hello"
    assert local_sk.source.path.name == "hello"
    assert github_sk.variables == {"default_name": "RemoteFriend"}
    assert local_sk.variables == {"default_name": "LocalFriend"}
    
    # Check MCP plugins
    github_mcp = next((p for p in mcp_plugins if isinstance(p.source, GitHubPluginSource)), None)
    local_mcp = next((p for p in mcp_plugins if isinstance(p.source, LocalPluginSource)), None)
    
    assert github_mcp is not None
    assert local_mcp is not None
    assert github_mcp.source.name == "mcp-hello"
    assert local_mcp.source.path.name == "mcp-server"
    assert github_mcp.variables == {"default_name": "RemoteMCPFriend"}
    assert local_mcp.variables == {"default_name": "LocalMCPFriend"}
    
    # Verify repository URL construction
    assert github_sk.source.repo_url == "github.com/testuser/agently-plugin-hello"
    assert github_mcp.source.repo_url == "github.com/testuser/mcp-hello" 