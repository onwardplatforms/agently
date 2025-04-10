# Agently - Declarative AI Agent Framework

Agently is the batteries included framework for creating AI agents in a declarative way with a simple CLI tool to initialize and run agents. Define your agents using YAML configurations and bring them to life with minimal code.

## Core Design Principles

- **Declarative Configuration**: Define complete agents using simple YAML files
- **Flexible Plugin Ecosystem**: Extend agent capabilities with MCP, Semantic Kernel, and Agently plugins
- **Community Sharing**: Share and reuse plugins across the Agently community
- **Provider Agnostic**: Support for multiple model providers including OpenAI, Ollama, and more
- **Streamlined CLI**: Simple `init` and `run` commands to manage your agent lifecycle

## Installation

### Prerequisites
- Python 3.8 or newer

### Mac

```bash
# Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install from PyPI
pip install agently

# Or install from source
git clone https://github.com/onwardplatforms/agently.git
cd agently
make install
```

### Windows

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate

# Install from PyPI
pip install agently

# Or install from source
git clone https://github.com/onwardplatforms/agently.git
cd agently
python -m pip install -r requirements.txt
python -m pip install -e .
```

### Environment Setup

Copy the example environment file and update with your API keys:

```bash
# Mac/Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Edit the `.env` file to include your API keys:
```
OPENAI_API_KEY=your_key_here
# Other API keys as needed
```

## Quick Start

```bash
# Create a simple agent configuration (agently.yaml)
cat > agently.yaml << EOF
version: "1"
name: "Hello Agent"
description: "A simple greeting agent"
system_prompt: "You are a friendly assistant that helps with greetings."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
env:
  OPENAI_API_KEY: ${{ env.OPENAI_API_KEY }}
EOF

# Run the agent
agently run
```

## Plugin System

Agently features a unified plugin system that makes it easy to extend your agent's capabilities through various plugin types.

### Supported Plugin Types

#### Semantic Kernel (SK) Plugins

Standard plugins that provide function-based capabilities to your agent:

```yaml
plugins:
  github:
    - source: "username/plugin-name"  # Will use agently-plugin- prefix
      version: "main"
      variables:
        key: "value"
  local:
    - source: "./plugins/my-local-plugin"
      variables:
        key: "value"
```

#### Multi-Command Protocol (MCP) Servers

External servers that enable complex, stateful interactions:

```yaml
plugins:
  github:
    - source: "username/mcp-server-name"
      type: "mcp"  # Identifies this as an MCP server
      version: "main"
      command: "python"  # How to start the server
      args: ["server.py"]
  local:
    - source: "./mcp-servers/my-local-server"
      type: "mcp"
      command: "python"
      args: ["server.py"]
```

### Developing Plugins

#### Using the Agently SDK

