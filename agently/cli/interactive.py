"""Interactive agent loop for CLI interaction."""

import asyncio
import logging

import click

from agently.agents.agent import Agent
from agently.cli.output import cli, echo, info, muted
from agently.config.types import AgentConfig
from agently.conversation.context import ConversationContext, Message

logger = logging.getLogger(__name__)


async def _run_interactive_loop(agent_config: AgentConfig):
    """Run the interactive agent loop.

    Args:
        agent_config: Agent configuration
    """
    # Initialize agent
    logger.info(f"Initializing agent: {agent_config.name}")
    agent = Agent(agent_config)
    await agent.initialize()
    logger.info("Agent initialized successfully")

    # Create conversation context
    context = ConversationContext(conversation_id=f"cli-{agent_config.id}")
    logger.debug(f"Created conversation context with ID: {context.id}")

    # Construct a simplified welcome message
    provider = agent_config.model.provider if hasattr(agent_config.model, "provider") else "unknown"
    model_name = agent_config.model.model if hasattr(agent_config.model, "model") else str(agent_config.model)

    # Enter interactive context for proper streaming
    with cli.enter_context("interactive"):
        # Welcome message with minimal but informative details
        echo(f"\nThe agent {agent_config.name} has been initialized using {provider} {model_name}")
        if agent_config.description:
            echo(f"{agent_config.description}")

        muted(f"\nType a message to begin. Type exit to quit.\n")

        # Main loop
        while True:
            try:
                # Get user input
                user_input = click.prompt("You", prompt_suffix="> ")
                logger.debug(f"User input: {user_input}")

                # Check for exit
                if user_input.lower() in ["exit", "quit"]:
                    logger.info("User requested exit")
                    break

                # Process message
                logger.info(f"Processing user message: {user_input[:50]}...")
                message = Message(content=user_input, role="user")

                # Reset the function state before processing the message
                cli.reset_function_state()

                # Display the prompt with newline before but not after
                echo("\nAssistant> ", nl=False)

                # For storing response chunks for history
                response_chunks = []

                async for chunk in agent.process_message(message, context):
                    # Store the chunk for history
                    if chunk:
                        response_chunks.append(chunk)
                        # Display the chunk immediately using the output manager
                        cli.stream(chunk)

                # Add a newline after the response
                echo("")

                response_text = "".join(response_chunks)
                logger.debug(f"Agent response complete: {len(response_text)} chars")

            except KeyboardInterrupt:
                logger.info("User interrupted with Ctrl+C")
                echo("\nExiting...")
                break
            except Exception as e:
                logger.exception(f"Error in interactive loop: {e}")
                echo(f"\nError: {e}")


def interactive_loop(agent_config: AgentConfig):
    """Run the interactive agent loop (sync wrapper).

    Args:
        agent_config: Agent configuration
    """
    try:
        logger.info("Starting interactive loop")
        asyncio.run(_run_interactive_loop(agent_config))
        logger.info("Interactive loop completed")
    except KeyboardInterrupt:
        logger.info("Interactive loop interrupted")
        echo("\nExiting...")
    except Exception as e:
        logger.exception(f"Error in interactive loop: {e}")
        echo(f"\nError: {e}")
