# Hello Local Example

This example demonstrates how to use Agently with a **local plugin** from the filesystem.

## Overview

This example shows:

1. How to configure an agent to use a local plugin from a directory
2. How to pass variables to local plugins
3. How Agently loads and uses local plugins

## Structure

- `agently.yaml` - The agent configuration file specifying the model, system prompt, and plugin with variables
- `plugins/hello/__init__.py` - A simple plugin that demonstrates the use of plugin variables

## Setup

First, make sure you have installed Agently:

```bash
pip install agently
```

You'll need an OpenAI API key. You can set it as an environment variable:

```bash
export OPENAI_API_KEY=your-api-key
```

## Running the Agent

To run the agent:

```bash
# Navigate to this example directory
cd examples/hello_local

# Run the agent
agently run
```

## How it Works

This example uses a local plugin from the `plugins/hello` directory.

The configuration in `agently.yaml` defines:
- The OpenAI model to use (gpt-4o)
- The local plugin to use from the filesystem
- Variables to pass to the plugin (default_name: "Friend")

When you use the `run` command, Agently:
1. Loads the plugin from the local directory
2. Initializes it with the provided variables
3. Makes the plugin functions available to the agent

## What to Try

Once the agent is running, you can try:

- `Greet me` (The agent will use the plugin to greet you)
- `Greet Sarah` (The agent will greet a specific person)
- `Say goodbye to John` (The agent will use the farewell function)
- `What time is it?` (The agent will generate a time-based greeting)
- `Remember my name is Alex` (The agent will remember your name)
- `Greet me again` (The agent should use your remembered name)

## The Plugin

The HelloPlugin demonstrates:
- Defining a plugin with a descriptive name and instructions
- Using plugin variables with defaults (`default_name`)
- A simple greeting function that uses the variable

## Running the Example

Run the agent with the CLI:

```bash
# From this directory
python -m cli.commands run --agent agently.yaml
```

Or simply:

```bash
# From this directory
agently run
```

Test just the plugin:

```bash
# From this directory
python test_plugin.py
```

## Testing the default_name Variable

To test that the plugin variables are working correctly, try these interactions:

1. For a generic greeting using the default name:
   ```
   You> greet me
   Assistant> Hello, Friend!
   ```

2. For greeting a specific person:
   ```
   You> greet Alice
   Assistant> Hello, Alice!
   ```

3. Explicitly verify the default_name variable:
   ```
   You> use the greet function with default variables
   Assistant> Hello, Friend!
   ```

These interactions confirm that the plugin is correctly using the `default_name` variable set to "Friend" in the YAML configuration.

## Customizing

You can customize the `default_name` variable by changing it in the `agently.yaml` file:

```yaml
plugins:
  local:
    - path: "./plugins/hello"
      variables:
        default_name: "Your Custom Default Name"
```
