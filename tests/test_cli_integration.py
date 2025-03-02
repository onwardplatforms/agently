"""Integration tests for CLI commands."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agently.cli.commands import cli
from click.testing import CliRunner


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with necessary files for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary directory
        project_dir = Path(temp_dir)
        
        # Create agent YAML file
        agent_yaml = project_dir / "agently.yaml"
        with open(agent_yaml, "w") as f:
            f.write("""
version: "1"
name: "Test Agent"
description: "A test agent for CLI integration tests"
system_prompt: "You are a test assistant."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  local:
    - source: "./plugins/test"
      variables:
        test_var: "test_value"
""")
        
        # Create plugins directory
        plugins_dir = project_dir / "plugins" / "test"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # Create plugin file
        plugin_file = plugins_dir / "__init__.py"
        with open(plugin_file, "w") as f:
            f.write("""
from agently.plugins.base import Plugin

class TestPlugin(Plugin):
    name = "test"
    description = "A test plugin"
    plugin_instructions = "This is a test plugin."
    
    def get_kernel_functions(self):
        return {"test_function": lambda x: f"Test function called with {x}"}
""")
        
        # Create lockfile
        lockfile = project_dir / "agently.lockfile.json"
        with open(lockfile, "w") as f:
            json.dump({
                "plugins": {
                    "local/test": {
                        "namespace": "local",
                        "name": "test",
                        "full_name": "test",
                        "version": "local",
                        "source_type": "local",
                        "source_path": str(plugins_dir),
                        "sha": "test-sha",
                        "installed_at": "2023-01-01T00:00:00"
                    }
                }
            }, f)
        
        # Change to the temporary directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Change back to the original directory
        os.chdir(original_dir)


def test_cli_init_command(temp_project_dir):
    """Test the init command."""
    # Run the init command
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--quiet"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Check that the lockfile exists
    lockfile_path = temp_project_dir / "agently.lockfile.json"
    assert lockfile_path.exists()
    
    # Check the lockfile contents
    with open(lockfile_path, "r") as f:
        lockfile = json.load(f)
    
    # Verify the plugin is in the lockfile
    assert "local/test" in lockfile["plugins"]


def test_cli_list_command(temp_project_dir):
    """Test the list command."""
    # Run the list command
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Check that the output contains the plugin
    assert "local/test" in result.output


def test_cli_run_command_help(temp_project_dir):
    """Test the run command help."""
    # Run the run command with --help
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Check that the output contains the help text
    assert "Run an agent from your configuration" in result.output


def test_cli_run_command_missing_openai_key(temp_project_dir):
    """Test the run command with missing OpenAI API key."""
    # Ensure OPENAI_API_KEY is not set
    env = os.environ.copy()
    if "OPENAI_API_KEY" in env:
        del env["OPENAI_API_KEY"]
    
    # Run the run command
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["run"])
    
    # Check that the output contains the error message
    assert "Error: Failed to initialize agent" in result.output


def test_cli_run_command_with_config(temp_project_dir):
    """Test the run command with a valid configuration."""
    # Set up environment with a mock API key
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "test-key-123"
    
    # Mock the interactive_loop function to avoid actual execution
    with patch("agently.cli.commands.interactive_loop") as mock_loop:
        # Run the run command
        runner = CliRunner(env=env)
        result = runner.invoke(cli, ["run", "--log-level", "debug"])
        
        # Check that the command executed successfully
        assert result.exit_code == 0
        
        # Verify that interactive_loop was called
        mock_loop.assert_called_once()
        
        # Verify the agent config passed to interactive_loop
        agent_config = mock_loop.call_args[0][0]
        assert agent_config.name == "Test Agent"
        assert agent_config.description == "A test agent for CLI integration tests"
        
        # Verify that plugin variables were loaded correctly
        assert len(agent_config.plugins) == 1
        assert agent_config.plugins[0].variables == {"test_var": "test_value"} 