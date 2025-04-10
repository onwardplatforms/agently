"""Continuous reasoning support for agents.

This module provides the infrastructure for agents to engage in multi-step reasoning,
allowing them to "think out loud" between function calls and provide explanations
of their thought process.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in the continuous reasoning flow."""

    REASONING = "reasoning"  # Intermediate reasoning/thinking
    TOOL_CALL = "tool_call"  # Function/tool call
    RESPONSE = "response"  # Final response to user


class ReasoningStep:
    """Represents a step in the agent's reasoning process."""

    def __init__(
        self,
        message_type: MessageType,
        content: str,
        tool_name: Optional[Union[str, Dict[str, Any]]] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Any] = None,
    ):
        """Initialize a reasoning step.

        Args:
            message_type: The type of message
            content: The content of the step
            tool_name: The name of the tool (for tool calls)
            tool_input: The input to the tool (for tool calls)
            tool_result: The result from the tool (for tool calls)
        """
        self.message_type = message_type
        self.content = content
        # Convert tool_name to string if it's a dictionary
        self.tool_name = str(tool_name) if tool_name is not None else None
        self.tool_input = tool_input
        self.tool_result = tool_result

    def __str__(self) -> str:
        """Get string representation of the reasoning step."""
        if self.message_type == MessageType.TOOL_CALL:
            return f"TOOL CALL: {self.tool_name}\nInput: {self.tool_input}\nResult: {self.tool_result}"
        elif self.message_type == MessageType.REASONING:
            return f"REASONING: {self.content}"
        else:
            return f"RESPONSE: {self.content}"


class ReasoningChain:
    """Manages a sequence of reasoning steps for an agent.

    This class tracks the agent's thinking process, tool calls, and responses
    during a continuous reasoning session.
    """

    def __init__(self):
        """Initialize a new reasoning chain."""
        self.steps: List[ReasoningStep] = []
        self.current_reasoning = ""

    def add_reasoning(self, content: str) -> None:
        """Add a reasoning step to the chain.

        Args:
            content: The reasoning content to add
        """
        # If we have accumulated reasoning, create a step
        if self.current_reasoning:
            self.current_reasoning += "\n" + content
        else:
            self.current_reasoning = content

    def finalize_reasoning(self) -> None:
        """Finalize the current reasoning and add it as a step."""
        if self.current_reasoning:
            self.steps.append(
                ReasoningStep(
                    message_type=MessageType.REASONING,
                    content=self.current_reasoning,
                )
            )
            self.current_reasoning = ""

    def add_tool_call(self, tool_name: Union[str, Dict[str, Any]], tool_input: Dict[str, Any], tool_result: Any) -> None:
        """Add a tool call step to the chain.

        Args:
            tool_name: Name of the tool being called (string or dict with name field)
            tool_input: Input parameters for the tool
            tool_result: Result of the tool execution
        """
        # Finalize any accumulated reasoning first
        self.finalize_reasoning()

        # Convert tool_name to string if it's a dictionary
        tool_name_str = str(tool_name) if not isinstance(tool_name, str) else tool_name

        self.steps.append(
            ReasoningStep(
                message_type=MessageType.TOOL_CALL,
                content=f"Calling tool {tool_name_str} with input {tool_input}",
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=tool_result,
            )
        )

    def add_response(self, content: str) -> None:
        """Add a final response step to the chain.

        Args:
            content: The response content
        """
        # Finalize any accumulated reasoning first
        self.finalize_reasoning()

        self.steps.append(
            ReasoningStep(
                message_type=MessageType.RESPONSE,
                content=content,
            )
        )

    def get_formatted_chain(self) -> str:
        """Get a formatted representation of the entire reasoning chain.

        Returns:
            A string representation of the reasoning chain
        """
        result = []
        for step in self.steps:
            result.append(str(step))
        return "\n\n".join(result)

    def get_all_steps(self) -> List[ReasoningStep]:
        """Get all steps in the reasoning chain.

        Returns:
            List of all reasoning steps
        """
        return self.steps.copy()


def extract_tool_calls_and_reasoning(
    message_content: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """Extract tool calls and reasoning from a message.

    This is a placeholder function that would be implemented to parse
    the model's output to separate reasoning from tool calls. The actual
    implementation would depend on the format of the model's output.

    Args:
        message_content: The content to parse

    Returns:
        A tuple containing (list of tool calls, reasoning text)
    """
    # Placeholder implementation
    # In a real implementation, this would parse the model's output
    # and extract tool calls and reasoning based on some convention
    # For example, tool calls might be marked with special syntax
    return [], message_content
