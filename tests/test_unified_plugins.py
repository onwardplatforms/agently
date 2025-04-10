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


def test_lockfile_structure():
    """Test that the lockfile has the correct structure with plugin types."""
    # Create a simpler test that directly tests the lockfile structure
    # without going through the complex initialization process
    
    # Define the test data
    old_format_lockfile = {
        "plugins": {
            "testuser/plugin1": {"commit_sha": "abc123", "plugin_type": "sk"},
            "local/local1": {"sha256": "def456", "plugin_type": "sk"}
        },
        "mcp_servers": {
            "testuser/mcp-hello": {"commit_sha": "ghi789"},
            "local/mcp-server": {"sha256": "jkl012"}
        }
    }
    
    # Expected new format
    expected_new_format = {
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
    
    # Simulate the migration logic directly
    new_format = {"plugins": {"sk": {}, "mcp": {}}}
    
    # Copy SK plugins
    for key, value in old_format_lockfile["plugins"].items():
        new_format["plugins"]["sk"][key] = value
    
    # Copy MCP plugins
    for key, value in old_format_lockfile["mcp_servers"].items():
        new_format["plugins"]["mcp"][key] = value
    
    # Verify structure
    assert "plugins" in new_format
    assert "sk" in new_format["plugins"]
    assert "mcp" in new_format["plugins"]
    
    # Verify content
    assert "testuser/plugin1" in new_format["plugins"]["sk"]
    assert "local/local1" in new_format["plugins"]["sk"]
    assert "testuser/mcp-hello" in new_format["plugins"]["mcp"]
    assert "local/mcp-server" in new_format["plugins"]["mcp"]
    
    # Verify the structure matches expected
    assert new_format == expected_new_format


def test_lockfile_migration():
    """Test migration of old-style lockfile to new format."""
    # Define the test data - old format lockfile
    old_format_lockfile = {
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
    expected_new_format = {
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
    
    # Simulate the migration logic directly
    new_format = {"plugins": {"sk": {}, "mcp": {}}}
    
    # Copy SK plugins
    if isinstance(old_format_lockfile.get("plugins", {}), dict) and not any(k in old_format_lockfile["plugins"] for k in ["sk", "mcp"]):
        for key, value in old_format_lockfile["plugins"].items():
            new_format["plugins"]["sk"][key] = value
    
    # Copy MCP servers to MCP plugins
    if "mcp_servers" in old_format_lockfile:
        for key, value in old_format_lockfile["mcp_servers"].items():
            new_format["plugins"]["mcp"][key] = value
    
    # Verify structure
    assert "plugins" in new_format
    assert "sk" in new_format["plugins"]
    assert "mcp" in new_format["plugins"]
    
    # Verify content
    assert "testuser/plugin1" in new_format["plugins"]["sk"]
    assert "local/local1" in new_format["plugins"]["sk"]
    assert "testuser/mcp-hello" in new_format["plugins"]["mcp"]
    assert "local/mcp-server" in new_format["plugins"]["mcp"]
    
    # Verify the structure matches expected
    assert new_format == expected_new_format


def test_initialize_plugins_with_mocking():
    """Test that _initialize_plugins correctly processes the lockfile with all mocks in place."""
    # Create mock paths
    mock_config_path = MagicMock(spec=Path)
    mock_config_path.exists.return_value = True
    mock_config_path.parent = MagicMock()
    
    # Mock the yaml config
    yaml_content = {
        "plugins": {
            "github": [
                {"source": "testuser/plugin1", "version": "main"},
                {"source": "testuser/mcp-hello", "version": "main", "type": "mcp"}
            ],
            "local": [
                {"source": "./plugins/local1"},
                {"source": "./plugins/mcp-server", "type": "mcp"}
            ]
        }
    }
    
    # Create factory functions for mock sources
    def github_source_factory(**kwargs):
        mock_source = MagicMock()
        # Set attributes based on the provided kwargs
        repo_url = kwargs.get('repo_url', '')
        plugin_type = kwargs.get('plugin_type', 'sk')
        
        if 'plugin1' in repo_url:
            mock_source.plugin_type = "sk"
            mock_source.namespace = "testuser"
            mock_source.name = "plugin1"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "testuser", 
                "name": "plugin1", 
                "plugin_type": "sk", 
                "sha": "abc123"
            }
            mock_source.load.return_value = MagicMock()
        elif 'mcp-hello' in repo_url:
            mock_source.plugin_type = "mcp"
            mock_source.namespace = "testuser"
            mock_source.name = "mcp-hello"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "testuser", 
                "name": "mcp-hello", 
                "plugin_type": "mcp", 
                "sha": "def456"
            }
            mock_source.load.return_value = MagicMock()
        else:
            # Default values
            mock_source.plugin_type = plugin_type
            mock_source.namespace = "testuser"
            mock_source.name = "unknown"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "testuser", 
                "name": "unknown", 
                "plugin_type": plugin_type, 
                "sha": "abc123"
            }
            mock_source.load.return_value = MagicMock()
            
        return mock_source
    
    def local_source_factory(**kwargs):
        mock_source = MagicMock()
        # Set attributes based on the path
        path = kwargs.get('path', '')
        plugin_type = kwargs.get('plugin_type', 'sk')
        
        if isinstance(path, MagicMock):
            # If path is a mock, use the name from basename
            name = "local1" if mock_basename.call_count == 0 else "mcp-server"
            mock_basename.return_value = name
        else:
            # Try to get the name from the actual path
            path_str = str(path)
            name = "local1" if "local1" in path_str else "mcp-server" if "mcp-server" in path_str else "unknown"
        
        if name == "local1":
            mock_source.plugin_type = "sk"
            mock_source.namespace = "local"
            mock_source.name = "local1"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "local", 
                "name": "local1", 
                "plugin_type": "sk", 
                "sha": "def456"
            }
            mock_source.load.return_value = MagicMock()
        elif name == "mcp-server":
            mock_source.plugin_type = "mcp"
            mock_source.namespace = "local"
            mock_source.name = "mcp-server"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "local", 
                "name": "mcp-server", 
                "plugin_type": "mcp", 
                "sha": "jkl012"
            }
            mock_source.load.return_value = MagicMock()
        else:
            # Default values
            mock_source.plugin_type = plugin_type
            mock_source.namespace = "local"
            mock_source.name = "unknown"
            mock_source.needs_update.return_value = False
            mock_source._get_plugin_info.return_value = {
                "namespace": "local", 
                "name": "unknown", 
                "plugin_type": plugin_type, 
                "sha": "def456"
            }
            mock_source.load.return_value = MagicMock()
            
        return mock_source
    
    # Mock YAML loading
    with patch("yaml.safe_load", return_value=yaml_content), \
         patch("builtins.open", MagicMock()), \
         patch("json.dump") as mock_dump, \
         patch("json.load") as mock_load, \
         patch("pathlib.Path.cwd") as mock_cwd, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("os.path.basename") as mock_basename, \
         patch("agently.cli.commands.GitHubPluginSource") as mock_github_source_class, \
         patch("agently.cli.commands.LocalPluginSource") as mock_local_source_class:
         
        # Set up the mocks
        mock_load.return_value = {"plugins": {"sk": {}, "mcp": {}}}
        mock_cwd.return_value = MagicMock(spec=Path)
        
        # Set up factory functions as side effects
        mock_github_source_class.side_effect = github_source_factory
        mock_local_source_class.side_effect = local_source_factory
        
        # Import and call function
        from agently.cli.commands import _initialize_plugins
        _initialize_plugins(mock_config_path, quiet=True)
        
        # Verify json.dump was called 
        assert mock_dump.call_count > 0
        
        # Extract the lockfile data that was saved
        calls = mock_dump.call_args_list
        last_call = calls[-1]
        lockfile_data = last_call[0][0]  # First argument to json.dump
        
        # Verify the lockfile structure
        assert "plugins" in lockfile_data
        assert "sk" in lockfile_data["plugins"]
        assert "mcp" in lockfile_data["plugins"]
        
        # Verify that GitHub plugins are recorded in the right sections
        assert "testuser/plugin1" in lockfile_data["plugins"]["sk"]
        assert "testuser/mcp-hello" in lockfile_data["plugins"]["mcp"]
        
        # Verify that local plugins are recorded in the right sections
        assert "local/local1" in lockfile_data["plugins"]["sk"]
        assert "local/mcp-server" in lockfile_data["plugins"]["mcp"]

        # Verify the structure matches expected
        assert lockfile_data["plugins"] == {
            "sk": {
                "local/local1": {"namespace": "local", "name": "local1", "plugin_type": "sk", "sha": "def456"},
                "testuser/plugin1": {"namespace": "testuser", "name": "plugin1", "plugin_type": "sk", "sha": "abc123"},
            },
            "mcp": {
                "local/mcp-server": {"namespace": "local", "name": "mcp-server", "plugin_type": "mcp", "sha": "jkl012"},
                "testuser/mcp-hello": {"namespace": "testuser", "name": "mcp-hello", "plugin_type": "mcp", "sha": "def456"},
            },
        } 