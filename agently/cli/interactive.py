"""Interactive agent loop for CLI interaction."""

import asyncio
import logging

import click

from agently.agents.agent import Agent
from agently.config.types import AgentConfig
from agently.conversation.context import ConversationContext, Message
from agently.utils import (
    blue,
    bold,
    get_formatted_output,
    gray,
    green,
    reset_function_state,
)

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

    # Welcome message with minimal but informative details
    click.echo(
        f"\nThe agent {bold(green(agent_config.name))} has been initialized using {blue(provider)} {blue(model_name)}"
    )
    if agent_config.description:
        click.echo(f"{agent_config.description}")

    click.echo(f"\n{gray('Type a message to begin. Type exit to quit.')}\n")

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
            reset_function_state()

            # Display the prompt with newline before but not after
            click.echo("\nAssistant> ", nl=False)

            # For storing response chunks for history while displaying them in real-time
            response_chunks = []

            # For real-time function call display
            last_function_output = ""
            has_function_output = False

            async for chunk in agent.process_message(message, context):
                # Store the chunk for history
                if chunk:
                    response_chunks.append(chunk)
                    # Display the chunk immediately
                    click.echo(chunk, nl=False)

                # Check for new function calls in real-time
                current_function_output = get_formatted_output()
                if current_function_output != last_function_output:
                    # Only output the new function calls
                    if not has_function_output:
                        # First function output - add a single newline
                        click.echo("\n", nl=False)
                        has_function_output = True

                    if last_function_output:
                        # If we already had function output, just add the new lines
                        new_lines = current_function_output.split("\n")[len(last_function_output.split("\n")) :]
                        if new_lines:
                            click.echo("\n".join(new_lines), nl=False)
                    else:
                        # First function call
                        click.echo(current_function_output, nl=False)

                    last_function_output = current_function_output

            # Add a newline after the response
            click.echo()

            # If there were function calls, add another newline for cleaner separation
            if has_function_output:
                click.echo()

            response_text = "".join(response_chunks)
            logger.debug(f"Agent response complete: {len(response_text)} chars")

        except KeyboardInterrupt:
            logger.info("User interrupted with Ctrl+C")
            click.echo("\nExiting...")
            break
        except Exception as e:
            logger.exception(f"Error in interactive loop: {e}")
            click.echo(f"\nError: {e}")


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
        click.echo("\nExiting...")
    except Exception as e:
        logger.exception(f"Error in interactive loop: {e}")
        click.echo(f"\nError: {e}")
