"""Agent implementation for the Agently framework.

This module provides the core Agent class that manages individual agent behavior,
including initialization, plugin management, and message processing.
"""

import inspect
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from semantic_kernel import Kernel
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.exceptions.content_exceptions import ContentAdditionException

from agently.agents.prompts import CONTINUOUS_REASONING_PROMPT, DEFAULT_PROMPT
from agently.agents.reasoning import ReasoningChain
from agently.config.types import AgentConfig
from agently.conversation.context import ConversationContext, Message
from agently.core import get_error_handler
from agently.errors import AgentError, ErrorContext, RetryConfig, RetryHandler
from agently.models.base import ModelProvider

logger = logging.getLogger(__name__)


class Agent:
    """Core agent class that manages individual agent behavior."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.id = config.id
        self.name = config.name

        # Configure logging based on agent configuration
        # This will only affect loggers used by this agent instance
        agent_logger = logging.getLogger(f"agent.{self.id}")
        agent_logger.setLevel(config.log_level)
        logger.debug(f"Agent logger configured with level: {config.log_level}")

        self.kernel = Kernel()
        self.provider: Optional[ModelProvider] = None
        self.error_handler = get_error_handler()
        self.retry_handler: RetryHandler[Any, Any] = RetryHandler(
            RetryConfig(max_attempts=2, initial_delay=0.5, max_delay=5.0)
        )
        logger.info(f"Agent initialized with config: id={self.id}, name={self.name}")

    async def _handle_agent_operation(self, operation_name: str, **context_details) -> ErrorContext:
        """Create error context for agent operations."""
        return ErrorContext(
            component="agent",
            operation=operation_name,
            details={"agent_id": self.id, "agent_name": self.name, **context_details},
        )

    def _create_agent_error(
        self,
        message: str,
        context: ErrorContext,
        cause: Exception = None,
        recovery_hint: Optional[str] = None,
    ) -> AgentError:
        """Create a standardized agent error."""
        return AgentError(
            message=message,
            context=context,
            recovery_hint=recovery_hint or "Check agent configuration and try again",
            cause=cause,
        )

    async def initialize(self) -> None:
        """Initialize the agent with the configured model provider and plugins."""
        try:
            context = await self._handle_agent_operation("initialize")
            logger.debug("Initializing agent with context: %s", context)

            # Create a new kernel
            from semantic_kernel import Kernel

            self.kernel = Kernel()
            logger.debug("Created new kernel")

            # Initialize the model provider
            provider_type = self.config.model.provider.lower()
            logger.debug("Initializing model provider: %s", provider_type)

            if provider_type == "openai":
                from ..models.openai import OpenAIProvider

                self.provider = OpenAIProvider(self.config.model)
                # Register the provider with the kernel
                if self.provider.client:
                    self.kernel.add_service(self.provider.client)
                logger.info(f"OpenAI provider initialized with model: {self.config.model.model}")
            elif provider_type == "ollama":
                from ..models.ollama import OllamaProvider

                self.provider = OllamaProvider(self.config.model)
                # Register the provider with the kernel
                if self.provider.client:
                    self.kernel.add_service(self.provider.client)
                # Register the kernel with the provider for function calling
                if hasattr(self.provider, "register_kernel"):
                    self.provider.register_kernel(self.kernel)
                logger.info(f"Ollama provider initialized with model: {self.config.model.model}")
            else:
                raise ValueError(f"Unsupported provider type: {provider_type}")
            logger.debug("Model provider initialized: %s", self.provider)

            # Initialize plugins
            await self._init_plugins()
            logger.debug("Plugins initialized")

            # Initialize MCP servers
            await self._init_mcp_servers()
            logger.debug("MCP servers initialized")

        except Exception as e:
            logger.error("Error initializing agent", extra={"error": str(e)}, exc_info=e)
            raise self._create_agent_error(
                message="Failed to initialize agent",
                context=context,
                cause=e,
                recovery_hint="Check configuration and model availability",
            ) from e

    # TODO: See about consolidating this with _init_mcp_servers
    async def _init_plugins(self) -> None:
        """Initialize agent plugins."""
        try:
            context = await self._handle_agent_operation("init_plugins")
            logger.debug("Initializing plugins with context: %s", context)

            # Initialize plugin manager
            from ..plugins import PluginManager

            self.plugin_manager = PluginManager()
            logger.debug("Plugin manager created")

            # Load configured plugins
            logger.info(f"Loading {len(self.config.plugins)} plugins")
            for i, plugin_config in enumerate(self.config.plugins):
                logger.debug(f"Loading plugin {i+1}/{len(self.config.plugins)} with config: {plugin_config}")
                try:
                    logger.debug(f"Plugin source: {plugin_config.source}")
                    logger.debug(f"Plugin variables: {plugin_config.variables}")
                    plugin_instance = await self.plugin_manager.load_plugin(
                        plugin_config.source, plugin_config.variables or {}
                    )

                    # Log plugin details
                    logger.info(f"Plugin loaded: name={plugin_instance.name}, class={plugin_instance.__class__.__name__}")
                    logger.debug(f"Plugin description: {plugin_instance.description}")
                    logger.debug(f"Plugin instructions: {plugin_instance.plugin_instructions}")

                    # Register plugin with the kernel
                    logger.debug(f"Registering plugin {plugin_instance.name} with kernel")
                    self.kernel.add_plugin(plugin_instance, plugin_instance.name)
                    logger.info(f"Plugin {plugin_instance.name} registered with kernel")

                    # Log available functions
                    kernel_functions = plugin_instance.__class__.get_kernel_functions()
                    logger.debug(
                        f"Plugin {plugin_instance.name} has {len(kernel_functions)} kernel functions: "
                        f"{list(kernel_functions.keys())}"
                    )
                except Exception as e:
                    logger.error(f"Error loading plugin: {e}", exc_info=e)
                    raise

                logger.debug(f"Plugin {i+1}/{len(self.config.plugins)} loaded and registered successfully")

            # Add chat function to kernel
            logger.debug("Adding chat function to kernel")
            self.kernel.add_function(
                prompt="{{$chat_history}}{{$user_input}}",
                plugin_name="ChatBot",
                function_name="Chat",
            )
            logger.debug("Added chat function to kernel")

            # Log all registered plugins in kernel at debug level only
            logger.debug(f"Kernel plugins: {self.kernel.plugins}")

        except Exception as e:
            logger.error("Failed to initialize plugins", exc_info=e)
            raise self._create_agent_error(
                message="Failed to initialize plugins",
                context=context,
                cause=e,
                recovery_hint="Check plugin configuration",
            ) from e

    async def _init_mcp_servers(self) -> None:
        """Initialize MCP servers for the agent."""
        try:
            context = await self._handle_agent_operation("init_mcp_servers")
            logger.debug("Initializing MCP servers with context: %s", context)

            if not self.config.mcp_servers:
                logger.info("No MCP servers configured, skipping initialization")
                return

            # Import MCP server classes from semantic_kernel
            try:
                from semantic_kernel.connectors.mcp import MCPSsePlugin, MCPStdioPlugin

                logger.debug("Successfully imported MCP server classes")
            except ImportError as e:
                logger.error(f"Failed to import MCP server classes: {e}")
                raise ImportError("Failed to import MCP server classes. Make sure semantic-kernel[mcp] is installed.") from e

            # Track open MCP server connections
            self.mcp_server_connections = []

            # Initialize each MCP server
            logger.info(f"Loading {len(self.config.mcp_servers)} MCP servers")
            for i, mcp_config in enumerate(self.config.mcp_servers):
                logger.debug(f"Loading MCP server {i+1}/{len(self.config.mcp_servers)}: {mcp_config.name}")

                try:
                    # Initialize an MCP server based on type
                    mcp_server_instance: Any = None
                    if hasattr(mcp_config, "url"):
                        # This is a URL-based MCP server
                        logger.debug(f"Initializing URL-based MCP server with URL: {mcp_config.url}")
                        mcp_server_instance = MCPSsePlugin(
                            name=mcp_config.name,
                            description=mcp_config.description,
                            url=mcp_config.url,
                        )
                    else:
                        # This is a stdio-based MCP server
                        logger.debug(f"Initializing stdio-based MCP server with command: {mcp_config.command}")
                        mcp_server_instance = MCPStdioPlugin(
                            name=mcp_config.name,
                            description=mcp_config.description,
                            command=mcp_config.command,
                            args=mcp_config.args,
                        )

                    # Connect to the MCP server
                    logger.debug(f"Connecting to MCP server: {mcp_config.name}")
                    await mcp_server_instance.connect()

                    # Track the connection for cleanup
                    self.mcp_server_connections.append(mcp_server_instance)

                    # Add the MCP server to the kernel
                    logger.debug(f"Adding MCP server to kernel: {mcp_config.name}")
                    self.kernel.add_plugin(mcp_server_instance)

                    logger.info(f"MCP server loaded and connected: {mcp_config.name}")

                except Exception as e:
                    logger.error(f"Error initializing MCP server {mcp_config.name}: {e}", exc_info=e)
                    raise

            logger.info(f"Successfully initialized {len(self.mcp_server_connections)} MCP servers")

        except Exception as e:
            logger.error("Failed to initialize MCP servers", exc_info=e)
            raise self._create_agent_error(
                message="Failed to initialize MCP servers",
                context=context,
                cause=e,
                recovery_hint="Check MCP server configuration",
            ) from e

    async def _build_prompt_context(self, message: Message = None) -> str:
        """Build the prompt context for the agent.

        Args:
            message: The message to build context for (optional)

        Returns:
            The prompt context string
        """
        # Start with the system prompt from configuration
        system_prompt = getattr(self.config, "system_prompt", "")

        # Determine if we should use continuous reasoning mode
        use_continuous_reasoning = getattr(self.config, "continuous_reasoning", False)

        # Select the appropriate prompt template
        if use_continuous_reasoning:
            context = CONTINUOUS_REASONING_PROMPT.format(system_prompt=system_prompt)
        else:
            context = DEFAULT_PROMPT.format(system_prompt=system_prompt)

        logger.debug("Building prompt context starting with system prompt")

        # Add plugin instructions if we have plugins
        if self.plugin_manager and self.plugin_manager.plugins:
            plugin_instructions = []
            for plugin_class, plugin_instance in self.plugin_manager.plugins.values():
                if plugin_instance.plugin_instructions:
                    plugin_instructions.append(f"{plugin_instance.name}: {plugin_instance.plugin_instructions}")

            if plugin_instructions:
                context += "\n\nAvailable plugins:\n" + "\n".join(plugin_instructions)
                logger.debug(f"Added plugin instructions to context: {plugin_instructions}")

        # Add MCP server capabilities if we have any
        if hasattr(self, "mcp_server_connections") and self.mcp_server_connections:
            mcp_instructions = []
            for mcp_server in self.mcp_server_connections:
                if hasattr(mcp_server, "description") and mcp_server.description:
                    mcp_instructions.append(f"{mcp_server.name}: {mcp_server.description}")
                else:
                    mcp_instructions.append(f"{mcp_server.name}: MCP server for external tool access")

            if mcp_instructions:
                context += "\n\nAvailable MCP servers:\n" + "\n".join(mcp_instructions)
                logger.debug(f"Added MCP server instructions to context: {mcp_instructions}")

        return context

    async def process_message(self, message: Message, context: ConversationContext) -> AsyncGenerator[str, None]:
        """Process a message and generate responses."""
        # Initialize operation_context to None before the try block
        operation_context = None

        try:
            # Create operation context with the correct context.id
            operation_context = await self._handle_agent_operation(
                "process_message", message_type=message.role, context_id=context.id
            )
            logger.debug("Processing message with context: %s", operation_context)

            if not self.provider:
                raise RuntimeError("Agent not initialized")

            # Add message to context
            await context.add_message(message)
            logger.debug("Added message to context")

            # Build prompt context with plugins
            prompt_context = await self._build_prompt_context(message)
            logger.debug(f"Built prompt context: {prompt_context[:100]}...")

            # Get chat history from context
            history = context.get_history()
            logger.debug(f"Chat history has {len(history.messages)} messages")

            # Add system prompt if not already present
            if not any(msg.role == "system" for msg in history.messages):
                history.add_system_message(prompt_context)
                logger.debug("Added system prompt to history")

            async def _process():
                try:
                    # Create settings for function calling
                    from semantic_kernel.connectors.ai.function_choice_behavior import (
                        FunctionChoiceBehavior,
                    )
                    from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings import (
                        open_ai_prompt_execution_settings as openai_settings,
                    )

                    logger.debug("Creating OpenAI chat settings")
                    settings = openai_settings.OpenAIChatPromptExecutionSettings(
                        temperature=self.config.model.temperature,
                        max_tokens=self.config.model.max_tokens,
                        top_p=self.config.model.top_p,
                        frequency_penalty=self.config.model.frequency_penalty,
                        presence_penalty=self.config.model.presence_penalty,
                        function_choice_behavior=FunctionChoiceBehavior.Auto(),
                    )
                    logger.debug(f"Created settings: {settings}")

                    # Create arguments for the chat function
                    from semantic_kernel.functions import KernelArguments

                    arguments = KernelArguments(
                        chat_history=history,
                        user_input=message.content,
                        settings=settings,
                    )
                    logger.debug(f"Created kernel arguments with user input: {message.content[:50]}...")

                    # Stream the response
                    streamed_assistant_chunks = []
                    streamed_tool_chunks = []
                    complete_assistant_response = ""

                    logger.info("Invoking kernel with ChatBot.Chat function")
                    try:
                        async for result in self.kernel.invoke_stream(
                            plugin_name="ChatBot",
                            function_name="Chat",
                            arguments=arguments,
                            return_function_results=True,
                        ):
                            logger.debug(f"Received result type: {type(result)}")
                            if isinstance(result, list) and len(result) > 0:
                                msg = result[0]
                                logger.debug(f"Result item type: {type(msg)}, role: {getattr(msg, 'role', 'unknown')}")

                                if isinstance(msg, StreamingChatMessageContent):
                                    if msg.role == AuthorRole.ASSISTANT:
                                        # This is a standard assistant message - collect and yield it
                                        streamed_assistant_chunks.append(msg)
                                        chunk_text = str(msg)
                                        complete_assistant_response += chunk_text
                                        logger.debug(f"Assistant chunk: {chunk_text}")
                                        yield chunk_text
                                    elif msg.role == AuthorRole.TOOL:
                                        # This is a tool/function message - collect but don't yield
                                        logger.debug(f"Tool message received: {msg}")
                                        # Log extra details about the tool message
                                        if hasattr(msg, "function_invoke_attempt"):
                                            logger.debug(
                                                f"Tool message has function_invoke_attempt: "
                                                f"{getattr(msg, 'function_invoke_attempt')}"
                                            )
                                        if hasattr(msg, "items"):
                                            logger.debug(f"Tool message items: {getattr(msg, 'items')}")
                                        streamed_tool_chunks.append(msg)
                                        # Don't yield tool messages to avoid mixing message types
                                    else:
                                        logger.debug(f"Other message type with role {msg.role}: {msg}")
                    except ContentAdditionException as e:
                        # Handle the ContentAdditionException gracefully - log at debug level instead of warning
                        logger.debug(f"ContentAdditionException occurred: {e}. This is expected when mixing message roles.")
                        # Log more details about the exception at debug level
                        logger.debug(f"Exception details: {str(e)}")
                        logger.debug(f"Exception type: {type(e).__name__}")
                        # We've already yielded text chunks, so we can continue
                    except Exception as e:
                        logger.error(f"Error during streaming: {e}", exc_info=e)
                        yield f"\n\nError during streaming: {str(e)}"

                    # Process tool messages if any
                    if streamed_tool_chunks:
                        logger.debug(f"Processing {len(streamed_tool_chunks)} tool messages")
                        try:
                            # Group tool chunks by function_invoke_attempt if available
                            grouped_chunks: Dict[int, List[Any]] = {}
                            for chunk in streamed_tool_chunks:
                                key = getattr(chunk, "function_invoke_attempt", 0)
                                if key not in grouped_chunks:
                                    grouped_chunks[key] = []
                                grouped_chunks[key].append(chunk)

                            # Process tool calls and extract results
                            for attempt, chunks in grouped_chunks.items():
                                logger.debug(f"Tool call attempt {attempt} with {len(chunks)} chunks")
                                # Extract and yield function results
                                if chunks:
                                    for chunk in chunks:
                                        # Check if this chunk has items with function results
                                        if hasattr(chunk, "items"):
                                            for item in chunk.items:
                                                if hasattr(item, "content_type") and item.content_type == "function_result":
                                                    if hasattr(item, "result") and item.result:
                                                        # This is a function result, yield the actual result
                                                        logger.debug(f"Found function result: {item.result}")
                                                        # Replace the complete_assistant_response with the function result
                                                        complete_assistant_response = str(item.result)
                                                        # We've already yielded chunks, so we don't need to yield again
                        except Exception as e:
                            logger.error(f"Error processing tool chunks: {e}", exc_info=e)

                    # After streaming is complete, add the assistant's complete response to history
                    if streamed_assistant_chunks or complete_assistant_response:
                        logger.debug(f"Adding assistant response to history: {complete_assistant_response[:50]}...")
                        logger.debug(f"Chat history before adding response has {len(history.messages)} messages")
                        await context.add_message(Message(content=complete_assistant_response, role="assistant"))
                        logger.debug(f"Chat history after adding response has {len(history.messages)} messages")
                except Exception as e:
                    logger.error("Error executing chat function", exc_info=e)
                    yield f"\n\nError executing chat function: {str(e)}"

            # Use the retry handler with the process function
            async for chunk in self.retry_handler.retry_generator(_process, operation_context):
                yield chunk

        except Exception as e:
            # Ensure we have a default operation_context if we failed before creating one
            if operation_context is None:
                operation_context = ErrorContext(
                    component="agent",
                    operation="process_message",
                    details={
                        "agent_id": self.id,
                        "message_type": getattr(message, "role", "unknown"),
                        "error": str(e),
                    },
                )

            logger.error("Error processing message", extra={"error": str(e)}, exc_info=e)

            if isinstance(e, AgentError):
                raise

            error = self._create_agent_error(
                message="Error processing message",
                context=operation_context,
                cause=e,
                recovery_hint="Try rephrasing your message or check agent status",
            )
            yield f"Error: {str(error)} - {error.recovery_hint}"

    async def process_continuous_reasoning(
        self, message: Message, context: ConversationContext
    ) -> AsyncGenerator[str, None]:
        """Process a message with continuous reasoning.

        This method allows the agent to "think out loud", showing its reasoning
        process between tool calls and providing a window into its decision-making.

        Args:
            message: The message to process
            context: The conversation context

        Yields:
            Text chunks of the agent's reasoning, tool calls, and final response
        """
        # Initialize operation_context to None before the try block
        operation_context = None

        # Create a reasoning chain to track the agent's thought process
        reasoning_chain = ReasoningChain()

        try:
            # Create operation context with the correct context.id
            operation_context = await self._handle_agent_operation(
                "process_continuous_reasoning", message_type=message.role, context_id=context.id
            )
            logger.debug("Processing message with continuous reasoning: %s", operation_context)

            if not self.provider:
                raise RuntimeError("Agent not initialized")

            # Add message to context
            await context.add_message(message)
            logger.debug("Added message to context")

            # Build prompt context with plugins and continuous reasoning instructions
            prompt_context = await self._build_prompt_context(message)
            logger.debug(f"Built prompt context: {prompt_context[:100]}...")

            # Get chat history from context
            history = context.get_history()
            logger.debug(f"Chat history has {len(history.messages)} messages")

            # Add system prompt if not already present
            if not any(msg.role == "system" for msg in history.messages):
                history.add_system_message(prompt_context)
                logger.debug("Added system prompt to history")

            async def _process():
                try:
                    # Create settings for function calling
                    from semantic_kernel.connectors.ai.function_choice_behavior import (
                        FunctionChoiceBehavior,
                    )
                    from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings import (
                        open_ai_prompt_execution_settings as openai_settings,
                    )

                    logger.debug("Creating OpenAI chat settings")
                    settings = openai_settings.OpenAIChatPromptExecutionSettings(
                        temperature=self.config.model.temperature,
                        max_tokens=self.config.model.max_tokens or 4000,  # Ensure we have room for extended reasoning
                        top_p=self.config.model.top_p,
                        frequency_penalty=self.config.model.frequency_penalty,
                        presence_penalty=self.config.model.presence_penalty,
                        function_choice_behavior=FunctionChoiceBehavior.Auto(),
                    )
                    logger.debug(f"Created settings: {settings}")

                    # Create arguments for the chat function
                    from semantic_kernel.functions import KernelArguments

                    arguments = KernelArguments(
                        chat_history=history,
                        user_input=message.content,
                        settings=settings,
                    )
                    logger.debug(f"Created kernel arguments with user input: {message.content[:50]}...")

                    # Variables to track the current state
                    current_thinking = ""
                    in_thinking_block = False
                    in_answer_block = False
                    final_answer = ""
                    assistant_response = ""

                    logger.info("Invoking kernel with ChatBot.Chat function")
                    try:
                        async for result in self.kernel.invoke_stream(
                            plugin_name="ChatBot",
                            function_name="Chat",
                            arguments=arguments,
                            return_function_results=True,
                        ):
                            logger.debug(f"Received result type: {type(result)}")
                            if isinstance(result, list) and len(result) > 0:
                                msg = result[0]
                                logger.debug(f"Result item type: {type(msg)}, role: {getattr(msg, 'role', 'unknown')}")

                                if isinstance(msg, StreamingChatMessageContent):
                                    if msg.role == AuthorRole.ASSISTANT:
                                        # Process the chunk content
                                        chunk_text = str(msg)
                                        assistant_response += chunk_text

                                        # Check for thinking/answer tags
                                        if "<thinking>" in chunk_text:
                                            in_thinking_block = True
                                            # Extract just the content after the tag
                                            chunk_text = chunk_text.split("<thinking>", 1)[1]

                                        if "</thinking>" in chunk_text and in_thinking_block:
                                            # Extract just the content before the closing tag
                                            parts = chunk_text.split("</thinking>", 1)
                                            current_thinking += parts[0]
                                            in_thinking_block = False

                                            # Add the completed thinking to the reasoning chain
                                            reasoning_chain.add_reasoning(current_thinking)
                                            current_thinking = ""

                                            # Yield the thinking as it is completed
                                            yield f"Thinking: {current_thinking}\n"

                                            # Set the remainder for further processing
                                            if len(parts) > 1:
                                                chunk_text = parts[1]
                                            else:
                                                chunk_text = ""

                                        if "<answer>" in chunk_text:
                                            in_answer_block = True
                                            # Extract just the content after the tag
                                            chunk_text = chunk_text.split("<answer>", 1)[1]

                                        if "</answer>" in chunk_text and in_answer_block:
                                            # Extract just the content before the closing tag
                                            parts = chunk_text.split("</answer>", 1)
                                            final_answer += parts[0]
                                            in_answer_block = False

                                            # Add the completed answer to the reasoning chain
                                            reasoning_chain.add_response(final_answer)

                                            # Yield the final answer
                                            yield f"Answer: {final_answer}\n"

                                            # Set the remainder for further processing
                                            if len(parts) > 1:
                                                chunk_text = parts[1]
                                            else:
                                                chunk_text = ""

                                        # Add to current block based on state
                                        if in_thinking_block:
                                            current_thinking += chunk_text
                                            # We don't yield thinking chunks until the block is complete
                                        elif in_answer_block:
                                            final_answer += chunk_text
                                            # We don't yield answer chunks until the block is complete
                                        else:
                                            # This is regular text outside blocks, yield it
                                            yield chunk_text

                                    elif msg.role == AuthorRole.TOOL:
                                        # This is a tool/function message - process it
                                        logger.debug(f"Tool message received: {msg}")
                                        # Tool processing will be handled below
                                        # We don't yield tool messages directly
                                    else:
                                        logger.debug(f"Other message type with role {msg.role}: {msg}")
                    except ContentAdditionException as e:
                        # Handle the ContentAdditionException gracefully - log at debug level instead of warning
                        logger.debug(f"ContentAdditionException occurred: {e}. This is expected when mixing message roles.")
                        # Log more details about the exception at debug level
                        logger.debug(f"Exception details: {str(e)}")
                        logger.debug(f"Exception type: {type(e).__name__}")
                        # We've already yielded text chunks, so we can continue
                    except Exception as e:
                        logger.error(f"Error during streaming: {e}", exc_info=e)
                        yield f"\n\nError during streaming: {str(e)}"

                    # Process tool messages if any
                    tool_messages = self._extract_tool_messages(result)
                    if tool_messages:
                        logger.debug(f"==== PROCESSING {len(tool_messages)} TOOL MESSAGES IN CONTINUOUS REASONING ====")
                        try:
                            # Process each tool call
                            for i, tool_message in enumerate(tool_messages):
                                logger.debug(f"Processing tool message {i}: {tool_message}")

                                # Extract tool name and input
                                tool_name = tool_message.get("name", "unknown_tool")
                                # Ensure tool_name is always a string
                                if not isinstance(tool_name, str):
                                    tool_name = str(tool_name)
                                tool_input = tool_message.get("arguments", {})
                                if not isinstance(tool_input, dict):
                                    tool_input = {} if tool_input is None else {"input": tool_input}

                                logger.debug(f"Extracted tool_name: {tool_name}, type: {type(tool_name)}")

                                # Execute the tool and get result
                                tool_result = await self._execute_tool(tool_name, tool_input)

                                # Add to reasoning chain - ensure tool_name is a string
                                reasoning_chain.add_tool_call(
                                    tool_name=str(tool_name) if not isinstance(tool_name, str) else tool_name,
                                    tool_input=tool_input,
                                    tool_result=tool_result,
                                )

                                # Yield the tool call information
                                yield f"Tool call: {tool_name}\nInput: {tool_input}\nResult: {tool_result}\n"

                                # Check if the tool call failed due to missing parameters
                                if isinstance(tool_result, str) and tool_result.startswith(
                                    "Error: Missing required parameters"
                                ):
                                    # Feed the error back to the LLM to allow it to retry
                                    logger.debug(f"Tool call failed, feeding error back to LLM: {tool_result}")
                                    yield f"The tool call failed. {tool_result}\n"

                                    # Instead of trying to invoke the kernel again with a new message,
                                    # we'll just yield a message prompting the agent to try again
                                    # This avoids the StreamingChatMessageContent role conflict
                                    params_msg = f"\nPlease try again with the correct parameters for {tool_name}. "
                                    error_details = f"You need to provide: {tool_result.split(':', 2)[2].strip()}\n"
                                    yield params_msg + error_details

                                    # We don't need to add a new message to the context or invoke the kernel again
                                    # The agent will see this message in the next turn and can respond appropriately

                        except Exception as e:
                            logger.error(f"Error processing tool messages: {str(e)}", exc_info=True)
                            yield f"\n\nError processing tool calls: {str(e)}"

                    # Add complete response to history
                    # We'll use the final answer if available, otherwise the full assistant response
                    if final_answer:
                        complete_response = final_answer
                    else:
                        complete_response = assistant_response

                    if complete_response:
                        logger.debug(f"Adding assistant response to history: {complete_response[:50]}...")
                        await context.add_message(Message(content=complete_response, role="assistant"))

                except Exception as e:
                    logger.error("Error executing chat function", exc_info=e)
                    yield f"\n\nError executing chat function: {str(e)}"

            # Use the retry handler with the process function
            async for chunk in self.retry_handler.retry_generator(_process, operation_context):
                yield chunk

        except Exception as e:
            # Ensure we have a default operation_context if we failed before creating one
            if operation_context is None:
                operation_context = ErrorContext(
                    component="agent",
                    operation="process_continuous_reasoning",
                    details={
                        "agent_id": self.id,
                        "message_type": getattr(message, "role", "unknown"),
                        "error": str(e),
                    },
                )

            logger.error("Error processing message with continuous reasoning", extra={"error": str(e)}, exc_info=e)

            if isinstance(e, AgentError):
                raise

            # Create an agent error with proper context (but don't store the result since we don't use it)
            self._create_agent_error(
                message="Error processing message with continuous reasoning",
                context=operation_context,
                cause=e,
                recovery_hint="Try rephrasing your message or check agent status",
            )

    def _extract_tool_messages(self, result: Any) -> List[Dict[str, Any]]:
        """Extract tool messages from the result.

        This is a helper method to extract tool calls from the model response.

        Args:
            result: The result from the model

        Returns:
            A list of tool message dictionaries
        """
        # Explicitly annotate the type to avoid confusion
        tool_messages: List[Dict[str, Any]] = []

        # Add debug logging for the result
        logger.debug(f"_extract_tool_messages received result type: {type(result)}")
        logger.debug("==== EXTRACT TOOL MESSAGES ====")
        logger.debug(f"Result type: {type(result)}")

        # Check if the result is a list of messages
        if isinstance(result, list):
            logger.debug(f"Result is a list with {len(result)} items")
            for i, item in enumerate(result):
                # Only log the item type, not the full content which could be very verbose
                logger.debug(f"Processing item {i}, type: {type(item)}")

                # Look for tool calls in message content
                if hasattr(item, "role") and getattr(item, "role") == "tool":
                    logger.debug(f"Found tool message at index {i}")
                    # Try to extract function name and arguments
                    if hasattr(item, "name"):
                        tool_name = getattr(item, "name", "unknown_tool")
                        tool_args = getattr(item, "arguments", {})
                        # Ensure tool_name is always a string
                        if not isinstance(tool_name, str):
                            tool_name = str(tool_name)
                        logger.debug(f"Extracted tool name: {tool_name}, type: {type(tool_name)}")
                        # Only add tool messages with valid names
                        if tool_name is not None:
                            tool_messages.append({"name": str(tool_name), "arguments": tool_args})
                        else:
                            logger.debug("Skipping tool message with None name")
                    else:
                        logger.debug("Tool message at index {} has no 'name' attribute".format(i))

                    # Also check inside items if there's a nested structure
                    if hasattr(item, "items"):
                        items_list = getattr(item, "items", [])
                        logger.debug(f"Tool message has 'items' attribute with {len(items_list)} items")
                        for j, sub_item in enumerate(items_list):
                            if hasattr(sub_item, "function_name"):
                                tool_name = getattr(sub_item, "function_name", "unknown_tool")
                                tool_args = getattr(sub_item, "function_parameters", {})
                                # Ensure tool_name is always a string
                                if not isinstance(tool_name, str):
                                    tool_name = str(tool_name)
                                logger.debug(f"Extracted nested tool name: {tool_name}, type: {type(tool_name)}")
                                # Only add tool messages with valid names
                                if tool_name is not None:
                                    tool_messages.append({"name": str(tool_name), "arguments": tool_args})
                                else:
                                    logger.debug("Skipping nested tool message with None name")
                            else:
                                logger.debug(f"Sub-item {j} has no 'function_name' attribute")

                # Split the non-tool nested tool message checking to avoid long lines
                if hasattr(item, "items") and not (hasattr(item, "role") and getattr(item, "role") == "tool"):
                    # Check for tool calls in items even if the parent is not a tool message
                    items_list = getattr(item, "items", [])
                    if items_list:
                        msg = f"Non-tool message at index {i} has 'items' attribute with {len(items_list)} items"
                        logger.debug(msg)

                        for j, sub_item in enumerate(items_list):
                            if hasattr(sub_item, "function_name"):
                                tool_name = getattr(sub_item, "function_name", "unknown_tool")
                                tool_args = getattr(sub_item, "function_parameters", {})
                                # Ensure tool_name is always a string
                                if not isinstance(tool_name, str):
                                    tool_name = str(tool_name)
                                msg = f"Extracted non-tool nested tool name: {tool_name}, type: {type(tool_name)}"
                                logger.debug(msg)

                                # Only add tool messages with valid names
                                if tool_name is not None:
                                    tool_messages.append({"name": str(tool_name), "arguments": tool_args})
                                else:
                                    logger.debug("Skipping non-tool nested tool message with None name")
        else:
            logger.debug("Result is not a list, cannot extract tool messages")

        logger.debug(f"==== FINAL EXTRACTED TOOL MESSAGES: {len(tool_messages)} ====")
        # Add type: ignore to suppress mypy error about dict vs str type incompatibility
        for i, msg in enumerate(tool_messages):  # type: ignore
            # Use str() to ensure we're logging a string representation of the message
            logger.debug(f"Tool message {i}: {str(msg)}")
        return tool_messages

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Execute a tool and get the result.

        Args:
            tool_name: The name of the tool to execute
            tool_input: The input parameters for the tool

        Returns:
            The result of the tool execution
        """
        logger.debug("==== EXECUTE TOOL ====")
        logger.debug(f"Tool name: {tool_name}, type: {type(tool_name)}")

        if not self.plugin_manager:
            logger.warning("No plugin manager available, cannot execute tools")
            return f"Error: No plugin manager available to execute {tool_name}"

        try:
            # Check if tool_name is None
            if tool_name is None:
                logger.error("Tool name is None, cannot execute tool")
                return "Error: Tool name is None, cannot execute tool"

            # Try to find the tool in the plugin manager
            tool_parts = tool_name.split(".")
            logger.debug(f"Split tool_name into parts: {tool_parts}")

            if len(tool_parts) > 1:
                # Format: plugin_name.function_name
                plugin_name = tool_parts[0]
                function_name = tool_parts[1]
                logger.debug(f"Parsed plugin_name: {plugin_name}, function_name: {function_name}")
            else:
                # Just a function name, try to find it in any plugin
                plugin_name = None
                function_name = tool_name
                logger.debug(f"No plugin specified, using function_name: {function_name}")

            # Execute the function through the plugin manager
            if plugin_name:
                # Try to get the result using the specific plugin
                logger.debug(f"Executing tool {function_name} in plugin {plugin_name}")
                result = await self.plugin_manager.execute_plugin(plugin_name, function_name, **tool_input)
                return result
            else:
                # Try to find the function in any plugin
                logger.debug(f"Searching for tool {function_name} in all plugins")
                for plugin_name, (plugin_class, plugin_instance) in self.plugin_manager.plugins.items():
                    if hasattr(plugin_instance, function_name):
                        logger.debug(f"Found tool {function_name} in plugin {plugin_instance.name}")
                        func = getattr(plugin_instance, function_name)
                        is_coroutine = inspect.iscoroutinefunction(func)
                        logger.debug(f"Function is coroutine: {is_coroutine}")

                        try:
                            if is_coroutine:
                                logger.debug(f"Executing async function {function_name}")
                                result = await func(**tool_input)
                            else:
                                logger.debug(f"Executing sync function {function_name}")
                                import asyncio

                                result = await asyncio.to_thread(func, **tool_input)

                            return result
                        except TypeError as e:
                            # This is likely a parameter error
                            error_msg = str(e)
                            logger.warning(f"Parameter error executing function {function_name}: {error_msg}")

                            # Check if this is a missing parameter error
                            if "missing" in error_msg and "required" in error_msg and "argument" in error_msg:
                                # Extract the missing parameter name(s)
                                import re

                                missing_params = re.findall(r"'(\w+)'", error_msg)

                                # Return a helpful error message that the LLM can use to correct its call
                                return_msg = "Error: Missing required parameters for {}: {}. ".format(
                                    function_name, ", ".join(missing_params)
                                )
                                return_msg += "Please provide values for these parameters and try again."
                                return return_msg

                            # Other TypeError
                            error_details = f"Error: Invalid parameters for {function_name}: {error_msg}. "
                            error_details += "Please check parameter types and values."
                            return error_details
                        except Exception as e:
                            logger.error(f"Error executing function {function_name}: {str(e)}")
                            return f"Error executing function {function_name}: {str(e)}"

                # If we get here, we didn't find the function
                logger.error(f"Tool {function_name} not found in any plugin")
                return f"Error: Tool {function_name} not found"

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
            return f"Error executing tool {tool_name}: {str(e)}"

    async def close(self) -> None:
        """Close resources held by the agent."""
        logger.info(f"Closing agent resources: {self.id}")

        # Close MCP server connections
        if hasattr(self, "mcp_server_connections") and self.mcp_server_connections:
            logger.info(f"Closing {len(self.mcp_server_connections)} MCP server connections")
            for mcp_server in self.mcp_server_connections:
                try:
                    logger.debug(f"Closing MCP server connection: {mcp_server.name}")
                    await mcp_server.close()
                except Exception as e:
                    logger.warning(f"Error closing MCP server {mcp_server.name}: {e}")
            logger.info("All MCP server connections closed")

        # Clear provider and kernel references
        self.provider = None
        self.kernel = None
        logger.info(f"Agent resources closed: {self.id}")
