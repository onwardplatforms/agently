"""Base model provider interface for the Agently framework.

This module defines the abstract base class for model providers, which handles
interactions with various AI models and provides error handling capabilities.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from semantic_kernel.contents import ChatHistory

from agently.core import get_error_handler
from agently.errors import ErrorContext, ModelError, RetryConfig, RetryHandler


class ModelProvider(ABC):
    """Base class for model providers."""

    def __init__(self):
        self.error_handler = get_error_handler()
        self.retry_handler: RetryHandler[Any, Any] = RetryHandler(
            RetryConfig(max_attempts=3, initial_delay=1.0, max_delay=10.0)
        )

    @abstractmethod
    def chat(self, history: ChatHistory, **kwargs) -> AsyncIterator[str]:
        """Process a chat message and return response chunks."""

    @abstractmethod
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings for text."""

    async def _handle_api_call(self, operation_name: str, **context_details) -> ErrorContext:
        """Create error context for API calls."""
        return ErrorContext(
            component="model_provider",
            operation=operation_name,
            details=context_details,
        )

    def _create_model_error(self, message: str, context: ErrorContext, cause: Exception = None) -> ModelError:
        """Create a standardized model error."""
        return ModelError(
            message=message,
            context=context,
            recovery_hint="Check API credentials and try again",
            cause=cause,
        )
