# Hello Remote Example

This example demonstrates how to use Agently with a **remote plugin** from GitHub.

## Overview

This example shows:

1. How to configure an agent to use a remote plugin from GitHub
2. How to pass variables to remote plugins
3. How Agently loads, caches and uses remote plugins

## Setup

First, make sure you have installed Agently:

```bash
pip install agently
```

You'll need an OpenAI API key. You can set it as an environment variable:

```bash
export OPENAI_API_KEY=your-api-key
```

## Installing the Remote Plugin

Before running the agent, you need to install the remote plugin:

```bash
# Navigate to this example directory
cd examples/hello_remote

# Install plugins defined in agently.yaml
agently install
```

This will:
1. Clone the plugin repository to `.agently/plugins/`
2. Record the plugin details in the lockfile

## Running the Agent

To run the agent:

```bash
# Run from this directory
agently run
```

## How it Works

This example uses a remote plugin from `github.com/onwardplatforms/agently-plugin-hello`.

The configuration in `agently.yaml` defines:
- The OpenAI model to use (gpt-4o)
- The remote plugin to use from GitHub
- Variables to pass to the plugin

When you use the `install` command, Agently:
1. Clones the plugin repository to a cache directory
2. Records the commit SHA in the lockfile for reproducibility

When you use the `run` command, Agently:
1. Loads the plugin from the local cache
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
