#!/usr/bin/env python3
"""Test script for continuous reasoning agent."""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import agently
sys.path.append(str(Path(__file__).parent.parent.parent))

from agently.agents.agent import Agent
from agently.config.parser import load_agent_config
from agently.conversation.context import ConversationContext, Message
from agently.utils.logging import LogLevel, configure_logging


async def main():
    """Run the test agent with continuous reasoning."""
    # Set up logging
    configure_logging(level=LogLevel.INFO)

    # Load agent configuration
    config_path = Path(__file__).parent / "agently.yaml"
    config = load_agent_config(config_path)
    
    # Override to ensure continuous reasoning is enabled
    config.continuous_reasoning = True

    # Initialize the agent
    agent = Agent(config)
    await agent.initialize()
    print(f"Agent initialized: {config.name}")

    # Create a conversation context
    context = ConversationContext(conversation_id=f"test-{config.id}")

    # Get user input and process
    user_input = input("Ask a question: ")
    message = Message(content=user_input, role="user")

    # Process the message with continuous reasoning
    print("\nAgent response (with reasoning):")
    async for chunk in agent.process_continuous_reasoning(message, context):
        print(chunk, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    # Run the main function
    asyncio.run(main()) 