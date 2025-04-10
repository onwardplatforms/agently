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
from agently.cli.commands import _initialize_plugins


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


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory with plugin configs for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Create a sample agently.yaml file with both plugin types
    yaml_content = """
agent:
  name: Test Agent
  model: gpt-3.5-turbo

plugins:
  github:
    - source: testuser/plugin1
      version: main
    - source: testuser/mcp-hello
      version: main
      type: mcp
  local:
    - source: ./plugins/local1
    - source: ./plugins/mcp-server
      type: mcp
"""
    config_file = config_dir / "agently.yaml"
    config_file.write_text(yaml_content)
    
    # Create local plugin directories
    plugins_dir = config_dir / "plugins"
    plugins_dir.mkdir()
    
    local1_dir = plugins_dir / "local1"
    local1_dir.mkdir()
    
    mcp_dir = plugins_dir / "mcp-server"
    mcp_dir.mkdir()
    
    return config_dir


@pytest.fixture
def mock_git_repo(monkeypatch):
    """Mock git operations for testing."""
    def mock_clone(*args, **kwargs):
        return True
    
    def mock_get_sha(*args, **kwargs):
        return "abc123"
    
    monkeypatch.setattr("agently.plugins.sources.GitHubPluginSource._clone_or_update_repo", mock_clone)
    monkeypatch.setattr("agently.plugins.sources.GitHubPluginSource._get_repo_sha", mock_get_sha)
    monkeypatch.setattr("agently.plugins.sources.LocalPluginSource._calculate_plugin_sha", lambda self: "def456")


def test_github_repo_url_construction():
    """Test repository URL construction for different plugin types."""
    # Standard plugin
    sk_source = GitHubPluginSource(
        repo_url="testuser/plugin1",
        version="main",
        plugin_type="sk"
    )
    assert sk_source.repo_url == "github.com/testuser/agently-plugin-plugin1"
    
    # MCP plugin
    mcp_source = GitHubPluginSource(
        repo_url="testuser/mcp-hello",
        version="main",
        plugin_type="mcp"
    )
    assert mcp_source.repo_url == "github.com/testuser/mcp-hello"
    
    # Custom namespace
    custom_source = GitHubPluginSource(
        repo_url="custom/mcp-test",
        version="main",
        plugin_type="mcp",
        namespace="custom"
    )
    assert custom_source.repo_url == "github.com/custom/mcp-test"


def test_local_plugin_type_handling():
    """Test that LocalPluginSource handles plugin types correctly."""
    # Standard plugin
    sk_source = LocalPluginSource(
        path=Path("/tmp/plugins/local1"),
        plugin_type="sk"
    )
    assert sk_source.plugin_type == "sk"
    assert sk_source.cache_dir == Path.cwd() / ".agently" / "plugins" / "sk"
    
    # MCP plugin
    mcp_source = LocalPluginSource(
        path=Path("/tmp/plugins/mcp-server"),
        plugin_type="mcp"
    )
    assert mcp_source.plugin_type == "mcp"
    assert mcp_source.cache_dir == Path.cwd() / ".agently" / "plugins" / "mcp"


