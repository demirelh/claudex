"""Base backend interface for ClaudeX."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, Callable


class BackendType(Enum):
    """Available backend types."""
    COPILOT = "copilot"
    OPENAI = "openai"


@dataclass
class ToolCall:
    """Accumulated tool call from streaming response."""
    id: str = ""
    function_name: str = ""
    arguments_json: str = ""


@dataclass
class StreamResult:
    """Result of a streaming chat completion.

    May contain text content, tool calls, or both.
    """
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    # Token usage tracking
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Timing
    time_to_first_token: float = 0.0
    total_time: float = 0.0
    # Whether the stream was interrupted but partial content was recovered
    partial: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class Backend(Protocol):
    """Protocol for LLM backend implementations.

    All backends must implement streaming chat completion with tool support.
    """

    @property
    def name(self) -> str:
        """Human-readable backend name (e.g., 'GitHub Copilot Business')."""
        ...

    @property
    def backend_type(self) -> BackendType:
        """Backend type identifier."""
        ...

    def is_available(self) -> bool:
        """Check if backend is available (credentials exist, etc.)."""
        ...

    async def stream_chat_with_tools(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 16384,
        temperature: float = 0.0,
        top_p: float = 1.0,
        tools: Optional[list[dict]] = None,
        on_content_chunk: Optional[Callable[[str], None]] = None,
    ) -> StreamResult:
        """Stream a chat completion with tool support.

        Args:
            messages: List of chat messages (OpenAI format).
            model: Model identifier.
            max_tokens: Maximum response tokens.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.
            tools: Optional list of tool definitions (OpenAI format).
            on_content_chunk: Optional callback for each text chunk.

        Returns:
            StreamResult with accumulated content and/or tool calls.
        """
        ...
