"""Tests for CLI commands."""

import os
import sys
import tempfile
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
name: "CLI Test Agent"
description: "A test agent for CLI commands"
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
