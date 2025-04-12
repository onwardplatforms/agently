"""Integration tests for CLI commands."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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
                    "sk": {
                        "local/test": {
                            "namespace": "local",
                            "name": "test",
                            "full_name": "test",
                            "version": "local",
                            "source_type": "local",
                            "plugin_type": "sk",
                            "source_path": str(plugins_dir),
                            "sha": "test-sha",
                            "installed_at": "2023-01-01T00:00:00"
                        }
                    },
                    "mcp": {}
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
    lockfile_path = temp_project_dir / "agently.lockfile.json"
    assert lockfile_path.exists()
    
    # Check the lockfile contents
    with open(lockfile_path, "r") as f:
        lockfile = json.load(f)
    
    # Verify the plugin is in the lockfile with the new structure
    assert "plugins" in lockfile
    assert "sk" in lockfile["plugins"]
    assert "local/test" in lockfile["plugins"]["sk"]


def test_cli_list_command(temp_project_dir):
    """Test the list command."""
    # Run the list agents command - now we must specify the 'agents' subcommand
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "agents"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Print output for debugging
    print(f"List command output: {result.output}")
    
    # Verify the output format reflects the new agent listing structure
    assert "Configured agents" in result.output
    assert "Test Agent" in result.output


def test_cli_run_command_help(temp_project_dir):
    """Test the run command help."""
    # Run the run command with --help
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Check that the output contains the help text
    assert "Run agent in REPL mode" in result.output


def test_cli_run_command_missing_openai_key(temp_project_dir):
    """Test the run command with missing OpenAI API key."""
    # First initialize the agent so we can test the OpenAI key error
    # Rather than the initialization error
    runner = CliRunner()
    init_result = runner.invoke(cli, ["init"])
    assert init_result.exit_code == 0
    
    # Ensure OPENAI_API_KEY is not set
    env = os.environ.copy()
    if "OPENAI_API_KEY" in env:
        del env["OPENAI_API_KEY"]
    
    # Run the run command with --force to bypass initialization check
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["run", "--force"])
    
    # Now we should get the OpenAI key error instead of the initialization error
    assert "Error: OpenAI API key not found" in result.output or "Failed to initialize agent" in result.output


def test_cli_run_command_with_config(temp_project_dir):
    """Test the run command with a valid configuration."""
    # First initialize the agent
    runner = CliRunner()
    init_result = runner.invoke(cli, ["init"])
    assert init_result.exit_code == 0
    
    # Set up environment with a mock API key
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "test-key-123"
    
    # Mock the interactive_loop function to avoid actual execution
    with patch("agently.cli.commands.interactive_loop") as mock_loop:
        # Run the run command with --force to bypass potential initialization issues
        runner = CliRunner(env=env)
        result = runner.invoke(cli, ["run", "--log-level", "debug", "--force"])
        
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


@pytest.fixture
def temp_mcp_project_dir():
    """Create a temporary project directory with MCP server configurations for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary directory
        project_dir = Path(temp_dir)
        
        # Create agent YAML file with unified plugin format for MCP servers
        agent_yaml = project_dir / "agently.yaml"
        with open(agent_yaml, "w") as f:
            f.write("""
version: "1"
name: "MCP Test Agent"
description: "A test agent for MCP server integration tests"
system_prompt: "You are a test assistant with MCP capabilities."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  github:
    - source: "testuser/test-plugin"
      type: "sk"
      version: "main"
    - source: "testuser/mcp-test"
      type: "mcp"
      version: "main"
      command: "python"
      args: ["server.py"]
      description: "A test MCP server from GitHub"
  local:
    - source: "./plugins/local-sk"
      type: "sk"
    - source: "./plugins/local-mcp"
      type: "mcp"
      command: "python"
      args: ["server.py"]
      description: "A test local MCP server"
""")
        
        # Create plugins directories
        sk_dir = project_dir / "plugins" / "local-sk"
        sk_dir.mkdir(parents=True, exist_ok=True)
        
        mcp_dir = project_dir / "plugins" / "local-mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        
        # Create plugin files
        sk_file = sk_dir / "__init__.py"
        with open(sk_file, "w") as f:
            f.write("""
from agently.plugins.base import Plugin

class TestSKPlugin(Plugin):
    name = "local-sk"
    description = "A test SK plugin"
    plugin_instructions = "This is a test SK plugin."
    
    def get_kernel_functions(self):
        return {"test_function": lambda x: f"Test function called with {x}"}
""")
        
        # Create lockfile with both SK and MCP plugins
        lockfile = project_dir / "agently.lockfile.json"
        with open(lockfile, "w") as f:
            json.dump({
                "plugins": {
                    "sk": {
                        "local/local-sk": {
                            "namespace": "local",
                            "name": "local-sk",
                            "full_name": "local-sk",
                            "version": "local",
                            "source_type": "local",
                            "plugin_type": "sk",
                            "source_path": str(sk_dir),
                            "sha": "test-sk-sha",
                            "installed_at": "2023-01-01T00:00:00"
                        },
                        "testuser/test-plugin": {
                            "namespace": "testuser",
                            "name": "test-plugin",
                            "full_name": "testuser/test-plugin",
                            "version": "main",
                            "source_type": "github",
                            "plugin_type": "sk",
                            "repo_url": "github.com/testuser/test-plugin",
                            "sha": "test-gh-sha",
                            "installed_at": "2023-01-01T00:00:00"
                        }
                    },
                    "mcp": {
                        "local/local-mcp": {
                            "namespace": "local",
                            "name": "local-mcp",
                            "full_name": "local-mcp",
                            "version": "local",
                            "source_type": "local",
                            "plugin_type": "mcp",
                            "source_path": str(mcp_dir),
                            "command": "python",
                            "args": ["server.py"],
                            "sha": "test-mcp-sha",
                            "installed_at": "2023-01-01T00:00:00"
                        },
                        "testuser/mcp-test": {
                            "namespace": "testuser",
                            "name": "mcp-test",
                            "full_name": "testuser/mcp-test",
                            "version": "main",
                            "source_type": "github",
                            "plugin_type": "mcp",
                            "repo_url": "github.com/testuser/mcp-test",
                            "sha": "test-mcp-gh-sha",
                            "installed_at": "2023-01-01T00:00:00"
                        }
                    }
                }
            }, f)
        
        # Setup .agently directory structure for MCP plugins
        agently_dir = project_dir / ".agently" / "plugins"
        sk_cache_dir = agently_dir / "sk"
        mcp_cache_dir = agently_dir / "mcp"
        
        sk_cache_dir.mkdir(parents=True, exist_ok=True)
        mcp_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Change to the temporary directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Change back to the original directory
        os.chdir(original_dir)


