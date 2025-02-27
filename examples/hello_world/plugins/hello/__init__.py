"""Example hello world plugin demonstrating the plugin system."""

from typing import Optional

from semantic_kernel.functions import kernel_function

from agently.plugins.base import Plugin, PluginVariable
from agently.utils import format_action, format_subaction, format_result, format_function_call, format_function_result


class HelloPlugin(Plugin):
    """A simple hello world plugin for testing the agent system."""

    name = "hello"
    description = "A simple plugin that says hello"
    plugin_instructions = """
    Use this plugin when you need to:
    - Greet someone with a simple hello message
    - Greet generically using the configured default_name when no specific person is mentioned

    IMPORTANT: When you call the greet function, return ONLY the exact greeting message produced
    by the function without adding any additional commentary or explanations.
    Do not call the function multiple times for the same request.
    """

    # Define a default_name variable that can be configured
    default_name = PluginVariable(
        type=str,
        description="The default name to use when no name is provided",
        default="World",
    )

    @kernel_function(description="Greet someone by name, or use the configured default_name if no name is provided")
    def greet(self, name: Optional[str] = None) -> str:
        """Generate a friendly greeting message.

        When no specific name is provided, this will use the configured default_name value.
        For generic greetings, call this with no arguments to use the default_name.

        Args:
            name: The name of the person to greet (optional, uses default_name if not provided)

        Returns:
            A personalized greeting message
        """
        # Show the action being performed
        print(format_action(f"Plugin: Creating greeting"))

        # Generate the greeting
        if name:
            print(format_subaction(f"Target: {name}"))
            result = f"Hello, {name}!"
        else:
            print(format_subaction(f"Using default: {self.default_name}"))
            result = f"Hello, {self.default_name}!"

        # Show the successful result
        print(format_result(f'Function returned: "{result}"'))

        return result
