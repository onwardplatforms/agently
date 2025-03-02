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


@patch("agently.plugins.sources.GitHubPluginSource.load")
def test_load_github_plugin_config(mock_load, temp_github_yaml_config):
    """Test loading agent config with GitHub plugins."""
    # Mock the load method to avoid actual GitHub operations
    mock_load.return_value = MagicMock()

    # Load the config
    config = load_agent_config(temp_github_yaml_config)

    # Verify plugins were loaded correctly
    assert len(config.plugins) == 3

    # Check first plugin (short format)
    plugin1 = config.plugins[0]
    assert plugin1.source.namespace == "testuser"
    assert plugin1.source.name == "hello"
    assert plugin1.source.repo_url == "github.com/testuser/agently-plugin-hello"
    assert plugin1.source.version == "main"
    assert plugin1.variables == {"default_name": "TestFriend"}

    # Check second plugin (github.com format)
    plugin2 = config.plugins[1]
    assert plugin2.source.namespace == "testuser"
    assert plugin2.source.name == "world"
    assert plugin2.source.repo_url == "github.com/testuser/agently-plugin-world"
    assert plugin2.source.version == "v1.0.0"

    # Check third plugin (https URL format with plugin_path)
    plugin3 = config.plugins[2]
    assert plugin3.source.namespace == "testuser"
    assert plugin3.source.name == "advanced"
    assert plugin3.source.repo_url == "github.com/testuser/agently-plugin-advanced"
    assert plugin3.source.version == "main"
    assert plugin3.source.plugin_path == "plugins/advanced"