@patch("agently.plugins.sources.GitHubPluginSource._clone_or_update_repo")
@patch("agently.plugins.sources.GitHubPluginSource._get_repo_sha")
@patch("agently.plugins.sources.LocalPluginSource.load")
@patch("agently.plugins.sources.GitHubPluginSource.load")
def test_init_with_mcp_servers(
    mock_github_load, mock_local_load, mock_git_sha, mock_git_clone, temp_mcp_project_dir
):
    """Test the init command with MCP servers in unified plugin format."""
    # Create a proper mock for the plugin class
    class MockPlugin:
        name = "test-plugin"
        namespace = "testuser"
        description = "Test plugin"
        plugin_instructions = "Test instructions"
        
        def __init__(self):
            pass
        
        @classmethod
        def get_kernel_functions(cls):
            return {}
    
    # Set up mocks
    mock_github_load.return_value = MockPlugin
    mock_local_load.return_value = MockPlugin
    mock_git_sha.return_value = "abc123"
    mock_git_clone.return_value = True
    
    # Mock the plugin source get_plugin_info method to avoid serialization issues
    with patch("agently.plugins.sources.GitHubPluginSource._get_plugin_info") as mock_plugin_info, \
         patch("agently.plugins.sources.LocalPluginSource._get_plugin_info") as mock_local_info:
        
        mock_plugin_info.return_value = {
            "namespace": "testuser",
            "name": "test-plugin",
            "full_name": "testuser/test-plugin",
            "version": "main",
            "source_type": "github",
            "plugin_type": "sk",
            "repo_url": "github.com/testuser/test-plugin",
            "sha": "abc123",
            "installed_at": "2023-01-01T00:00:00"
        }
        
        mock_local_info.return_value = {
            "namespace": "local",
            "name": "local-plugin",
            "full_name": "local-plugin",
            "version": "local",
            "source_type": "local",
            "plugin_type": "sk",
            "source_path": str(temp_mcp_project_dir / "plugins" / "local-sk"),
            "sha": "def456",
            "installed_at": "2023-01-01T00:00:00"
        }
        
        # Run the init command
        runner = CliRunner()
        result = runner.invoke(cli, ["init"])
        
        # Print output for debugging
        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.output}")
        print(f"Exception: {result.exception}" if result.exception else "No exception")
        
        # Verify the command executed successfully
        assert result.exit_code == 0
        
        # Check lockfile exists
        lockfile_path = temp_mcp_project_dir / "agently.lockfile.json"
        assert lockfile_path.exists()
        
        # Verify lockfile structure with both SK and MCP plugins
        with open(lockfile_path, "r") as f:
            lockfile = json.load(f)
        
        # Check unified plugin format structure
        assert "plugins" in lockfile


