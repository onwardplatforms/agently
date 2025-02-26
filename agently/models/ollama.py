"""Ollama model provider implementation.

This module provides integration with Ollama's API, including:
- Chat completions with streaming support
- Embeddings generation
- Function calling support
- Error handling and retries
"""

import os
import inspect
import json
from typing import Any, AsyncIterator, Optional, List, Dict, Callable

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.ollama.services.ollama_chat_completion import OllamaChatCompletion
from semantic_kernel.connectors.ai.ollama.ollama_prompt_execution_settings import OllamaChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory, ChatMessageContent, TextContent
from semantic_kernel.functions import KernelFunction
from semantic_kernel.functions.kernel_arguments import KernelArguments
from ollama import AsyncClient

from agently.config.types import ModelConfig
from agently.errors import ErrorContext, ModelError

from .base import ModelProvider


class OllamaProvider(ModelProvider):
    """Ollama implementation of the model provider."""

    def __init__(self, config: ModelConfig):
        """Initialize the Ollama provider.

        Args:
            config: Configuration for the provider, including model settings
        """
        super().__init__()
        self.config = config
        self.kernel = None

        # Get base URL from environment or use default
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        # Create the Ollama AsyncClient
        self.ollama_client = AsyncClient(host=base_url)

        # Create the Ollama client using Semantic Kernel's built-in client
        # Note: OllamaChatCompletion doesn't accept async_client parameter
        self.client = OllamaChatCompletion(ai_model_id=self.config.model)
        self.service_id = "ollama"

    def register_kernel(self, kernel: Kernel):
        """Register the kernel with the provider for function calling.

        Args:
            kernel: The Semantic Kernel instance
        """
        self.kernel = kernel

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
            settings = OllamaChatPromptExecutionSettings(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens if self.config.max_tokens else 2048,
                top_p=self.config.top_p if self.config.top_p else 0.9,
            )

            # If kernel is available, we can use direct function calling with Ollama
            if self.kernel and hasattr(self.kernel, "plugins"):
                try:
                    # Convert messages to Ollama format
                    messages = self._convert_history_to_messages(history)

                    # Create a dictionary of available functions
                    available_functions = {}
                    function_tools = []

                    # Extract functions from kernel plugins
                    for plugin_name, plugin in self.kernel.plugins.items():
                        for func_name, function in plugin.functions.items():
                            # Skip the Chat function
                            if plugin_name == "ChatBot" and func_name == "Chat":
                                continue

                            # Add the function to available_functions with a unique name
                            function_id = f"{plugin_name}-{func_name}"
                            available_functions[function_id] = (plugin_name, func_name, function)

                            # Create a Python function that will be converted to a tool
                            # This is just a placeholder - we'll use the actual function from the kernel
                            def create_function_wrapper(plugin_name, func_name):
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

                                    # Add type hints for parameters if available
                                    for param in function.metadata.parameters:
                                        if param.name not in ["chat_history", "user_input"]:
                                            # We can't dynamically add type hints, but Ollama will use the schema
                                            pass

                                return wrapper

                            # Create and add the wrapper function
                            function_tools.append(create_function_wrapper(plugin_name, func_name))

                    # Use direct Ollama client for function calling with the function tools
                    response = await self.ollama_client.chat(
                        model=self.config.model,
                        messages=messages,
                        stream=True,
                        tools=function_tools,
                        temperature=self.config.temperature,
                    )

                    # Process the streaming response
                    buffer = ""
                    function_results = {}

                    async for chunk in response:
                        # Handle tool calls if present
                        if chunk.message and chunk.message.tool_calls:
                            for tool_call in chunk.message.tool_calls:
                                function_name = tool_call.function.name
                                arguments = tool_call.function.arguments

                                # Parse arguments if they're in string format
                                if isinstance(arguments, str):
                                    try:
                                        arguments = json.loads(arguments)
                                    except json.JSONDecodeError:
                                        arguments = {"text": arguments}

                                # Look up the function in our available_functions dictionary
                                if function_name in available_functions:
                                    plugin_name, func_name, function = available_functions[function_name]

                                    # Execute the function using the kernel
                                    try:
                                        result = await self.kernel.invoke(function, KernelArguments(**arguments))

                                        # Store the result and yield it
                                        function_results[function_name] = str(result)
                                        yield str(result)
                                    except Exception as e:
                                        error_msg = f"Error executing function {function_name}: {str(e)}"
                                        function_results[function_name] = error_msg
                                        yield error_msg
                                else:
                                    error_msg = f"Function {function_name} not found"
                                    yield error_msg

                        # Yield the content if present and not a function call
                        if chunk.message and chunk.message.content:
                            content = chunk.message.content

                            # Check if the content looks like a function call
                            if "(" in content and ")" in content:
                                # Check if we've already executed this function
                                skip = False
                                for func_result in function_results.values():
                                    if func_result in content:
                                        skip = True
                                        break

                                if not skip:
                                    # Try to match a function call pattern
                                    import re

                                    match = re.search(r"(\w+)\s*\((.*?)\)", content)
                                    if match:
                                        func_name = match.group(1)
                                        args_str = match.group(2)

                                        # Check if this is one of our functions
                                        found_function = False
                                        for available_func, (plugin_name, fn_name, function) in available_functions.items():
                                            if fn_name == func_name:
                                                found_function = True

                                                # Parse arguments
                                                args = {}
                                                if args_str and args_str.strip():
                                                    # Handle quoted string arguments
                                                    if args_str.startswith('"') and args_str.endswith('"'):
                                                        args = {"name": args_str.strip('"')}
                                                    elif args_str.startswith("'") and args_str.endswith("'"):
                                                        args = {"name": args_str.strip("'")}
                                                    else:
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
                                                        except:
                                                            # If parsing fails, try to use as a positional argument
                                                            if not args_str.strip().startswith("{"):
                                                                args = {"name": args_str.strip()}

                                                # Execute the function
                                                max_retries = 3
                                                retry_count = 0
                                                last_error = None

                                                while retry_count < max_retries:
                                                    try:
                                                        # If this is a standalone function call (not embedded in text),
                                                        # add a message indicating we're executing the function
                                                        if content.strip() == f"{func_name}({args_str})":
                                                            yield f"I'll execute the {func_name} function for you.\n\n"

                                                        result = await self.kernel.invoke(function, KernelArguments(**args))

                                                        # Store the result and yield it
                                                        function_results[available_func] = str(result)

                                                        # If this is a retry, add a message indicating we're executing the function
                                                        if retry_count > 0:
                                                            yield f"I'll execute the {func_name} function for you.\n\n"

                                                        yield str(result)
                                                        skip = True
                                                        break
                                                    except Exception as e:
                                                        last_error = e
                                                        retry_count += 1
                                                        print(
                                                            f"Error executing function {func_name} (attempt {retry_count}): {str(e)}"
                                                        )
                                                        # Short delay before retry
                                                        import asyncio

                                                        await asyncio.sleep(0.1)

                                                if retry_count == max_retries and last_error:
                                                    error_msg = f"Error executing function {func_name} after {max_retries} attempts: {str(last_error)}"
                                                    print(error_msg)
                                                    yield f"I tried to execute the {func_name} function but encountered an error: {str(last_error)}"

                                        if found_function:
                                            # Skip yielding the function call text
                                            continue

                                # Special handling for common patterns like "greet()" or "hello()"
                                if not skip and (content.strip() == "greet()" or content.strip() == "hello()"):
                                    # Look for these specific functions
                                    for available_func, (plugin_name, fn_name, function) in available_functions.items():
                                        if fn_name in ["greet", "hello"]:
                                            try:
                                                yield f"I'll execute the {fn_name} function for you.\n\n"
                                                result = await self.kernel.invoke(function, KernelArguments())
                                                function_results[available_func] = str(result)
                                                yield str(result)
                                                skip = True
                                                break
                                            except Exception as e:
                                                error_msg = f"Error executing function {fn_name}: {str(e)}"
                                                print(error_msg)
                                                yield f"I tried to execute the {fn_name} function but encountered an error: {str(e)}"

                                # Special handling for cases where the model just outputs the function name without parentheses
                                if not skip and (content.strip() == "greet" or content.strip() == "hello"):
                                    # Look for these specific functions
                                    for available_func, (plugin_name, fn_name, function) in available_functions.items():
                                        if fn_name == content.strip():
                                            try:
                                                yield f"I'll execute the {fn_name} function for you.\n\n"
                                                result = await self.kernel.invoke(function, KernelArguments())
                                                function_results[available_func] = str(result)
                                                yield str(result)
                                                skip = True
                                                break
                                            except Exception as e:
                                                error_msg = f"Error executing function {fn_name}: {str(e)}"
                                                print(error_msg)
                                                yield f"I tried to execute the {fn_name} function but encountered an error: {str(e)}"

                                # More general function name detection for single-word responses
                                if not skip and len(content.strip().split()) == 1:
                                    # Check if this single word matches any function name
                                    for available_func, (plugin_name, fn_name, function) in available_functions.items():
                                        # Check for exact match or close match (e.g., "greet" vs "greeting")
                                        if (
                                            fn_name == content.strip()
                                            or content.strip().startswith(fn_name)
                                            or fn_name.startswith(content.strip())
                                        ):
                                            try:
                                                yield f"I'll execute the {fn_name} function for you.\n\n"
                                                result = await self.kernel.invoke(function, KernelArguments())
                                                function_results[available_func] = str(result)
                                                yield str(result)
                                                skip = True
                                                break
                                            except Exception as e:
                                                error_msg = f"Error executing function {fn_name}: {str(e)}"
                                                print(error_msg)
                                                yield f"I tried to execute the {fn_name} function but encountered an error: {str(e)}"

                                if not skip:
                                    # Check if the entire content is just a function call
                                    # This handles cases where the model outputs just "function_name(args)" without other text
                                    full_content_match = re.match(r"^\s*(\w+)\s*\((.*?)\)\s*$", content.strip())
                                    if full_content_match and not buffer.strip():
                                        func_name = full_content_match.group(1)
                                        args_str = full_content_match.group(2)

                                        # Check if this is one of our functions
                                        for available_func, (plugin_name, fn_name, function) in available_functions.items():
                                            if fn_name == func_name:
                                                # Parse arguments
                                                args = {}
                                                if args_str and args_str.strip():
                                                    # Handle quoted string arguments
                                                    if args_str.startswith('"') and args_str.endswith('"'):
                                                        args = {"name": args_str.strip('"')}
                                                    elif args_str.startswith("'") and args_str.endswith("'"):
                                                        args = {"name": args_str.strip("'")}
                                                    else:
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
                                                        except:
                                                            # If parsing fails, try to use as a positional argument
                                                            if not args_str.strip().startswith("{"):
                                                                args = {"name": args_str.strip()}

                                                try:
                                                    # Add a message indicating we're executing the function
                                                    yield f"I'll execute the {func_name} function for you.\n\n"

                                                    # Execute the function
                                                    result = await self.kernel.invoke(function, KernelArguments(**args))

                                                    # Store the result and yield it
                                                    function_results[available_func] = str(result)
                                                    yield str(result)
                                                    skip = True
                                                    break
                                                except Exception as e:
                                                    error_msg = f"Error executing function {func_name}: {str(e)}"
                                                    print(error_msg)
                                                    yield f"I tried to execute the {func_name} function but encountered an error: {str(e)}"
                                                    skip = True
                                                    break

                                    if not skip:
                                        buffer += content
                                        yield content
                            else:
                                buffer += content
                                yield content

                except Exception as e:
                    # Fall back to standard streaming if function calling fails
                    print(f"Error using direct function calling: {e}")

                    async for chunk in self.client.get_streaming_chat_message_content(
                        chat_history=history,
                        settings=settings,
                    ):
                        if chunk.items and chunk.items[0].text:
                            yield chunk.items[0].text
            else:
                # Use standard streaming without function calling
                async for chunk in self.client.get_streaming_chat_message_content(
                    chat_history=history,
                    settings=settings,
                ):
                    if chunk.items and chunk.items[0].text:
                        yield chunk.items[0].text

        except Exception as e:
            error = self._create_model_error(message=f"Unexpected error: {str(e)}", context=context, cause=e)
            yield f"Error: {str(error)} - {error.recovery_hint}"

    def _convert_history_to_messages(self, history: ChatHistory) -> List[Dict[str, str]]:
        """Convert chat history to Ollama message format.

        Args:
            history: The chat history

        Returns:
            The messages in Ollama format
        """
        messages = []
        for msg in history.messages:
            role = msg.role.value
            # Ollama doesn't support system messages in the same way, convert to user
            if role == "system":
                role = "user"

            content = ""
            for item in msg.items:
                if hasattr(item, "text"):
                    content += item.text

            messages.append({"role": role, "content": content})

        return messages

    def _extract_tools_from_kernel(self, kernel: Kernel) -> List[Dict[str, Any]]:
        """Extract tools from kernel plugins for Ollama function calling.

        Args:
            kernel: The Semantic Kernel instance

        Returns:
            List of tools in Ollama format
        """
        tools = []

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
            parameters = {"type": "object", "properties": {}, "required": []}

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
            tool = {
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
            print(f"Error creating tool for {plugin_name}-{func_name}: {str(e)}")
            return None

    async def get_embeddings(self, text: str) -> list[float]:
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
            import json

            async def _make_request():
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
