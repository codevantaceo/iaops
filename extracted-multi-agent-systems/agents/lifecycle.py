"""
Agent Lifecycle Management for Agent Orchestration.

This module provides the AgentLifecycle class which manages
the spawning, monitoring, and termination of agents.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import Agent, AgentMessage, MessageType
from .communication import AgentCommunicationBus
from .registry import AgentRegistry


class AgentState(Enum):
    """States in an agent's lifecycle."""

    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    IDLE = "idle"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


@dataclass
class AgentInstance:
    """Represents a running agent instance."""

    agent: Agent
    agent_type: str
    state: AgentState = AgentState.INITIALIZING
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)
    error_count: int = 0
    task_count: int = 0

    # Health metrics
    health_score: float = 1.0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0


class AgentLifecycle:
    """Manages the lifecycle of agents."""

    def __init__(
        self,
        registry: AgentRegistry,
        communication: AgentCommunicationBus,
        heartbeat_interval: float = 30.0,
        health_check_interval: float = 60.0,
    ):
        self.registry = registry
        self.communication = communication

        self.heartbeat_interval = heartbeat_interval
        self.health_check_interval = health_check_interval

        self._instances: dict[str, AgentInstance] = {}
        self._agent_types: dict[str, type[Agent]] = {}

        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread: threading.Thread | None = None

        # Callbacks
        self._state_change_callbacks: list[Callable[[str, AgentState, AgentState], None]] = []
        self._error_callbacks: list[Callable[[str, Exception], None]] = []

    def register_agent_type(
        self,
        agent_type: str,
        agent_class: type[Agent],
    ) -> None:
        """Register an agent type that can be spawned."""
        with self._lock:
            self._agent_types[agent_type] = agent_class

    async def spawn_agent(
        self,
        agent_type: str,
        agent_id: str,
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> AgentInstance | None:
        """Spawn a new agent instance."""
        with self._lock:
            # Check if agent type is registered
            if agent_type not in self._agent_types:
                raise ValueError(f"Unknown agent type: {agent_type}")

            # Check if agent ID already exists
            if agent_id in self._instances:
                raise ValueError(f"Agent {agent_id} already exists")

            # Create agent instance
            agent_class = self._agent_types[agent_type]
            agent = agent_class(agent_id=agent_id, config=config or {})

            # Create instance record
            instance = AgentInstance(
                agent=agent,
                agent_type=agent_type,
            )

            self._instances[agent_id] = instance

            # Register with communication bus
            self.communication.register_agent(agent_id)

        try:
            # Initialize the agent
            await self._initialize_agent(instance)

            # Register with registry
            self.registry.register(
                agent=agent,
                agent_type=agent_type,
                tags=tags,
            )

            return instance

        except Exception:
            # Cleanup on failure
            with self._lock:
                if agent_id in self._instances:
                    del self._instances[agent_id]

                self.communication.unregister_agent(agent_id)

            raise

    async def spawn_agents(
        self,
        specs: list[tuple[str, str, dict[str, Any] | None, list[str] | None]],
    ) -> list[AgentInstance]:
        """Spawn multiple agents concurrently."""
        tasks = [
            self.spawn_agent(agent_type, agent_id, config, tags)
            for agent_type, agent_id, config, tags in specs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        instances = []
        for result in results:
            if isinstance(result, Exception):
                # Log error but continue
                pass
            elif result is not None:
                instances.append(result)

        return instances

    async def terminate_agent(self, agent_id: str, graceful: bool = True) -> bool:
        """Terminate an agent instance."""
        with self._lock:
            instance = self._instances.get(agent_id)
            if not instance:
                return False

            old_state = instance.state
            instance.state = AgentState.SHUTTING_DOWN

            # Notify state change
            self._notify_state_change(agent_id, old_state, instance.state)

        try:
            if graceful:
                # Send shutdown message
                shutdown_msg = AgentMessage(
                    msg_type=MessageType.SHUTDOWN,
                    sender_id="lifecycle",
                    recipient_id=agent_id,
                )
                self.communication.send(shutdown_msg)

                # Wait for agent to shutdown
                await asyncio.sleep(1.0)

            # Call shutdown on agent
            await instance.agent.shutdown()

            # Update state
            with self._lock:
                instance.state = AgentState.TERMINATED
                self._notify_state_change(agent_id, old_state, instance.state)

            # Unregister
            self.registry.unregister(agent_id)
            self.communication.unregister_agent(agent_id)

            # Remove instance
            with self._lock:
                del self._instances[agent_id]

            return True

        except Exception as e:
            # Handle error
            with self._lock:
                instance.state = AgentState.ERROR
                instance.error_count += 1

            self._notify_error(agent_id, e)

            # Force cleanup
            try:
                self.registry.unregister(agent_id)
                self.communication.unregister_agent(agent_id)

                with self._lock:
                    if agent_id in self._instances:
                        del self._instances[agent_id]
            except Exception:
                pass

            return False

    async def terminate_all(self, graceful: bool = True) -> int:
        """Terminate all agents."""
        with self._lock:
            agent_ids = list(self._instances.keys())

        count = 0
        for agent_id in agent_ids:
            if await self.terminate_agent(agent_id, graceful):
                count += 1

        return count

    def get_instance(self, agent_id: str) -> AgentInstance | None:
        """Get an agent instance by ID."""
        with self._lock:
            return self._instances.get(agent_id)

    def list_instances(
        self,
        agent_type: str | None = None,
        state: AgentState | None = None,
    ) -> list[AgentInstance]:
        """List agent instances with optional filters."""
        with self._lock:
            instances = list(self._instances.values())

            if agent_type:
                instances = [i for i in instances if i.agent_type == agent_type]

            if state:
                instances = [i for i in instances if i.state == state]

            return instances

    def get_state(self, agent_id: str) -> AgentState | None:
        """Get the state of an agent."""
        instance = self.get_instance(agent_id)
        return instance.state if instance else None

    def is_alive(self, agent_id: str) -> bool:
        """Check if an agent is alive."""
        state = self.get_state(agent_id)
        return state in (AgentState.READY, AgentState.BUSY, AgentState.IDLE)

    def start_monitoring(self) -> None:
        """Start the monitoring thread."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
            )
            self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop the monitoring thread."""
        with self._lock:
            self._running = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=2.0)
                self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Monitoring loop for health checks."""
        while self._running:
            try:
                self._check_heartbeats()
                self._check_health()
                time.sleep(min(self.heartbeat_interval, self.health_check_interval))
            except Exception:
                pass

    def _check_heartbeats(self) -> None:
        """Check agent heartbeats."""
        now = time.time()

        with self._lock:
            for agent_id, instance in self._instances.items():
                if not self.is_alive(agent_id):
                    continue

                # Send heartbeat
                heartbeat_msg = AgentMessage(
                    msg_type=MessageType.HEARTBEAT,
                    sender_id="lifecycle",
                    recipient_id=agent_id,
                )
                self.communication.send(heartbeat_msg)

                # Check for stale agents
                if now - instance.last_heartbeat > self.heartbeat_interval * 2:
                    # Mark as error
                    old_state = instance.state
                    instance.state = AgentState.ERROR
                    self._notify_state_change(agent_id, old_state, instance.state)

    def _check_health(self) -> None:
        """Check agent health."""
        # Simplified health check
        # In production, would monitor CPU, memory, etc.
        pass

    async def _initialize_agent(self, instance: AgentInstance) -> None:
        """Initialize an agent."""
        old_state = instance.state
        instance.state = AgentState.INITIALIZING
        self._notify_state_change(instance.agent.agent_id, old_state, instance.state)

        # Call initialize
        await instance.agent.initialize()

        # Update state
        old_state = instance.state
        instance.state = AgentState.READY
        instance.started_at = time.time()
        self._notify_state_change(instance.agent.agent_id, old_state, instance.state)

    def _notify_state_change(
        self,
        agent_id: str,
        old_state: AgentState,
        new_state: AgentState,
    ) -> None:
        """Notify state change callbacks."""
        for callback in self._state_change_callbacks:
            try:
                callback(agent_id, old_state, new_state)
            except Exception:
                pass

    def _notify_error(self, agent_id: str, error: Exception) -> None:
        """Notify error callbacks."""
        for callback in self._error_callbacks:
            try:
                callback(agent_id, error)
            except Exception:
                pass

    def add_state_change_callback(
        self,
        callback: Callable[[str, AgentState, AgentState], None],
    ) -> None:
        """Add a state change callback."""
        self._state_change_callbacks.append(callback)

    def remove_state_change_callback(
        self,
        callback: Callable[[str, AgentState, AgentState], None],
    ) -> None:
        """Remove a state change callback."""
        if callback in self._state_change_callbacks:
            self._state_change_callbacks.remove(callback)

    def add_error_callback(
        self,
        callback: Callable[[str, Exception], None],
    ) -> None:
        """Add an error callback."""
        self._error_callbacks.append(callback)

    def remove_error_callback(
        self,
        callback: Callable[[str, Exception], None],
    ) -> None:
        """Remove an error callback."""
        if callback in self._error_callbacks:
            self._error_callbacks.remove(callback)

    def get_lifecycle_stats(self) -> dict[str, Any]:
        """Get statistics about the lifecycle manager."""
        with self._lock:
            return {
                "total_instances": len(self._instances),
                "by_state": {
                    state.value: len([i for i in self._instances.values() if i.state == state])
                    for state in AgentState
                },
                "by_type": {
                    agent_type: len(
                        [i for i in self._instances.values() if i.agent_type == agent_type]
                    )
                    for agent_type in set(i.agent_type for i in self._instances.values())
                },
                "total_errors": sum(i.error_count for i in self._instances.values()),
                "total_tasks": sum(i.task_count for i in self._instances.values()),
                "running": self._running,
            }
