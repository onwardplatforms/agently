"""Example hello world plugin demonstrating the plugin system."""

import datetime
from typing import Optional, Dict

from semantic_kernel.functions import kernel_function

from agently.plugins.base import Plugin, PluginVariable
from agently.utils import format_action, print_agent_message, format_result, format_function_call, format_function_result


class HelloPlugin(Plugin):
    """A simple hello world plugin for testing the agent system."""

    name = "hello"
    description = "A simple plugin that says hello"
    plugin_instructions = """
    Use this plugin when you need to:
    - Greet someone with a simple hello message
    - Remember a user's name for future interactions
    - Create time-aware greetings (morning, afternoon, evening)
    - Generate farewell messages

    You can combine multiple functions for a more personalized experience:
    1. Use remember_name to store the user's name
    2. Use time_greeting to create a time-appropriate greeting
    3. Use farewell when the conversation is ending

    IMPORTANT: When calling any greeting function, return ONLY the exact greeting message produced
    by the function without adding any additional commentary or explanations.
    Do not call the function multiple times for the same request.
    """

    # Define a default_name variable that can be configured
    default_name = PluginVariable(
        type=str,
        description="The default name to use when no name is provided",
        default="World",
    )

    def __init__(self, **kwargs):
        """Initialize the plugin."""
        super().__init__(**kwargs)
        self.remembered_names: Dict[str, str] = {}
        self.conversation_id = None

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
        print(format_action("saying hello"))

        # Check if we have a remembered name for this conversation
        if not name and self.conversation_id and self.conversation_id in self.remembered_names:
            name = self.remembered_names[self.conversation_id]
            result = f"Hello, {name}!"
        # Generate the greeting
        elif name:
            result = f"Hello, {name}!"
        else:
            name = self.default_name
            result = f"Hello, {self.default_name}!"

        return result

    @kernel_function(description="Remember a user's name for future interactions in this conversation")
    def remember_name(self, name: str, conversation_id: Optional[str] = None) -> str:
        """Store a user's name for this conversation.

        Args:
            name: The name to remember
            conversation_id: Optional conversation ID (uses current context if not provided)

        Returns:
            Confirmation message
        """
        print(format_action("remembering name"))

        # Store the conversation ID
        self.conversation_id = conversation_id or self.conversation_id or "default"

        # Store the name
        self.remembered_names[self.conversation_id] = name

        result = f"I'll remember that your name is {name}."

        return result

    @kernel_function(description="Create a greeting based on the time of day")
    def time_greeting(self, name: Optional[str] = None) -> str:
        """Generate a time-appropriate greeting (morning, afternoon, evening).

        Args:
            name: The name to include in the greeting (optional)

        Returns:
            A time-appropriate greeting
        """
        print(format_action("creating time-based greeting"))

        # Get current hour (0-23)
        current_hour = datetime.datetime.now().hour

        # Determine time of day
        if 5 <= current_hour < 12:
            time_greeting = "Good morning"
        elif 12 <= current_hour < 18:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        # Check for remembered name
        if not name and self.conversation_id and self.conversation_id in self.remembered_names:
            name = self.remembered_names[self.conversation_id]
        elif not name:
            name = self.default_name

        # Create greeting
        result = f"{time_greeting}, {name}!"

        return result

    @kernel_function(description="Generate a farewell message")
    def farewell(self, name: Optional[str] = None) -> str:
        """Generate a farewell message.

        Args:
            name: The name to include in the farewell (optional)

        Returns:
            A farewell message
        """
        print(format_action("saying goodbye"))

        # Check for remembered name
        if not name and self.conversation_id and self.conversation_id in self.remembered_names:
            name = self.remembered_names[self.conversation_id]
        elif not name:
            name = self.default_name

        # Create farewell
        result = f"Goodbye, {name}! Have a wonderful day."

        return result
