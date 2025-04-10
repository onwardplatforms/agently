#!/usr/bin/env python
"""
A simple MCP server implementation for the Hello/Goodbye example.
This script creates a simple MCP server that exposes hello and goodbye functions.

To use this as an MCP server, run it with:
    python hello_goodbye_server.py
"""

import logging
import os
from mcp.server.fastmcp import FastMCP

# Configure logging
log_level_name = os.getenv("LOG_LEVEL", "ERROR")
# Handle the NONE level specially
if log_level_name == "NONE":
    logging_level = logging.ERROR  # Default to ERROR if NONE is specified
else:
    logging_level = getattr(logging, log_level_name)

logging.basicConfig(level=logging_level, format='%(message)s')

# Configure specific loggers to reduce noise
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.ERROR)

# Remove all handlers from the root logger to prevent duplicate messages
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Create a custom logger for our application
logger = logging.getLogger("hello-goodbye-server")
logger.setLevel(logging.INFO)
# Prevent propagation to avoid duplicate logs
logger.propagate = False

# Create a custom formatter for our application logs - no timestamp
formatter = logging.Formatter('%(message)s')

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Function to log tool calls
def log_tool_call(func_name, **kwargs):
    """Log tool calls with consistent formatting."""
    params = []
    for key, value in kwargs.items():
        if isinstance(value, str) and len(value) > 50:
            value = value[:47] + "..."
        params.append(f"- {key}: {value}")
    
    logger.info(f"ƒ(x) calling {func_name} with parameters:\n" + "\n".join(params))

# Initialize the FastMCP server
mcp = FastMCP("hello_goodbye")

@mcp.tool()
async def say_hello(name: str) -> str:
    """
    Say hello to someone.
    
    Args:
        name: The name of the person to greet
        
    Returns:
        A greeting message
    """
    log_tool_call("say_hello", name=name)
    return f"Hello, {name}! Nice to meet you."

@mcp.tool()
async def say_goodbye(name: str, formal: bool = False) -> str:
    """
    Say goodbye to someone.
    
    Args:
        name: The name of the person to say goodbye to
        formal: Whether to use formal language
        
    Returns:
        A farewell message
    """
    log_tool_call("say_goodbye", name=name, formal=formal)
    if formal:
        return f"Farewell, {name}. It was a pleasure to make your acquaintance."
    else:
        return f"Goodbye, {name}! Have a great day!"

if __name__ == "__main__":
    logger.info("Starting Hello-Goodbye MCP server via stdio.")
    mcp.run(transport='stdio') 