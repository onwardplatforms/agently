# Multi-Agent Example

This example demonstrates how to configure and use multiple agents within a single project. The configuration defines three specialized agents:

1. **Research Agent** - Focuses on finding and analyzing information
2. **Coding Agent** - Specializes in software development tasks
3. **Creative Agent** - Excels at creative writing and idea generation

## Configuration

The `agently.yaml` file defines multiple agents using the new multi-agent schema. Each agent has:

- A unique identifier (`id`)
- Name and description
- Specialized system prompt
- Model configuration with appropriate parameters
- Plugin configuration

```yaml
version: "1"
agents:
  - id: "researcher"
    name: "Research Agent"
    # ... other configuration
    
  - id: "coder"
    name: "Coding Agent"
    # ... other configuration
    
  - id: "creative"
    name: "Creative Agent"
    # ... other configuration

# Shared environment variables
env:
  OPENAI_API_KEY: ${{ env.OPENAI_API_KEY }}
```

## Running the Example

To use this example, you need to have the Agently CLI installed and configured. Make sure you have set the `OPENAI_API_KEY` environment variable.

### Listing Available Agents

You can list all the configured agents using:

```bash
cd examples/multi_agent
agently list agents
```

To see detailed information about a specific agent:

```bash
agently list agents researcher
```

### Initializing Agents

To initialize all agents and their plugins:

```bash
agently init
```

To initialize a specific agent:

```bash
agently init researcher
```

### Running an Agent

By default, running without specifying an agent ID will start the first agent in the configuration:

```bash
agently run
```

To run a specific agent using its ID:

```bash
agently run coder
```

## Using Custom File Paths

If your configuration file has a different name or location, you can specify it with the `--file` or `-f` option:

```bash
agently run researcher --file custom-config.yaml
```

This works with all commands:

```bash
agently list agents --file custom-config.yaml
agently init --file custom-config.yaml
```

## Next Steps

This example demonstrates the basics of multi-agent configuration. In future versions of Agently, you'll be able to:

1. Run multiple agents simultaneously in a conversation
2. Allow agents to collaborate and share information
3. Define agent relationships and hierarchies

## CLI Command Reference

```
agently version                      # Display version information
agently init [agent_id]              # Initialize all or specific agent
agently run [agent_id]               # Run the first or specific agent
agently list agents [agent_id]       # List all agents or details for specific agent

Options:
  --file, -f                         # Specify config file path
  --log-level                        # Set logging level
``` 