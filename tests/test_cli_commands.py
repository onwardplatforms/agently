"""Tests for CLI commands."""

import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agently.cli.commands import cli, run
from agently.config.types import AgentConfig, ModelConfig
from agently.errors import AgentError
from agently.utils.logging import LogLevel


@pytest.fixture
def temp_agent_yaml():
    """Create a temporary agent YAML file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as temp_file:
        temp_file.write(
            b"""
version: "1"
agents:
  - name: "CLI Test Agent"
    description: "A test agent for CLI commands"
    system_prompt: "You are a test assistant."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.7
    plugins:
      - source: "local"
        type: "agently"
        path: "./plugins/test"
        variables:
          test_var: "test_value"
          default_name: "CLIFriend"
"""
        )
    yield Path(temp_file.name)
    # Clean up
    os.unlink(temp_file.name)


def test_cli_command_help():
    """Test the CLI help command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "agently.run - Declarative AI agents without code" in result.output


def test_run_command_help():
    """Test the run command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "Run agent in REPL mode" in result.output


def test_run_command_missing_config():
    """Test run command with missing configuration file."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--agent", "nonexistent.yaml"])
    assert result.exit_code == 2  # Click returns 2 for command errors
    assert "Error" in result.output

@pytest.fixture
def temp_project_with_outdated_lockfile():
    """Create a temporary project directory with an outdated lockfile."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        
        # Create agent YAML file with only one plugin
        agent_yaml = project_dir / "agently.yaml"
        with open(agent_yaml, "w") as f:
            f.write("""
version: "1"
agents:
  - id: "cleanup-agent"
    name: "Cleanup Test Agent"
    description: "An agent for testing lockfile cleanup"
    system_prompt: "You are a test assistant."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.7
    plugins:
      - source: "local"
        type: "agently"
        path: "./plugins/current"
        variables:
          test_var: "current_value"
""")
        
        # Create plugins directory with current plugin
        plugins_dir = project_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        
        current_plugin_dir = plugins_dir / "current"
        current_plugin_dir.mkdir(parents=True, exist_ok=True)
        
        with open(current_plugin_dir / "__init__.py", "w") as f:
            f.write("""
from agently.plugins.base import Plugin

class CurrentPlugin(Plugin):
    name = "current"
    description = "A current plugin"
    plugin_instructions = "This is a current plugin."
    
    def get_kernel_functions(self):
        return {"current_function": lambda x: f"Current function called with {x}"}
""")
        
        # Create outdated plugin directory (not referenced in config)
        outdated_plugin_dir = plugins_dir / "outdated"
        outdated_plugin_dir.mkdir(parents=True, exist_ok=True)
        
        with open(outdated_plugin_dir / "__init__.py", "w") as f:
            f.write("""
from agently.plugins.base import Plugin

class OutdatedPlugin(Plugin):
    name = "outdated"
    description = "An outdated plugin"
    plugin_instructions = "This is an outdated plugin."
    
    def get_kernel_functions(self):
        return {"outdated_function": lambda x: f"Outdated function called with {x}"}
""")
        
        # Create a lockfile with both current and outdated plugins
        lockfile = project_dir / "agently.lockfile.json"
        with open(lockfile, "w") as f:
            json.dump({
                "agents": {
                    "cleanup-agent": {
                        "name": "Cleanup Test Agent",
                        "plugins": [
                            {
                                "namespace": "local",
                                "name": "current",
                                "full_name": "current",
                                "version": "local",
                                "source_type": "local",
                                "plugin_type": "agently",
                                "source_path": str(current_plugin_dir),
                                "sha": "current-sha",
                                "installed_at": "2023-01-01T00:00:00"
                            },
                            {
                                "namespace": "local",
                                "name": "outdated",
                                "full_name": "outdated",
                                "version": "local",
                                "source_type": "local",
                                "plugin_type": "agently",
                                "source_path": str(outdated_plugin_dir),
                                "sha": "outdated-sha",
                                "installed_at": "2023-01-01T00:00:00"
                            }
                        ]
                    }
                }
            }, f)
        
        # Change to the temporary directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Change back to the original directory
        os.chdir(original_dir)

def test_init_command_removes_outdated_plugins(temp_project_with_outdated_lockfile):
    """Test that init command removes agents that are no longer in the configuration."""
    # Run the init command
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    
    # Print debug information
    print(f"Exit code: {result.exit_code}")
    print(f"Output: {result.output}")
    if result.exception:
        print(f"Exception: {result.exception}")
        import traceback
        traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Check that the lockfile exists
    lockfile_path = temp_project_with_outdated_lockfile / "agently.lockfile.json"
    assert lockfile_path.exists()
    
    # Check the lockfile contents
    with open(lockfile_path, "r") as f:
        lockfile = json.load(f)
    
    # Verify the current plugin is in the lockfile
    assert "agents" in lockfile
    assert "cleanup-agent" in lockfile["agents"]
    assert "plugins" in lockfile["agents"]["cleanup-agent"]
    
    # Get the plugins list
    plugins = lockfile["agents"]["cleanup-agent"]["plugins"]
    
    # Verify the current plugin exists
    assert any(p["name"] == "current" for p in plugins)
    
    # Verify the outdated plugin has been removed from the lockfile
    assert not any(p["name"] == "outdated" for p in plugins)
