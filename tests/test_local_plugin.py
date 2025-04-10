"""Tests for local plugin source functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from agently.config.parser import load_agent_config
from agently.plugins.sources import LocalPluginSource


@pytest.fixture
def temp_local_yaml_config():
    """Create a temporary YAML config file with local plugin for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
name: "Local Plugin Test Agent"
description: "An agent that tests local plugins"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  local:
    - source: "./plugins/hello"
      variables:
        default_name: "TestFriend"
    - source: "/absolute/path/to/plugin"
      variables:
        option: "value"
    - source: "./plugins/mcp-server"
      type: "mcp"
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


@pytest.fixture
def mock_plugin_dir():
    """Create a temporary directory structure for a mock plugin."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a plugin directory structure
        plugin_dir = Path(temp_dir) / "mock_plugin"
        plugin_dir.mkdir()

        # Create an __init__.py file
        init_file = plugin_dir / "__init__.py"
        with open(init_file, "w") as f:
            f.write(
                """
from agently.plugins.base import Plugin

class MockPlugin(Plugin):
    name = "mock_plugin"
    description = "A mock plugin for testing"
    plugin_instructions = "This is a mock plugin for testing purposes."

    def get_kernel_functions(self):
        return []
"""
            )

        yield plugin_dir


def test_local_plugin_source_path_handling():
    """Test that LocalPluginSource handles paths correctly."""
    # Test with relative path
    source1 = LocalPluginSource(Path("./plugins/hello"))
    assert source1.path.name == "hello"
    assert source1.plugin_type == "sk"  # Default type is "sk"

    # Test with absolute path
    abs_path = Path("/absolute/path/to/plugin").resolve()
    source2 = LocalPluginSource(abs_path)
    assert source2.path == abs_path
    assert source2.plugin_type == "sk"
    
    # Test with MCP type
    source3 = LocalPluginSource(Path("./plugins/mcp-server"), plugin_type="mcp")
    assert source3.path.name == "mcp-server"
    assert source3.plugin_type == "mcp"


@patch("agently.plugins.sources.importlib.util.spec_from_file_location")
@patch("agently.plugins.sources.importlib.util.module_from_spec")
def test_local_plugin_load(mock_module_from_spec, mock_spec_from_file, mock_plugin_dir):
    """Test loading a plugin from a local directory."""
    # Set up mocks for Python module loading
    mock_spec = MagicMock()
    mock_loader = MagicMock()
    mock_spec.loader = mock_loader
    mock_spec_from_file.return_value = mock_spec

    # Create a mock module with a Plugin subclass
    mock_module = MagicMock()
    
    # Add a Plugin base class to the module
    plugin_base_class = type(
        "Plugin",
        (),
        {
            "name": "base_plugin",
            "description": "Base plugin class",
            "plugin_instructions": "Base plugin instructions",
            "get_kernel_functions": lambda self: [],
        },
    )
    mock_module.Plugin = plugin_base_class
    
    # Create the MockPlugin class that inherits from Plugin
    mock_plugin_class = type(
        "MockPlugin",
        (plugin_base_class,),  # Make it inherit from Plugin
        {
            "name": "mock_plugin",
            "description": "A mock plugin for testing",
            "plugin_instructions": "This is a mock plugin for testing purposes.",
            "get_kernel_functions": lambda self: [],
        },
    )
    mock_module.MockPlugin = mock_plugin_class
    mock_module_from_spec.return_value = mock_module

    # Create a LocalPluginSource pointing to our mock plugin directory
    source = LocalPluginSource(mock_plugin_dir)

    # Load the plugin
    plugin_class = source.load()

    # Verify the plugin was loaded correctly
    assert plugin_class.__name__ == "MockPlugin"
    assert plugin_class.name == "mock_plugin"
    assert plugin_class.description == "A mock plugin for testing"

    # Verify the module loading process was called correctly
    mock_spec_from_file.assert_called_once()
    mock_module_from_spec.assert_called_once()
    mock_loader.exec_module.assert_called_once_with(mock_module)


@patch("os.path.isabs")
@patch("agently.plugins.sources.LocalPluginSource.load")
def test_load_local_plugin_config(mock_load, mock_isabs, temp_local_yaml_config):
    """Test loading agent config with local plugins."""
    # Mock the load method to avoid actual file operations
    mock_load.return_value = MagicMock()

    # Mock isabs to handle path resolution
    mock_isabs.return_value = True

    # Load the config
    config = load_agent_config(temp_local_yaml_config)

    # Verify plugins were loaded correctly
    assert len(config.plugins) == 3

    # Check first plugin
    plugin1 = config.plugins[0]
    assert isinstance(plugin1.source, LocalPluginSource)
    assert plugin1.source.path.name == "hello"
    assert plugin1.variables == {"default_name": "TestFriend"}
    assert plugin1.source.plugin_type == "sk"  # Default type is "sk"

    # Check second plugin
    plugin2 = config.plugins[1]
    assert isinstance(plugin2.source, LocalPluginSource)
    assert str(plugin2.source.path).endswith("to/plugin")
    assert plugin2.variables == {"option": "value"}
    assert plugin2.source.plugin_type == "sk"
    
    # Check third plugin (MCP type)
    plugin3 = config.plugins[2]
    assert isinstance(plugin3.source, LocalPluginSource)
    assert plugin3.source.path.name == "mcp-server"
    assert plugin3.variables == {"default_name": "MCPFriend"}
    assert plugin3.source.plugin_type == "mcp"


def test_local_plugin_source_error_handling():
    """Test error handling in LocalPluginSource."""
    # Test with non-existent path
    non_existent_path = Path("/path/that/does/not/exist")
    source = LocalPluginSource(non_existent_path)

    # Loading should raise ImportError
    with pytest.raises(ImportError) as excinfo:
        source.load()
    assert "Plugin path does not exist" in str(excinfo.value)

    # Test with path that's not a .py file or directory with __init__.py
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create an empty directory (no __init__.py)
        empty_dir = Path(temp_dir) / "empty_plugin"
        empty_dir.mkdir()

        # Create a non-Python file
        non_py_file = Path(temp_dir) / "not_python.txt"
        with open(non_py_file, "w") as f:
            f.write("This is not a Python file")

        # Test with empty directory
        source1 = LocalPluginSource(empty_dir)
        with pytest.raises(ImportError) as excinfo:
            source1.load()
        assert "must be a .py file or directory with __init__.py" in str(excinfo.value)

        # Test with non-Python file
        source2 = LocalPluginSource(non_py_file)
        with pytest.raises(ImportError) as excinfo:
            source2.load()
        assert "must be a .py file or directory with __init__.py" in str(excinfo.value)
