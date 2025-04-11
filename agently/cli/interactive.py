"""Interactive agent loop for CLI interaction."""

import asyncio
import logging

import click
from agently_sdk import styles  # Import styles directly from SDK

from agently.agents.agent import Agent
from agently.config.types import AgentConfig
from agently.conversation.context import ConversationContext, Message

logger = logging.getLogger(__name__)


# Create a simplified output manager for interactive mode
class OutputManager:
    """Minimal output manager for CLI interaction."""

    def __init__(self):
        """Initialize the output manager."""
        self.context_stack = []
        self.last_output_type = None

    def echo(self, message, nl=True):
        """Echo a message."""
        click.echo(message, nl=nl)

    def info(self, message, nl=True):
        """Show an info message."""
        click.echo(styles.info(message), nl=nl)

    def muted(self, message, nl=True):
        """Show a muted message."""
        click.echo(styles.dim(message), nl=nl)

    def stream(self, chunk: str):
        """Stream a chunk of text to the output."""
        if chunk:
            click.echo(chunk, nl=False)

    # Context manager-related methods
    def enter_context(self, context_name):
        """Enter a named context."""
        self.context_stack.append(context_name)
        return self

    def exit_context(self):
        """Exit the current context."""
        if self.context_stack:
            self.context_stack.pop()

    def reset_function_state(self):
        """Reset function call tracking state."""
        self.last_output_type = None

    # Context manager protocol
    def __enter__(self):
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager."""
        self.exit_context()


# Create a singleton instance
cli = OutputManager()


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
        cli.echo(f"\nThe agent {agent_config.name} has been initialized using {provider} {model_name}")
        if agent_config.description:
            cli.echo(agent_config.description)

        cli.muted("\nType a message to begin. Type exit to quit.\n")

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
                cli.echo("\nAssistant> ", nl=False)

                # For storing response chunks for history
                response_chunks = []

                async for chunk in agent.process_message(message, context):
                    # Store the chunk for history
                    if chunk:
                        response_chunks.append(chunk)
                        # Display the chunk immediately using the output manager
                        cli.stream(chunk)

                # Add a newline after the response
                cli.echo("")

                response_text = "".join(response_chunks)
                logger.debug(f"Agent response complete: {len(response_text)} chars")

            except KeyboardInterrupt:
                logger.info("User interrupted with Ctrl+C")
                cli.echo("\nExiting...")
                break
            except Exception as e:
                logger.exception(f"Error in interactive loop: {e}")
                cli.echo(f"\nError: {e}")


def interactive_loop(agent_config: AgentConfig):
    """Run the interactive agent loop (sync wrapper).

    Args:
        agent_config: Agent configuration
    """
    try:
        logger.info("Starting interactive loop")

        # Get or create event loop more safely
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create a new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run the interactive loop
        loop.run_until_complete(_run_interactive_loop(agent_config))
        logger.info("Interactive loop completed")
    except KeyboardInterrupt:
        logger.info("Interactive loop interrupted")
        cli.echo("\nExiting...")
    except Exception as e:
        logger.exception(f"Error in interactive loop: {e}")
        cli.echo(f"\nError: {e}")
