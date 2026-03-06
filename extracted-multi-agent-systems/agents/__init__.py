"""
Multi-Agent Orchestration System for IndestructibleAutoOps.

This module provides a comprehensive framework for agent-based
task execution with true coordination, messaging, and policy enforcement.
"""

from .base import Agent, AgentCapability, AgentMessage, MessageType
from .communication import AgentCommunicationBus, MessageQueue
from .coordination import AgentCoordinator, Task, TaskResult, TaskStatus
from .lifecycle import AgentLifecycle, AgentState
from .policy_engine import (
    Policy,
    PolicyEngine,
    PolicySeverity,
    PolicyType,
    PolicyViolation,
)
from .registry import AgentRegistry

__all__ = [
    # Base agent types
    "Agent",
    "AgentCapability",
    "AgentMessage",
    "MessageType",
    # Registry and discovery
    "AgentRegistry",
    # Communication
    "AgentCommunicationBus",
    "MessageQueue",
    # Coordination
    "AgentCoordinator",
    "Task",
    "TaskResult",
    "TaskStatus",
    # Policy enforcement
    "PolicyEngine",
    "Policy",
    "PolicySeverity",
    "PolicyType",
    "PolicyViolation",
    # Lifecycle management
    "AgentLifecycle",
    "AgentState",
]
