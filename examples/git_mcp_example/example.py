#!/usr/bin/env python3
"""
Example script demonstrating how to use Agently with the Git MCP server programmatically.
"""
import os
import subprocess
from agently.agents.agent import Agent

def main():
    """Run the example script."""
    # Check if we're in a git repository
    if not os.path.exists(".git"):
        print("Initializing Git repository...")
        os.system("git init")
    
    # Initialize Agently if needed
    if not os.path.exists(".agently"):
        print("Initializing Agently...")
        subprocess.run(["agently", "init"], check=True)
    
    # Create an agent using the configuration from agently.yaml
    agent = Agent.from_config("agently.yaml")
    
    # Use the agent to interact with the Git repository
    response = agent.process_message(
        "I need to understand this Git repository. First, tell me the current status. "
        "Then, if there are any unstaged files, show me what they are. "
        "If there are unstaged changes to README.md, please stage them and create a "
        "commit with the message 'Update README.md'."
    )
    
    print("\nAgent Response:")
    print(response)

if __name__ == "__main__":
    main() 