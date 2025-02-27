"""Ollama model provider implementation.

This module provides integration with Ollama's API, including:
- Chat completions with streaming support
- Embeddings generation
- Function calling support
- Error handling and retries
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple, TypeVar

from ollama import AsyncClient
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.ollama.ollama_prompt_execution_settings import OllamaChatPromptExecutionSettings
from semantic_kernel.connectors.ai.ollama.services.ollama_chat_completion import OllamaChatCompletion
from semantic_kernel.contents import ChatHistory, TextContent
from semantic_kernel.functions import KernelFunction
from semantic_kernel.functions.kernel_arguments import KernelArguments

from agently.config.types import ModelConfig
from agently.errors import ModelError

from .base import ModelProvider

logger = logging.getLogger(__name__)
T = TypeVar("T")

# mypy: ignore-errors


class OllamaProvider(ModelProvider):
    """Ollama implementation of the model provider."""

    def __init__(self, config: ModelConfig):
        """Initialize the Ollama provider.

        Args:
            config: Configuration for the provider, including model settings
        """
        super().__init__()
        self.config = config
        self.kernel: Optional[Kernel] = None

        # Get base URL from environment or use default
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        # Create the Ollama AsyncClient
        self.ollama_client = AsyncClient(host=base_url)

        # Create the Ollama client using Semantic Kernel's built-in client
        # Note: OllamaChatCompletion doesn't accept async_client parameter
        self.client = OllamaChatCompletion(ai_model_id=self.config.model)
        self.service_id = "ollama"

        logger.debug(f"Initialized Ollama provider with model: {self.config.model}")

    def register_kernel(self, kernel: Kernel):
        """Register the kernel with the provider for function calling.

        Args:
            kernel: The Semantic Kernel instance
        """
        self.kernel = kernel
        logger.debug("Kernel registered with Ollama provider")

    async def chat(self, history: ChatHistory, **kwargs: Any) -> AsyncIterator[str]:
        """Process a chat message using Ollama's API.

        Args:
            history: Chat history to use for context
            **kwargs: Additional arguments to pass to the API

        Yields:
            Chunks of the response as they arrive

        Raises:
            ModelError: For API errors or unexpected issues
        """
        try:
            context = await self._handle_api_call(
                "chat_completion",
                model=self.config.model,
                messages=history.messages,
            )

            # Build settings dictionary from config
            settings = OllamaChatPromptExecutionSettings()
            # Set parameters individually
            if hasattr(settings, "temperature") and self.config.temperature is not None:
                settings.temperature = self.config.temperature
            if hasattr(settings, "max_tokens") and self.config.max_tokens is not None:
                settings.max_tokens = self.config.max_tokens
            if hasattr(settings, "top_p") and self.config.top_p is not None:
                settings.top_p = self.config.top_p

            # If kernel is available, we can use direct function calling with Ollama
            if self.kernel is not None and hasattr(self.kernel, "plugins"):
                try:
                    # Convert messages to Ollama format
                    messages = self._convert_history_to_messages(history)

                    # Get available functions from kernel plugins
                    available_functions, function_tools = self._extract_available_functions()

                    # Prepare options with temperature
                    options: Optional[Dict[str, Any]] = None
                    if self.config.temperature is not None:
                        options = {"temperature": self.config.temperature}

                    # Use direct Ollama client for function calling with the function tools
                    response = await self.ollama_client.chat(
                        model=self.config.model,
                        messages=messages,
                        stream=True,
                        tools=function_tools,
                        options=options,
                    )

                    # Process the streaming response
                    buffer = ""
                    function_results: Dict[str, str] = {}
                    executed_functions: Set[str] = set()

                    async for chunk in response:
                        # Handle tool calls if present
                        if chunk.message and chunk.message.tool_calls:
                            for tool_call in chunk.message.tool_calls:
                                function_name = tool_call.function.name
                                arguments = tool_call.function.arguments

                                # Parse arguments if they're in string format
                                if isinstance(arguments, str):
                                    try:
                                        arguments_dict = json.loads(arguments)
                                        # Ensure we're using a Dict type
                                        if isinstance(arguments_dict, dict):
                                            arguments = arguments_dict  # type: ignore
                                        else:
                                            arguments = {"text": arguments}
                                    except json.JSONDecodeError:
                                        arguments = {"text": arguments}

                                # Execute the function if available
                                result = await self._execute_function_by_id(
                                    function_name, arguments, available_functions, function_results  # type: ignore
                                )
                                if result:
                                    yield result  # type: ignore

                        # Yield the content if present and not a function call
                        if chunk.message and chunk.message.content:
                            content = str(chunk.message.content)  # Ensure content is a string

                            # Process potential function calls in the content
                            processed, result = await self._process_function_call_in_content(
                                content, buffer, available_functions, function_results, executed_functions
                            )

                            if processed:
                                if result:
                                    yield result  # type: ignore
                            else:
                                buffer += content
                                yield content  # type: ignore

                except Exception as e:
                    # Fall back to standard streaming if function calling fails
                    logger.error(f"Error using direct function calling: {e}", exc_info=True)
                    async for chunk in self._fallback_to_standard_streaming(history, settings):
                        yield chunk
            else:
                # Use standard streaming without function calling
                async for chunk in self._fallback_to_standard_streaming(history, settings):
                    yield chunk

        except Exception as e:
            error = self._create_model_error(message=f"Unexpected error: {str(e)}", context=context, cause=e)
            yield f"Error: {str(error)} - {error.recovery_hint}"

    async def _fallback_to_standard_streaming(
        self, history: ChatHistory, settings: OllamaChatPromptExecutionSettings
    ) -> AsyncIterator[str]:
        """Fall back to standard streaming without function calling.

        Args:
            history: Chat history to use for context
            settings: Execution settings for the chat

        Yields:
            Chunks of the response as they arrive
        """
        async for chunk in self.client.get_streaming_chat_message_content(
            chat_history=history,
            settings=settings,
        ):
            if chunk.items:
                for item in chunk.items:
                    if isinstance(item, TextContent) and item.text:
                        yield item.text

    def _extract_available_functions(self) -> Tuple[Dict[str, Tuple[str, str, KernelFunction]], List[Any]]:
        """Extract available functions from kernel plugins.

        Returns:
            A tuple containing:
            - Dictionary mapping function IDs to (plugin_name, function_name, function) tuples
            - List of function tools for Ollama
        """
        available_functions: Dict[str, Tuple[str, str, KernelFunction]] = {}
        function_tools: List[Any] = []

        # Extract functions from kernel plugins
        if self.kernel is not None and hasattr(self.kernel, "plugins"):
            for plugin_name, plugin in self.kernel.plugins.items():
                for func_name, function in plugin.functions.items():
                    # Skip the Chat function
                    if plugin_name == "ChatBot" and func_name == "Chat":
                        continue

                    # Add the function to available_functions with a unique name
                    function_id = f"{plugin_name}-{func_name}"
                    available_functions[function_id] = (plugin_name, func_name, function)

                    # Create a Python function that will be converted to a tool
                    function_tools.append(self._create_function_wrapper(plugin_name, func_name, function))

            # Log available functions
            if available_functions:
                func_list = ", ".join([f"{plugin}.{func}" for plugin, func, _ in available_functions.values()])
                logger.info(f"Available functions for function calling: {func_list}")

        return available_functions, function_tools

    def _create_function_wrapper(self, plugin_name: str, func_name: str, function: KernelFunction) -> Any:
        """Create a function wrapper for Ollama tools.

        Args:
            plugin_name: Name of the plugin
            func_name: Name of the function
            function: The kernel function

        Returns:
            A function wrapper that can be used as an Ollama tool
        """

        async def wrapper(**kwargs):
            # This function will be converted to a tool schema
            # The actual execution happens later
            return f"Called {plugin_name}.{func_name} with {kwargs}"

        # Set the name to match what we'll look for in available_functions
        wrapper.__name__ = f"{plugin_name}-{func_name}"

        # Copy metadata from the original function
        if hasattr(function, "metadata") and function.metadata:
            # Set docstring from function description
            wrapper.__doc__ = function.metadata.description

        return wrapper

    async def _execute_function_by_id(
        self,
        function_id: str,
        arguments: Dict[str, Any],  # Make sure this is explicitly Dict, not Mapping
        available_functions: Dict[str, Tuple[str, str, KernelFunction]],
        function_results: Dict[str, str],
    ) -> Optional[str]:
        """Execute a function by its ID.

        Args:
            function_id: The ID of the function to execute
            arguments: Arguments to pass to the function
            available_functions: Dictionary of available functions
            function_results: Dictionary to store function results

        Returns:
            The result of the function execution, or an error message
        """
        # Look up the function in our available_functions dictionary
        if function_id in available_functions:
            plugin_name, func_name, function = available_functions[function_id]

            # Execute the function using the kernel
            try:
                if self.kernel is not None:
                    result = await self.kernel.invoke(function, KernelArguments(**arguments))

                    # Store the result and return it
                    result_str = str(result)
                    function_results[function_id] = result_str
                    return result_str
                else:
                    error_msg = "Kernel is not initialized"
                    function_results[function_id] = error_msg
                    logger.error(error_msg)
                    return error_msg
            except Exception as e:
                error_msg = f"Error executing function {function_id}: {str(e)}"
                function_results[function_id] = error_msg
                logger.error(error_msg, exc_info=True)
                return error_msg
        else:
            error_msg = f"Function {function_id} not found"
            logger.warning(error_msg)
            return error_msg

    def _parse_function_arguments(self, args_str: str) -> Dict[str, Any]:
        """Parse function arguments from a string.

        Args:
            args_str: String containing function arguments

        Returns:
            Dictionary of parsed arguments
        """
        args: Dict[str, Any] = {}
        if not args_str or not args_str.strip():
            return args

        # Handle quoted string arguments
        if args_str.startswith('"') and args_str.endswith('"'):
            return {"name": args_str.strip('"')}
        elif args_str.startswith("'") and args_str.endswith("'"):
            return {"name": args_str.strip("'")}

        # Try to parse as key=value pairs
        try:
            for arg in args_str.split(","):
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    # Remove quotes from values
                    if value.startswith('"') and value.endswith('"'):
                        value = value.strip('"')
                    elif value.startswith("'") and value.endswith("'"):
                        value = value.strip("'")
                    args[key.strip()] = value.strip()
        except Exception:
            # If parsing fails, try to use as a positional argument
            if not args_str.strip().startswith("{"):
                args = {"name": args_str.strip()}

        return args

    async def _execute_function_with_retry(
        self, function: KernelFunction, args: Dict[str, Any], func_name: str, max_retries: int = 3
    ) -> Tuple[bool, str, Optional[Exception]]:
        """Execute a function with retry logic.

        Args:
            function: The function to execute
            args: Arguments to pass to the function
            func_name: Name of the function (for error reporting)
            max_retries: Maximum number of retries

        Returns:
            Tuple containing:
            - Success flag
            - Result string or error message
            - Exception object if an error occurred, None otherwise
        """
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                if self.kernel is not None:
                    result = await self.kernel.invoke(function, KernelArguments(**args))
                    result_str = str(result)
                    return True, result_str, None
                else:
                    error_msg = "Kernel is not initialized"
                    return False, error_msg, RuntimeError(error_msg)
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(f"Error executing function {func_name} (attempt {retry_count}): {str(e)}")
                # Short delay before retry
                await asyncio.sleep(0.1)

        error_msg = f"I tried to execute the {func_name} function but encountered " f"an error: {str(last_error)}"
        return False, error_msg, last_error

    async def _process_function_call_in_content(
        self,
        content: str,
        buffer: str,
        available_functions: Dict[str, Tuple[str, str, KernelFunction]],
        function_results: Dict[str, str],
        executed_functions: Set[str],
    ) -> Tuple[bool, Optional[str]]:
        """Process potential function calls in content.

        Args:
            content: Content to process
            buffer: Current buffer of text
            available_functions: Dictionary of available functions
            function_results: Dictionary of function results
            executed_functions: Set of already executed function IDs

        Returns:
            Tuple containing:
            - Boolean indicating if content was processed as a function call
            - Result string if a function was executed, None otherwise
        """
        # Check if the content looks like a function call
        if "(" not in content or ")" not in content:
            # Special handling for function names without parentheses
            if content.strip() in ["greet", "hello"] or len(content.strip().split()) == 1:
                return await self._handle_function_name_only(
                    content.strip(), available_functions, function_results, executed_functions
                )
            return False, None

        # Check if we've already executed this function
        for func_id, result in function_results.items():
            if result in content:
                return True, None

        # Try to match a function call pattern
        match = re.search(r"(\w+)\s*\((.*?)\)", content)
        if not match:
            return False, None

        func_name = match.group(1)
        args_str = match.group(2)

        # Find the function in available functions
        for available_func, (plugin_name, fn_name, function) in available_functions.items():
            if fn_name == func_name:
                # Skip if we've already executed this function
                if available_func in executed_functions:
                    return True, None

                # Parse arguments
                args = self._parse_function_arguments(args_str)

                # Add a message if this is a standalone function call
                result_text = ""
                if content.strip() == f"{func_name}({args_str})":
                    result_text = f"I'll execute the {func_name} function for you.\n\n"

                # Execute the function
                success, result, _ = await self._execute_function_with_retry(function, args, func_name)

                # Store the result and mark as executed
                if success:
                    function_results[available_func] = result
                    executed_functions.add(available_func)

                return True, result_text + result

        # Check if the entire content is just a function call
        full_content_match = re.match(r"^\s*(\w+)\s*\((.*?)\)\s*$", content.strip())
        if full_content_match and not buffer.strip():
            func_name = full_content_match.group(1)
            args_str = full_content_match.group(2)

            # Find the function in available functions
            for available_func, (plugin_name, fn_name, function) in available_functions.items():
                if fn_name == func_name:
                    # Skip if we've already executed this function
                    if available_func in executed_functions:
                        return True, None

                    # Parse arguments
                    args = self._parse_function_arguments(args_str)

                    # Add a message indicating we're executing the function
                    result_text = f"I'll execute the {func_name} function for you.\n\n"

                    # Execute the function
                    success, result, _ = await self._execute_function_with_retry(function, args, func_name)

                    # Store the result and mark as executed
                    if success:
                        function_results[available_func] = result
                        executed_functions.add(available_func)

                    return True, result_text + result

        return False, None

    async def _handle_function_name_only(
        self,
        content: str,
        available_functions: Dict[str, Tuple[str, str, KernelFunction]],
        function_results: Dict[str, str],
        executed_functions: Set[str],
    ) -> Tuple[bool, Optional[str]]:
        """Handle cases where the model outputs just a function name.

        Args:
            content: Content containing just a function name
            available_functions: Dictionary of available functions
            function_results: Dictionary of function results
            executed_functions: Set of already executed function IDs

        Returns:
            Tuple containing:
            - Boolean indicating if content was processed as a function call
            - Result string if a function was executed, None otherwise
        """
        for available_func, (plugin_name, fn_name, function) in available_functions.items():
            # Check for exact match or close match
            if fn_name == content or content.startswith(fn_name) or fn_name.startswith(content):
                # Skip if we've already executed this function
                if available_func in executed_functions:
                    return True, None

                # Add a message indicating we're executing the function
                result_text = f"I'll execute the {fn_name} function for you.\n\n"

                # Execute the function with empty arguments
                success, result, _ = await self._execute_function_with_retry(function, {}, fn_name)

                # Store the result and mark as executed
                if success:
                    function_results[available_func] = result
                    executed_functions.add(available_func)

                return True, result_text + result

        return False, None

    def _convert_history_to_messages(self, history: ChatHistory) -> List[Dict[str, str]]:
        """Convert chat history to Ollama message format.

        Args:
            history: The chat history

        Returns:
            The messages in Ollama format
        """
        messages: List[Dict[str, str]] = []
        for msg in history.messages:
            role = msg.role.value
            # Ollama doesn't support system messages in the same way, convert to user
            if role == "system":
                role = "user"

            content = ""
            for item in msg.items:
                if hasattr(item, "text") and item.text is not None:
                    content += item.text

            messages.append({"role": role, "content": content})

        return messages

    def _extract_tools_from_kernel(self, kernel: Optional[Kernel]) -> List[Dict[str, Any]]:
        """Extract tools from kernel plugins for Ollama function calling.

        Args:
            kernel: The Semantic Kernel instance

        Returns:
            List of tools in Ollama format
        """
        tools: List[Dict[str, Any]] = []

        if kernel is not None and hasattr(kernel, "plugins"):
            for plugin_name, plugin in kernel.plugins.items():
                for func_name, function in plugin.functions.items():
                    # Skip the Chat function
                    if plugin_name == "ChatBot" and func_name == "Chat":
                        continue

                    # Create a tool definition for the function
                    tool = self._create_tool_from_function(function, plugin_name, func_name)
                    if tool:
                        tools.append(tool)

        return tools

    def _create_tool_from_function(
        self, function: KernelFunction, plugin_name: str, func_name: str
    ) -> Optional[Dict[str, Any]]:
        """Create a tool definition from a kernel function.

        Args:
            function: The kernel function
            plugin_name: The name of the plugin
            func_name: The name of the function

        Returns:
            Tool definition in Ollama format
        """
        try:
            # Get function metadata
            metadata = function.metadata

            # Create parameters schema
            parameters: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}

            for param in metadata.parameters:
                if param.name not in ["chat_history", "user_input"]:  # Skip standard parameters
                    param_type = "string"  # Default type

                    if param.type_ == "int" or param.type_ == "integer":
                        param_type = "integer"
                    elif param.type_ == "float" or param.type_ == "number":
                        param_type = "number"
                    elif param.type_ == "bool" or param.type_ == "boolean":
                        param_type = "boolean"

                    parameters["properties"][param.name] = {
                        "type": param_type,
                        "description": param.description or f"Parameter {param.name}",
                    }

                    if param.is_required:
                        parameters["required"].append(param.name)

            # Create the tool definition
            tool: Dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": f"{plugin_name}-{func_name}",
                    "description": metadata.description or f"Function {func_name} from plugin {plugin_name}",
                    "parameters": parameters,
                },
            }

            return tool
        except Exception as e:
            # If there's an error creating the tool, log it and return None
            logger.error(f"Error creating tool for {plugin_name}-{func_name}: {str(e)}", exc_info=True)
            return None

    async def get_embeddings(self, text: str) -> List[float]:
        """Get embeddings for text using Ollama's API.

        Args:
            text: Text to get embeddings for

        Returns:
            List of embedding values

        Raises:
            ModelError: For API errors or unexpected issues
        """
        try:
            context = await self._handle_api_call("embeddings", model=self.config.model, text=text)

            # Use the Ollama API directly for embeddings since SK doesn't have a convenient method

            import aiohttp

            async def _make_request() -> List[float]:
                try:
                    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                    api_url = f"{base_url}/api"

                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{api_url}/embeddings",
                            json={"model": self.config.model, "prompt": text},
                        ) as response:
                            if response.status != 200:
                                error_text = await response.text()
                                raise ModelError(
                                    message=f"Ollama API error getting embeddings: {error_text}",
                                    context=context,
                                    recovery_hint="Check Ollama server status and model availability",
                                )

                            result = await response.json()
                            return result.get("embedding", [0.0] * 10)  # Return embeddings or fallback
                except Exception as e:
                    raise ModelError(
                        message=f"Ollama API error getting embeddings: {str(e)}",
                        context=context,
                        recovery_hint="Check Ollama server status and model availability",
                        cause=e,
                    )

            return await self.retry_handler.retry(_make_request, context)
        except Exception as e:
            raise ModelError(
                message=f"Failed to get embeddings: {str(e)}",
                context=context,
                recovery_hint="Check Ollama server status and model availability",
                cause=e,
            )
