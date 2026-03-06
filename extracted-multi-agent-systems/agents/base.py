"""
Base Agent Interfaces and Types for Multi-Agent Orchestration.

This module defines the fundamental abstractions for agents in the
IndestructibleAutoOps system, including message types, capabilities,
and the agent interface.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


class MessageType(Enum):
    """Types of messages that can be exchanged between agents."""

    # Lifecycle messages
    SPAWN = "spawn"
    INIT = "init"
    READY = "ready"
    SHUTDOWN = "shutdown"
    TERMINATE = "terminate"

    # Task-related messages
    TASK_ASSIGN = "task_assign"
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAIL = "task_fail"
    TASK_RETRY = "task_retry"

    # Coordination messages
    HEARTBEAT = "heartbeat"
    STATUS_REQUEST = "status_request"
    STATUS_RESPONSE = "status_response"

    # Data exchange messages
    DATA_REQUEST = "data_request"
    DATA_RESPONSE = "data_response"
    DATA_PUSH = "data_push"

    # Policy and governance messages
    POLICY_CHECK = "policy_check"
    POLICY_VIOLATION = "policy_violation"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"

    # Error handling
    ERROR = "error"


@dataclass
class AgentMessage:
    """Message exchanged between agents."""

    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.DATA_PUSH
    sender_id: str = ""
    recipient_id: str = ""
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    reply_to: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMessage:
        """Create message from dictionary."""
        return cls(
            msg_id=data.get("msg_id", str(uuid.uuid4())),
            msg_type=MessageType(data.get("msg_type", "data_push")),
            sender_id=data.get("sender_id", ""),
            recipient_id=data.get("recipient_id", ""),
            timestamp=data.get("timestamp", time.time()),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
            reply_to=data.get("reply_to", ""),
        )


@dataclass
class AgentCapability:
    """Describes what an agent can do."""

    name: str
    description: str
    input_types: list[str]
    output_types: list[str]
    is_async: bool = False
    required_capabilities: list[str] = field(default_factory=list)

    def can_handle(self, input_type: str) -> bool:
        """Check if this capability can handle the given input type."""
        return input_type in self.input_types


@dataclass
class AgentStatus:
    """Current status of an agent."""

    agent_id: str
    state: str = "idle"
    current_task: str | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    uptime: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)
    capabilities: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """Base class for all agents in the system."""

    def __init__(
        self,
        agent_id: str,
        capabilities: list[AgentCapability],
        config: dict[str, Any] | None = None,
    ):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.config = config or {}
        self.status = AgentStatus(
            agent_id=agent_id,
            capabilities=[c.name for c in capabilities],
        )
        self._message_handlers: dict[MessageType, Callable] = {}
        self._setup_handlers()

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the agent."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the agent gracefully."""
        pass

    @abstractmethod
    async def execute_task(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        pass

    def get_capability(self, name: str) -> AgentCapability | None:
        """Get a capability by name."""
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    def has_capability(self, name: str) -> bool:
        """Check if agent has a specific capability."""
        return self.get_capability(name) is not None

    def can_handle_input(self, input_type: str) -> bool:
        """Check if any capability can handle the given input type."""
        return any(cap.can_handle(input_type) for cap in self.capabilities)

    def register_handler(
        self, msg_type: MessageType, handler: Callable[[AgentMessage], Any]
    ) -> None:
        """Register a message handler."""
        self._message_handlers[msg_type] = handler

    async def handle_message(self, message: AgentMessage) -> AgentMessage | None:
        """Handle an incoming message."""
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            return await handler(message)
        return None

    def _setup_handlers(self) -> None:
        """Setup default message handlers."""
        self.register_handler(MessageType.HEARTBEAT, self._handle_heartbeat)
        self.register_handler(MessageType.STATUS_REQUEST, self._handle_status_request)
        self.register_handler(MessageType.TASK_ASSIGN, self._handle_task_assign)

    async def _handle_heartbeat(self, message: AgentMessage) -> AgentMessage:
        """Handle heartbeat message."""
        self.status.last_heartbeat = time.time()
        return AgentMessage(
            msg_type=MessageType.STATUS_RESPONSE,
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            payload=self.status.__dict__,
            correlation_id=message.msg_id,
        )

    async def _handle_status_request(self, message: AgentMessage) -> AgentMessage:
        """Handle status request."""
        self.status.uptime = time.time() - self.status.uptime
        return AgentMessage(
            msg_type=MessageType.STATUS_RESPONSE,
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            payload=self.status.__dict__,
            correlation_id=message.msg_id,
        )

    async def _handle_task_assign(self, message: AgentMessage) -> AgentMessage:
        """Handle task assignment."""
        task = message.payload.get("task", {})
        context = message.payload.get("context", {})

        try:
            self.status.state = "busy"
            self.status.current_task = task.get("task_id", "unknown")

            result = await self.execute_task(task, context)

            self.status.state = "idle"
            self.status.current_task = None
            self.status.tasks_completed += 1

            return AgentMessage(
                msg_type=MessageType.TASK_COMPLETE,
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                payload={
                    "task_id": task.get("task_id"),
                    "result": result,
                    "status": "success",
                },
                correlation_id=message.correlation_id,
            )
        except Exception as e:
            self.status.state = "error"
            self.status.current_task = None
            self.status.tasks_failed += 1

            return AgentMessage(
                msg_type=MessageType.TASK_FAIL,
                sender_id=self.agent_id,
                recipient_id=message.sender_id,
                payload={
                    "task_id": task.get("task_id"),
                    "error": str(e),
                    "status": "failed",
                },
                correlation_id=message.correlation_id,
            )