def test_log_level_option():
    """Test that the log level option is available in commands."""
    # Run the CLI help command
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Check for init command
    assert "init" in result.output
    
    # Run the init help command
    result = runner.invoke(cli, ["init", "--help"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Check for log level option
    assert "--log-level" in result.output
    assert "Set the logging level" in result.output


@pytest.fixture
def temp_multi_agent_dir():
    """Create a temporary project directory with multiple agents for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary directory
        project_dir = Path(temp_dir)
        
        # Create agent YAML file with multiple agents
        agent_yaml = project_dir / "agently.yaml"
        with open(agent_yaml, "w") as f:
            f.write("""
version: "1"
agents:
  - id: "agent1"
    name: "Agent One"
    description: "First test agent"
    system_prompt: "You are test agent one."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.7
    plugins:
      local:
        - source: "./plugins/test1"
          variables:
            agent_name: "Agent One"
  
  - id: "agent2"
    name: "Agent Two"
    description: "Second test agent"
    system_prompt: "You are test agent two."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.5
    plugins:
      local:
        - source: "./plugins/test2"
          variables:
            agent_name: "Agent Two"
""")
        
        # Create a copy with .yml extension to test auto-detection
        agent_yml = project_dir / "custom.yml"
        with open(agent_yml, "w") as f:
            f.write("""
version: "1"
agents:
  - id: "custom1"
    name: "Custom Agent"
    description: "Custom config agent"
    system_prompt: "You are a custom agent."
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.7
    plugins:
      local:
        - source: "./plugins/test1"
          variables:
            agent_name: "Custom Agent"
""")
        
        # Create plugins directories and files
        for agent_id in ["test1", "test2"]:
            plugins_dir = project_dir / "plugins" / agent_id
            plugins_dir.mkdir(parents=True, exist_ok=True)
            
            # Create plugin file
            plugin_file = plugins_dir / "__init__.py"
            with open(plugin_file, "w") as f:
                f.write(f"""
from agently.plugins.base import Plugin

class Test{agent_id.capitalize()}Plugin(Plugin):
    name = "{agent_id}"
    description = "A test plugin for {agent_id}"
    plugin_instructions = "This is a test plugin for {agent_id}."
    
    def get_kernel_functions(self):
        return {{"test_function": lambda x: f"Test function for {agent_id} called with {{x}}"}}
""")
        
        # Create lockfile with multi-agent structure
        lockfile = project_dir / "agently.lockfile.json"
        with open(lockfile, "w") as f:
            json.dump({
                "agents": {
                    "agent1": {
                        "name": "Agent One",
                        "plugins": {
                            "sk": {
                                "local/test1": {
                                    "namespace": "local",
                                    "name": "test1",
                                    "full_name": "test1",
                                    "version": "local",
                                    "source_type": "local",
                                    "plugin_type": "sk",
                                    "source_path": str(project_dir / "plugins" / "test1"),
                                    "sha": "test-sha-1",
                                    "installed_at": "2023-01-01T00:00:00",
                                    "variables": {
                                        "agent_name": "Agent One"
                                    }
                                }
                            },
                            "mcp": {}
                        }
                    },
                    "agent2": {
                        "name": "Agent Two",
                        "plugins": {
                            "sk": {
                                "local/test2": {
                                    "namespace": "local",
                                    "name": "test2",
                                    "full_name": "test2",
                                    "version": "local",
                                    "source_type": "local",
                                    "plugin_type": "sk",
                                    "source_path": str(project_dir / "plugins" / "test2"),
                                    "sha": "test-sha-2",
                                    "installed_at": "2023-01-01T00:00:00",
                                    "variables": {
                                        "agent_name": "Agent Two"
                                    }
                                }
                            },
                            "mcp": {}
                        }
                    }
                },
                "plugins": {
                    "sk": {
                        "local/test1": {
                            "namespace": "local",
                            "name": "test1",
                            "full_name": "test1",
                            "version": "local",
                            "source_type": "local",
                            "plugin_type": "sk",
                            "source_path": str(project_dir / "plugins" / "test1"),
                            "sha": "test-sha-1",
                            "installed_at": "2023-01-01T00:00:00"
                        },
                        "local/test2": {
                            "namespace": "local",
                            "name": "test2",
                            "full_name": "test2",
                            "version": "local",
                            "source_type": "local",
                            "plugin_type": "sk",
                            "source_path": str(project_dir / "plugins" / "test2"),
                            "sha": "test-sha-2",
                            "installed_at": "2023-01-01T00:00:00"
                        }
                    },
                    "mcp": {}
                }
            }, f)
        
        # Change to the temporary directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Change back to the original directory
        os.chdir(original_dir)


def test_list_specific_agent(temp_multi_agent_dir):
    """Test the list agents command with a specific agent ID."""
    # Run the list agents command with a specific agent ID
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "agents", "agent1"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output contains detailed agent information
    assert "Agent: Agent One (agent1)" in result.output
    assert "Description: First test agent" in result.output
    assert "Model: openai gpt-4o" in result.output
    
    # Check for plugin info
    assert "Plugins:" in result.output
    assert "./plugins/test1" in result.output


def test_init_specific_agent(temp_multi_agent_dir):
    """Test the init command with a specific agent ID."""
    # Run the init command with a specific agent ID
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "agent2"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output mentions the specific agent
    assert "Agent Two" in result.output or "agent2" in result.output
    
    # Check that the initialization was successful
    assert "Agently has been successfully initialized" in result.output


def test_run_specific_agent(temp_multi_agent_dir):
    """Test the run command with a specific agent ID."""
    # Set up environment with a mock API key
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "test-key-123"
    
    # Mock the interactive_loop function to avoid actual execution
    with patch("agently.cli.commands.interactive_loop") as mock_loop:
        # Run the run command with a specific agent ID
        runner = CliRunner(env=env)
        result = runner.invoke(cli, ["run", "agent2", "--force"])
        
        # Check that the command executed successfully
        assert result.exit_code == 0
        
        # Verify that interactive_loop was called
        mock_loop.assert_called_once()
        
        # Verify the correct agent config was loaded
        agent_config = mock_loop.call_args[0][0]
        assert agent_config.name == "Agent Two"
        assert agent_config.id == "agent2"


def test_custom_config_file_path(temp_multi_agent_dir):
    """Test using a custom config file path with --file option."""
    # Set up environment with a mock API key
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "test-key-123"
    
    # Test list command with custom config file
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["list", "agents", "--file", "custom.yml"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output contains the agent from the custom config
    assert "Custom Agent" in result.output
    
    # Test init command with custom config file
    with patch("agently.cli.commands._initialize_plugins") as mock_init:
        mock_init.return_value = {"added": 0, "updated": 0, "unchanged": 1, "removed": 0, "failed": 0}
        
        result = runner.invoke(cli, ["init", "--file", "custom.yml"])
        
        # Check that the command executed successfully
        assert result.exit_code == 0
        
        # Verify _initialize_plugins was called with the correct file
        args, _ = mock_init.call_args
        assert str(args[0]).endswith("custom.yml")
    
    # Test run command with custom config file
    with patch("agently.cli.commands.interactive_loop") as mock_loop:
        result = runner.invoke(cli, ["run", "--file", "custom.yml", "--force"])
        
        # Check that the command executed successfully
        assert result.exit_code == 0
        
        # Verify that interactive_loop was called
        mock_loop.assert_called_once()
        
        # Verify the correct agent config was loaded
        agent_config = mock_loop.call_args[0][0]
        assert agent_config.name == "Custom Agent"
        assert agent_config.id == "custom1"


def test_file_auto_detection(temp_multi_agent_dir):
    """Test automatic detection of config files with different extensions."""
    # Rename the default config file to test auto-detection
    os.rename("agently.yaml", "agently.yaml.bak")
    
    # Create a .yml file that should be auto-detected
    with open("agently.yml", "w") as f:
        f.write("""
version: "1"
name: "Auto Detected Agent"
description: "Agent from auto-detected .yml file"
system_prompt: "You are an auto-detected agent."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
""")
    
    # Test list agents command without specifying file path
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "agents"])
    
    # Check that the command executed successfully
    assert result.exit_code == 0
    
    # Verify it found the .yml file
    assert "Auto Detected Agent" in result.output 