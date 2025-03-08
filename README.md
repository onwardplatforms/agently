# Agently - Declarative AI Agent Framework

Agently is a Python framework for building, configuring, and running AI agents in a declarative way. Define your agents using YAML configurations and bring them to life with minimal code.

## Features

- **Declarative Configurations**: Define agents with YAML files
- **Plugin System**: Extend agent capabilities with plugins
- **Environment Variable Integration**: Securely handle API keys and configuration
- **Multiple Model Providers**: Support for OpenAI, Ollama, and more
- **Flexible Execution**: CLI, Python API, or interactive mode

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

- [Hello World](examples/hello_world/): A simple agent with plugin variables
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
     # Add any plugins your agent needs
     my-plugin:
       source:
         type: "github"
         repo: "username/repo"
         path: "plugins/my-plugin"
   
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

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.