@patch("agently.plugins.sources.GitHubPluginSource.load")
@patch("agently.plugins.sources.LocalPluginSource.load")
def test_lockfile_structure(mock_local_load, mock_github_load, temp_config_dir, mock_git_repo):
    """Test that the lockfile has the correct structure with plugin types."""
    # Set up mocks
    mock_github_plugin = MagicMock()
    mock_github_plugin.namespace = "testuser"
    mock_github_plugin.name = "plugin1"
    
    mock_github_mcp = MagicMock()
    mock_github_mcp.namespace = "testuser"
    mock_github_mcp.name = "mcp-hello"
    
    mock_local_plugin = MagicMock()
    mock_local_plugin.namespace = "local"
    mock_local_plugin.name = "local1"
    
    mock_local_mcp = MagicMock()
    mock_local_mcp.namespace = "local"
    mock_local_mcp.name = "mcp-server"
    
    # Set up return values for the load methods
    mock_github_load.side_effect = [mock_github_plugin, mock_github_mcp]
    mock_local_load.side_effect = [mock_local_plugin, mock_local_mcp]
    
    # Patch _get_plugin_info to return structured data
    with patch("agently.plugins.sources.GitHubPluginSource._get_plugin_info") as mock_github_info:
        with patch("agently.plugins.sources.LocalPluginSource._get_plugin_info") as mock_local_info:
            # Set up return values for _get_plugin_info
            mock_github_info.side_effect = [
                {"namespace": "testuser", "name": "plugin1", "plugin_type": "sk", "commit_sha": "abc123"},
                {"namespace": "testuser", "name": "mcp-hello", "plugin_type": "mcp", "commit_sha": "def456"}
            ]
            mock_local_info.side_effect = [
                {"namespace": "local", "name": "local1", "plugin_type": "sk", "sha256": "abc123"},
                {"namespace": "local", "name": "mcp-server", "plugin_type": "mcp", "sha256": "def456"}
            ]
            
            # Run the actual initialization
            with patch("builtins.open"), patch("json.dump"), patch("json.load") as mock_load:
                # Mock an empty lockfile
                mock_load.return_value = {"plugins": {"sk": {}, "mcp": {}}}
                
                # Call the function
                config_path = temp_config_dir / "agently.yaml"
                _initialize_plugins(config_path, quiet=True)
                
                # Check that _get_plugin_info was called with the right parameters
                assert mock_github_info.call_count == 2
                assert mock_local_info.call_count == 2
                
                # Check the expected calls to json.dump
                # Get the last call to json.dump
                calls = [c for c in mock_dump.call_args_list if len(c[0]) > 0]
                assert len(calls) > 0
                
                last_call = calls[-1]
                lockfile_data = last_call[0][0]  # First argument to json.dump
                
                # Check the structure
                assert "plugins" in lockfile_data
                assert "sk" in lockfile_data["plugins"]
                assert "mcp" in lockfile_data["plugins"]
                
                # Check that SK plugins are in the right place
                assert "testuser/plugin1" in lockfile_data["plugins"]["sk"]
                assert "local/local1" in lockfile_data["plugins"]["sk"]
                
                # Check that MCP plugins are in the right place
                assert "testuser/mcp-hello" in lockfile_data["plugins"]["mcp"]
                assert "local/mcp-server" in lockfile_data["plugins"]["mcp"]


def test_lockfile_migration():
    """Test migration of old-style lockfile to new format."""
    old_lockfile = {
        "plugins": {
            "testuser/plugin1": {"commit_sha": "abc123", "plugin_type": "sk"},
            "local/local1": {"sha256": "def456", "plugin_type": "sk"}
        },
        "mcp_servers": {
            "testuser/mcp-hello": {"commit_sha": "ghi789"},
            "local/mcp-server": {"sha256": "jkl012"}
        }
    }
    
    # Expected structure after migration
    expected = {
        "plugins": {
            "sk": {
                "testuser/plugin1": {"commit_sha": "abc123", "plugin_type": "sk"},
                "local/local1": {"sha256": "def456", "plugin_type": "sk"}
            },
            "mcp": {
                "testuser/mcp-hello": {"commit_sha": "ghi789"},
                "local/mcp-server": {"sha256": "jkl012"}
            }
        }
    }
    
    # Create a temporary file with the old lockfile
    with patch("builtins.open", new_callable=MagicMock), \
         patch("json.load", return_value=old_lockfile), \
         patch("json.dump") as mock_dump, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("agently.plugins.sources.GitHubPluginSource.load"), \
         patch("agently.plugins.sources.LocalPluginSource.load"):
        
        # Mock the yaml config
        with patch("yaml.safe_load") as mock_yaml:
            mock_yaml.return_value = {"plugins": {"github": [], "local": []}}
            
            # Test migration
            _initialize_plugins("dummy_path", quiet=True)
            
            # Check that the migration happened correctly
            calls = [c for c in mock_dump.call_args_list if len(c[0]) > 0]
            assert len(calls) > 0
            
            last_call = calls[-1]
            migrated_data = last_call[0][0]  # First argument to json.dump
            
            # Structure checks
            assert "plugins" in migrated_data
            assert "sk" in migrated_data["plugins"]
            assert "mcp" in migrated_data["plugins"]
            
            # Content checks for SK plugins
            assert "testuser/plugin1" in migrated_data["plugins"]["sk"]
            assert "local/local1" in migrated_data["plugins"]["sk"]
            
            # Content checks for MCP plugins
            assert "testuser/mcp-hello" in migrated_data["plugins"]["mcp"]
            assert "local/mcp-server" in migrated_data["plugins"]["mcp"]
            
            # Verify the mcp_servers key is removed
            assert "mcp_servers" not in migrated_data 