# Git MCP Example

This example demonstrates how to use the Model Context Protocol (MCP) Git server with Agently. The MCP Git server provides tools to interact with Git repositories through Large Language Models.

## Setup

1. Ensure you have an OpenAI API key set in your environment:
   ```bash
   export OPENAI_API_KEY=your_api_key_here
   ```

2. **Important**: Update the `agently.yaml` file to point to a valid Git repository on your system:
   ```yaml
   args: ["mcp-server-git", "--repository", "/path/to/valid/git/repository"]
   ```
   Replace `/path/to/valid/git/repository` with an actual Git repository path on your system.

3. Initialize Agently to install the MCP Git server:
   ```bash
   agently init
   ```

## Running the Example

Run the agent with the Git MCP server:

```bash
agently run
```

You can then ask the agent to perform various Git operations like:
- "What is the status of this repository?"
- "Add all files to the staging area"
- "Commit my changes with a message 'Initial commit'"

## Available Git Tools

The MCP Git server provides several tools:

- `git_status` - Show working tree status
- `git_diff_unstaged` - Show unstaged changes
- `git_diff_staged` - Show staged changes
- `git_add` - Add files to staging area
- `git_commit` - Create a commit
- `git_log` - Show commit history
- `git_checkout` - Switch branches
- `git_create_branch` - Create a new branch
- And more...

## How It Works

This example uses the official MCP Git server from the [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers/tree/main/src/git) repository. The `agently.yaml` file configures this as an MCP plugin that can be used with Agently. 