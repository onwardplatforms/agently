# Agently - Declarative AI Agent Framework

Agently is a Python framework for building, configuring, and running AI agents in a declarative way. Define your agents using YAML configurations and bring them to life with minimal code.

## Features

- **Declarative Configurations**: Define agents with YAML files
- **Plugin System**: Extend agent capabilities with plugins
- **Environment Variable Integration**: Securely handle API keys and configuration
- **Multiple Model Providers**: Support for OpenAI, Ollama, and more
- **Flexible Execution**: CLI, Python API, or interactive mode

## Quick Start

```bash
# Install the package
pip install agently

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

## Documentation

For full documentation, visit [docs.agently.ai](https://docs.agently.ai).

## Examples

Check out the [examples](examples/) directory for complete working examples:

- [Hello World](examples/hello_world/): A simple agent with plugin variables
- [Multi-Plugin Agent](examples/README.md): An agent using multiple plugin sources

## Development

```bash
# Clone the repository
git clone https://github.com/yourusername/agently.git
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

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
# Test comment