For easier plugin development, we recommend using the [Agently SDK](https://github.com/onwardplatforms/agently-sdk), which provides base classes and utilities for creating plugins:

```python
from agently_sdk.plugins import Plugin, PluginVariable, agently_function

class MyPlugin(Plugin):
    name = "my_plugin"
    description = "A useful description of what this plugin does"
    
    # Define configurable variables for your plugin
    api_key = PluginVariable(
        description="API key for the service",
        sensitive=True  # Marks as sensitive info
    )
    
    max_results = PluginVariable(
        description="Maximum number of results to return",
        default=10,
        type=int
    )
    
    @agently_function
    def my_function(self, param1: str, param2: int = 5) -> str:
        """Function description that will be used by the agent.
        
        Args:
            param1: First parameter description
            param2: Second parameter description
            
        Returns:
            Description of the return value
        """
        # Implementation using plugin variables
        return f"Processed {param1} with {self.max_results} results"
```

#### Plugin Variables

Plugins can define variables that:
- Allow for runtime configuration
- Can have default values, validation rules, and type constraints
- Are set via the `variables` section in the agent config

### Plugin Installation & Management

Plugins are managed using a structured workflow similar to Terraform:

```bash
# Initialize and install all plugins defined in your config
agently init

# List all installed plugins
agently list

# Run your agent with the installed plugins
agently run
```

### Plugin Storage

Plugins are stored in the `.agently/plugins` directory, organized by type:
- SK plugins: `.agently/plugins/sk/`
- MCP servers: `.agently/plugins/mcp/`

For more advanced usage and detailed documentation, check out the [full plugin documentation](https://docs.agently.run/plugins).

### Plugin Naming Conventions

When creating plugins to share with the community, follow these naming conventions for GitHub repositories:

- **Semantic Kernel Plugins**: Use the prefix `agently-plugin-`
  - Example: `agently-plugin-weather` for a weather plugin

- **MCP Servers**: Use the prefix `agently-mcp-`
  - Example: `agently-mcp-database` for a database MCP server

These conventions help with discoverability and make it clear what type of plugin a repository contains.

## Coder Agent Quick Start

The Coder Agent is a powerful AI coding assistant with Git-backed code editing capabilities:

```bash
# Install in development mode
pip install -e .

# Navigate to the coder agent example
cd examples/coder_agent

# Run the coder agent
agently run
```

With the Coder Agent, you can:
- Create and modify files
- Search across codebases
- Find references to symbols
- Format and lint code
- Track changes with Git-based version control

Example interactions:
```
> create a fibonacci.py file
> add types and Google style docstrings
> search for all references to a function
```

For more details, see the [Coder Agent documentation](examples/coder_agent/README.md).

## CLI Commands

Agently provides a convenient command-line interface for managing and interacting with your agents:

### `agently run`

Run an agent using its configuration file.

```bash
# Basic usage with default configuration file (agently.yaml)
agently run

# Specify a different configuration file
agently run --agent path/to/config.yaml

# Set log level
agently run --log-level info
```

Options:
- `--agent, -a`: Path to agent configuration file (default: "agently.yaml")
- `--log-level`: Set the logging level (options: none, debug, info, warning, error, critical)

### `agently init`

Initialize the agent and install required plugins based on configuration.

```bash
# Initialize using default configuration
agently init

# Force reinstallation of all plugins
agently init --force

# Suppress verbose output
agently init --quiet
```

Options:
- `--agent, -a`: Path to agent configuration file (default: "agently.yaml")
- `--force`: Force reinstallation of all plugins
- `--quiet`: Reduce output verbosity
- `--log-level`: Set the logging level

### `agently list`

List available plugins or configurations.

```bash
# List all installed plugins
agently list
```

## Documentation

For full documentation, visit [docs.agently.run](https://docs.agently.run).

## Examples

Check out the [examples](examples/) directory for complete working examples:

- [Coder Agent](examples/coder_agent/README.md): A powerful AI coding assistant with Git-backed changes
- [Multi-Plugin Agent](examples/README.md): An agent using multiple plugin sources

## Development

### Mac

```bash
# Clone the repository
git clone https://github.com/onwardplatforms/agently.git
cd agently

# Set up development environment
make install-dev

# Run tests
make test

# Format code
make format

# Run linters
make lint
```

### Windows

```bash
# Clone the repository
git clone https://github.com/onwardplatforms/agently.git
cd agently

# Set up development environment
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pre-commit install

# Run tests
python -m pytest tests/ -v --cov=. --cov-report=term-missing

# Format code
python -m black agently
python -m isort agently

# Run linters
python -m flake8 agently
```

## Creating Your Own Agent

1. **Create a configuration file**

   Create an `agently.yaml` file with your agent's configuration:

   ```yaml
   version: "1"
   name: "My Custom Agent"
   description: "An agent that performs specific tasks"
   system_prompt: |
     You are a specialized assistant that helps with [YOUR SPECIFIC TASK].
     Please provide helpful, accurate, and concise responses.
   
   model:
     provider: "openai"
     model: "gpt-4o"  # or another model of your choice
     temperature: 0.7
   
   plugins:
     github:
       - source: "username/plugin-name"
         version: "main"
         variables:
           api_key: ${{ env.SERVICE_API_KEY }}
     local:
       - source: "./plugins/my-local-plugin"
         variables:
           max_results: 20
   
   env:
     OPENAI_API_KEY: ${{ env.OPENAI_API_KEY }}
     # Add other environment variables as needed
   ```

2. **Initialize your agent**

   ```bash
   agently init
   ```

3. **Run your agent**

   ```bash
   agently run
   ```

## Troubleshooting

### Mac
- If you encounter permission issues: `sudo pip install agently`
- For M1/M2/M3 Macs, you may need to install Rosetta 2: `softwareupdate --install-rosetta`

### Windows
- If you see "Command not found" errors, ensure Python is in your PATH or use `python -m` prefix (e.g., `python -m pip`)
- If you get DLL load errors, try installing the [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

## License

MIT

## Contributing

Contributions are welcome! Here's how you can contribute to Agently:

### Code Contributions

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Submit a pull request

### Creating Plugins

1. Use the [Agently SDK](https://github.com/onwardplatforms/agently-sdk) for developing plugins
2. Follow the naming conventions for GitHub repositories
3. Add comprehensive documentation in your plugin's README
4. Include example usage in your plugin's documentation

### Documentation

Help improve our documentation by submitting PRs for:
- Fixes for unclear instructions
- Additional examples of using Agently
- Tutorials for specific use cases

### Bug Reports

Found a bug? Please open an issue with:
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)

For more details, see [CONTRIBUTING.md](CONTRIBUTING.md).
