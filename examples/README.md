# Agent Foundry Examples

This directory contains examples for using the Agent Foundry runtime.

## Directory Structure

- **hello_local/** - A simple example demonstrating the YAML-based agent configuration with local plugins
  - `agently.yaml` - The agent configuration file
  - `plugins/hello/__init__.py` - A simple plugin that demonstrates plugin functionality
- **hello_remote/** - An example demonstrating the use of remote plugins from GitHub

## Running Examples

To run the hello_local example:

```bash
# From the root directory
cd examples/hello_local
agently run
```

For examples using remote plugins, you may want to initialize the plugins first:

```bash
# From the root directory
cd examples/hello_remote
agently init
agently run
```

Or just run the agent directly, which will automatically initialize plugins:

```bash
# From the root directory
cd examples/hello_remote
agently run
```

## Creating Your Own Agent

To create your own agent:

1. Create a directory for your agent
2. Create an `agently.yaml` file with your agent configuration
3. Create or reference plugins for your agent to use
4. Run your agent with the CLI command: `agently run`

## YAML Configuration Example

Here's an example of a more complex agent configuration using both local and GitHub plugins:

```yaml
version: "1"
name: "Multi-Plugin Agent"
description: "An agent that uses multiple plugins from different sources"
system_prompt: "You are a helpful assistant with access to several tools."
model:
  provider: "openai"
  model: "gpt-4o"
  temperature: 0.7
plugins:
  local:
    - source: "./plugins/hello"
      variables:
        default_name: "Friend"
    - source: "./plugins/calculator"
      variables:
        precision: 2
  github:
    - source: "example/weather-plugin"
      version: "v1.0.0"
      plugin_path: "plugins/weather"
      variables:
        api_key: "${{ env.WEATHER_API_KEY }}"
        units: "metric"
env:
  OPENAI_API_KEY: ${{ env.OPENAI_API_KEY }}
  WEATHER_API_KEY: ${{ env.WEATHER_API_KEY }}
```

This structure makes it easy to organize plugins by their source type while still allowing multiple plugins of each type.
