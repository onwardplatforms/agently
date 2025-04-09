# MCP Hello-Goodbye Example

This example demonstrates how to use a [Model Context Protocol (MCP)](https://github.com/sse-model-context-protocol/protocol) server with Agently. It creates an agent that can interact with a simple hello-goodbye MCP server that provides functions to say hello and goodbye.

## What is MCP?

The Model Context Protocol (MCP) is a standard protocol that enables AI models to discover and call external tools. MCP servers provide a way for AI agents to access functionality implemented outside of the model itself. This enables more powerful and flexible AI applications that can interact with external systems and data sources.

## This Example

This example includes:

1. A simple MCP server implementation (`servers/hello_goodbye_server.py`) that provides two functions:
   - `say_hello`: Greets a person with a friendly message
   - `say_goodbye`: Says goodbye to a person (with optional formal style)
   
   The server is implemented using the [FastMCP](https://github.com/pnichols104/mcp) library, which simplifies building MCP-compatible servers.

2. A configuration file (`agently.yaml`) that defines an agent with access to the MCP server

## Requirements

- Python 3.9+
- Agently and its dependencies
- semantic-kernel with MCP support: `pip install semantic-kernel[mcp]`
- FastMCP library: `pip install mcp`
- An OpenAI API key set in your environment variables

## Running the Example

To run the example, use the Agently CLI:

```bash
cd examples/mcp_hello_goodbye
agently init    # Initialize the agent and MCP servers
agently run     # Start the interactive agent
```

This will start an interactive chat session with the agent defined in `agently.yaml`. You can then chat with the agent and ask it to:

1. Say hello to someone: "Can you say hello to Alex?"
2. Say goodbye to someone: "Say goodbye to Jordan."
3. Say a formal goodbye: "Can you say goodbye to Taylor, but make it formal?"

## Understanding How It Works

### MCP Server Implementation

The MCP server (`servers/hello_goodbye_server.py`) follows the MCP protocol to expose functions to AI models using FastMCP:

1. We define the functions as async methods decorated with `@mcp.tool()`
2. FastMCP automatically handles:
   - Function registration and discovery
   - Parameter validation
   - MCP protocol communication
   - Error handling

The server includes logging to help track function calls and their parameters.

### Agent Configuration

The agent configuration (`agently.yaml`) includes:

1. Basic agent settings (ID, name, description, system prompt)
2. Model configuration (provider, model name, temperature)
3. MCP server configuration:
   ```yaml
   mcp_servers:
     local:
       - name: "HelloGoodbye"
         description: "A plugin that can say hello and goodbye to users"
         command: "python"
         args:
           - "${PWD}/servers/hello_goodbye_server.py"
   ```

When the agent is initialized, Agently automatically launches the MCP server as a subprocess and connects to it using the Model Context Protocol.

## Creating Your Own MCP Servers

To create your own MCP server using FastMCP:

1. Import the FastMCP library: `from mcp.server.fastmcp import FastMCP`
2. Create an MCP server: `mcp = FastMCP("server_name")`
3. Define functions with the `@mcp.tool()` decorator
4. Run the server with: `mcp.run(transport='stdio')`

The hello-goodbye server in this example provides a simple template you can adapt for your own use cases.

## Learn More

- [Semantic Kernel MCP Support](https://github.com/microsoft/semantic-kernel/tree/main/python/semantic-kernel/semantic_kernel/connectors/mcp)
- [Model Context Protocol Specification](https://github.com/sse-model-context-protocol/protocol)
- [FastMCP Library](https://github.com/pnichols104/mcp)
- [Agently Documentation](https://docs.agently.ai/) 