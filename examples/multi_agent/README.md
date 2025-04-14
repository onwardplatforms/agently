# Multi-Agent Example

This example demonstrates how to configure and use multiple agents within a single project with the new schema format. The configuration defines five specialized agents:

1. **Research Agent** - Focuses on finding and analyzing information with deep reasoning (uses agently plugin type)
2. **Coding Agent** - Specializes in software development tasks (uses sk plugin type)
3. **Creative Agent** - Excels at creative writing and idea generation (uses agently plugin type)
4. **DevOps Agent** - Handles deployment, infrastructure, and operations
5. **MCP Agent** - Demonstrates MCP plugin configuration (commented out)

## Configuration

The `agently.yaml` file defines multiple agents using the new schema format. Each agent has:

- A unique identifier (`id`)
- Name and description
- Specialized system prompt (optional)
- Model configuration with appropriate parameters
- Features configuration (optional)
- Plugin configuration (flat array of plugins) if needed

```yaml
version: "1"
env:
  OPENAI_API_KEY: ${{ env.OPENAI_API_KEY }}
  
agents:
  - id: "researcher"
    name: "Research Agent"
    description: "Specializes in finding and analyzing information"
    system_prompt: >
      You are a research assistant with expertise in finding and analyzing information.
      Focus on providing comprehensive, accurate information with proper citations.
      When you don't know something, be transparent about the limits of your knowledge.
    model:
      provider: "openai"
      model: "gpt-4o"
      temperature: 0.2
    features:
      deep_reasoning: true
    plugins:
      - source: "local"
        type: "agently"  # Use agently type when variables are needed
        path: "../hello_local/plugins/hello"
        variables:
          default_name: "Researcher"
    
  - id: "coder"
    name: "Coding Agent"
    description: "Specializes in writing and debugging code"
    # ... other configuration
    plugins:
      - source: "local"
        type: "sk"  # Use sk type when no variables are needed
        path: "../coder_agent/plugins/coder"
```

### New Schema Features

The updated schema introduces several improvements:

1. **Flat Plugin Array**: Plugins are now specified as a flat array with clear type designation
   ```yaml
   plugins:
     - source: "local"  # "local" or "github"
       type: "sk"       # "sk", "mcp", or "agently"
       path: "../path/to/plugin"
   ```

2. **Optional System Prompt**: The system prompt is now optional

3. **Features Block**: Allows enabling special capabilities like deep reasoning
   ```yaml
   features:
     deep_reasoning: true  # Enables step-by-step reasoning
   ```

4. **Plugin Type-Specific Fields**: Each plugin type requires specific fields:
   - `sk` plugins: source and path/url (cannot have variables, command, or args)
   - `mcp` plugins: source, path/url, command, and args (cannot have variables)
   - `agently` plugins: source, path/url, and variables (cannot have command or args)

> **Note**: This example demonstrates both the `sk` and `agently` plugin types. The `sk` type is used for plugins without configuration variables, while the `agently` type is used for plugins that need custom variables. The MCP plugin type is shown in the configuration examples but is commented out as it requires additional setup.

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