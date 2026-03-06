"""
Agent Registry for Agent Discovery and Management.

This module provides the AgentRegistry class which manages the
registration, discovery, and lifecycle of all agents in the system.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .base import Agent, AgentCapability


@dataclass
class AgentMetadata:
    """Metadata about a registered agent."""

    agent_id: str
    agent_type: str
    capabilities: list[str]
    state: str = "idle"
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """Registry for managing and discovering agents."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._metadata: dict[str, AgentMetadata] = {}
        self._lock = threading.RLock()
        self._capabilities_index: dict[str, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._listeners: list[Callable[[str, str], None]] = []

    def register(
        self,
        agent: Agent,
        agent_type: str,
        tags: Iterable[str] | None = None,
    ) -> None:
        """Register an agent with the registry."""
        with self._lock:
            agent_id = agent.agent_id

            # Check for duplicates
            if agent_id in self._agents:
                raise ValueError(f"Agent {agent_id} already registered")

            # Store agent and metadata
            self._agents[agent_id] = agent
            self._metadata[agent_id] = AgentMetadata(
                agent_id=agent_id,
                agent_type=agent_type,
                capabilities=[c.name for c in agent.capabilities],
                tags=list(tags or []),
            )

            # Build indexes
            self._index_capabilities(agent_id, agent.capabilities)
            self._index_tags(agent_id, tags or [])

            # Notify listeners
            self._notify_listeners(agent_id, "registered")

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent from the registry."""
        with self._lock:
            if agent_id not in self._agents:
                raise ValueError(f"Agent {agent_id} not found")

            # Update metadata state
            self._metadata[agent_id].state = "terminated"

            # Remove from indexes
            metadata = self._metadata[agent_id]
            for cap in metadata.capabilities:
                self._capabilities_index[cap].discard(agent_id)
            for tag in metadata.tags:
                self._tag_index[tag].discard(agent_id)

            # Remove from registry
            del self._agents[agent_id]
            del self._metadata[agent_id]

            # Notify listeners
            self._notify_listeners(agent_id, "unregistered")

    def get_agent(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        with self._lock:
            return self._agents.get(agent_id)

    def get_metadata(self, agent_id: str) -> AgentMetadata | None:
        """Get agent metadata by ID."""
        with self._lock:
            return self._metadata.get(agent_id)

    def list_agents(
        self,
        agent_type: str | None = None,
        state: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> list[AgentMetadata]:
        """List agents with optional filters."""
        with self._lock:
            results = list(self._metadata.values())

            if agent_type:
                results = [m for m in results if m.agent_type == agent_type]

            if state:
                results = [m for m in results if m.state == state]

            if tags:
                tag_set = set(tags)
                results = [m for m in results if tag_set.issubset(set(m.tags))]

            return results

    def find_by_capability(self, capability: str) -> list[str]:
        """Find agent IDs that have a specific capability."""
        with self._lock:
            return list(self._capabilities_index.get(capability, set()))

    def find_by_capabilities(self, capabilities: Iterable[str]) -> list[str]:
        """Find agent IDs that have all specified capabilities."""
        with self._lock:
            if not capabilities:
                return list(self._agents.keys())

            result_sets = [self._capabilities_index.get(cap, set()) for cap in capabilities]
            if not result_sets:
                return []

            return list(set.intersection(*result_sets))

    def find_by_tag(self, tag: str) -> list[str]:
        """Find agent IDs that have a specific tag."""
        with self._lock:
            return list(self._tag_index.get(tag, set()))

    def find_by_tags(self, tags: Iterable[str]) -> list[str]:
        """Find agent IDs that have all specified tags."""
        with self._lock:
            if not tags:
                return list(self._agents.keys())

            result_sets = [self._tag_index.get(tag, set()) for tag in tags]
            if not result_sets:
                return []

            return list(set.intersection(*result_sets))

    def update_agent_state(self, agent_id: str, state: str) -> None:
        """Update the state of an agent."""
        with self._lock:
            if agent_id in self._metadata:
                self._metadata[agent_id].state = state
                self._metadata[agent_id].last_seen = time.time()

    def get_available_agents(self) -> list[AgentMetadata]:
        """Get all agents that are currently available (idle)."""
        return self.list_agents(state="idle")

    def count_agents(
        self,
        agent_type: str | None = None,
        state: str | None = None,
    ) -> int:
        """Count agents with optional filters."""
        return len(self.list_agents(agent_type=agent_type, state=state))

    def add_listener(self, listener: Callable[[str, str], None]) -> None:
        """Add a listener for agent registration/unregistration events."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, str], None]) -> None:
        """Remove a listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _index_capabilities(self, agent_id: str, capabilities: list[AgentCapability]) -> None:
        """Index agent by capabilities."""
        for cap in capabilities:
            if cap.name not in self._capabilities_index:
                self._capabilities_index[cap.name] = set()
            self._capabilities_index[cap.name].add(agent_id)

    def _index_tags(self, agent_id: str, tags: Iterable[str]) -> None:
        """Index agent by tags."""
        for tag in tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(agent_id)

    def _notify_listeners(self, agent_id: str, event: str) -> None:
        """Notify all listeners of an event."""
        for listener in self._listeners:
            try:
                listener(agent_id, event)
            except Exception:
                pass  # Don't let one listener break others

    def cleanup_stale_agents(self, timeout: float = 300.0) -> list[str]:
        """Remove agents that haven't been seen recently."""
        with self._lock:
            now = time.time()
            stale = []

            for agent_id, metadata in self._metadata.items():
                if now - metadata.last_seen > timeout:
                    try:
                        self.unregister(agent_id)
                        stale.append(agent_id)
                    except ValueError:
                        pass

            return stale

    def get_registry_stats(self) -> dict[str, Any]:
        """Get statistics about the registry."""
        with self._lock:
            return {
                "total_agents": len(self._agents),
                "by_state": {
                    state: len([m for m in self._metadata.values() if m.state == state])
                    for state in ["idle", "busy", "error", "terminated"]
                },
                "total_capabilities": len(self._capabilities_index),
                "total_tags": len(self._tag_index),
                "agents_by_type": {
                    agent_type: len(
                        [m for m in self._metadata.values() if m.agent_type == agent_type]
                    )
                    for agent_type in set(m.agent_type for m in self._metadata.values())
                },
            }
