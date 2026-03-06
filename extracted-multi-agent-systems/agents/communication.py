"""
Agent Communication Bus for Inter-Agent Messaging.

This module provides the communication infrastructure for agents
to exchange messages asynchronously using a pub/sub pattern.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from .base import AgentMessage, MessageType


@dataclass
class MessageQueue:
    """Queue for messages to/from an agent."""

    agent_id: str
    inbound: Queue[AgentMessage] = field(default_factory=Queue)
    outbound: Queue[AgentMessage] = field(default_factory=Queue)
    max_size: int = 1000

    def put_inbound(self, message: AgentMessage, timeout: float = 1.0) -> bool:
        """Put a message in the inbound queue."""
        try:
            self.inbound.put(message, timeout=timeout)
            return True
        except Exception:
            return False

    def get_inbound(self, timeout: float = 1.0) -> AgentMessage | None:
        """Get a message from the inbound queue."""
        try:
            return self.inbound.get(timeout=timeout)
        except Empty:
            return None

    def put_outbound(self, message: AgentMessage, timeout: float = 1.0) -> bool:
        """Put a message in the outbound queue."""
        try:
            self.outbound.put(message, timeout=timeout)
            return True
        except Exception:
            return False

    def get_outbound(self, timeout: float = 1.0) -> AgentMessage | None:
        """Get a message from the outbound queue."""
        try:
            return self.outbound.get(timeout=timeout)
        except Empty:
            return None

    def size(self) -> tuple[int, int]:
        """Get the size of inbound and outbound queues."""
        return self.inbound.qsize(), self.outbound.qsize()

    def clear(self) -> None:
        """Clear both queues."""
        while not self.inbound.empty():
            self.inbound.get_nowait()
        while not self.outbound.empty():
            self.outbound.get_nowait()


class AgentCommunicationBus:
    """Communication bus for agent messaging."""

    def __init__(self, max_queue_size: int = 1000):
        self._queues: dict[str, MessageQueue] = {}
        self._subscribers: defaultdict[str, set[str]] = defaultdict(set)
        self._history: list[AgentMessage] = []
        self._max_history = 1000
        self._max_queue_size = max_queue_size
        self._lock = threading.RLock()
        self._running = False
        self._delivery_thread: threading.Thread | None = None

    def register_agent(self, agent_id: str) -> MessageQueue:
        """Register an agent and create its message queues."""
        with self._lock:
            if agent_id in self._queues:
                return self._queues[agent_id]

            queue = MessageQueue(agent_id=agent_id, max_size=self._max_queue_size)
            self._queues[agent_id] = queue
            return queue

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent and remove its queues."""
        with self._lock:
            if agent_id in self._queues:
                self._queues[agent_id].clear()
                del self._queues[agent_id]

            # Remove from all subscriptions
            for topic in self._subscribers:
                self._subscribers[topic].discard(agent_id)

    def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe an agent to a topic."""
        with self._lock:
            self._subscribers[topic].add(agent_id)

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic."""
        with self._lock:
            self._subscribers[topic].discard(agent_id)

    def send(
        self,
        message: AgentMessage,
        timeout: float = 1.0,
    ) -> bool:
        """Send a message to a specific recipient."""
        if not message.recipient_id:
            return False

        with self._lock:
            queue = self._queues.get(message.recipient_id)
            if not queue:
                return False

            success = queue.put_inbound(message, timeout=timeout)

            # Add to history
            if success:
                self._add_to_history(message)

            return success

    def broadcast(
        self,
        message: AgentMessage,
        exclude_sender: bool = True,
        timeout: float = 1.0,
    ) -> int:
        """Broadcast a message to all agents."""
        with self._lock:
            count = 0
            for agent_id, queue in self._queues.items():
                if exclude_sender and agent_id == message.sender_id:
                    continue

                msg = AgentMessage(**message.to_dict())
                msg.recipient_id = agent_id

                if queue.put_inbound(msg, timeout=timeout):
                    count += 1

            self._add_to_history(message)
            return count

    def publish(
        self,
        topic: str,
        message: AgentMessage,
        timeout: float = 1.0,
    ) -> int:
        """Publish a message to a topic (all subscribers)."""
        with self._lock:
            subscribers = self._subscribers.get(topic, set())
            count = 0

            for agent_id in subscribers:
                queue = self._queues.get(agent_id)
                if not queue:
                    continue

                msg = AgentMessage(**message.to_dict())
                msg.recipient_id = agent_id
                msg.payload["topic"] = topic

                if queue.put_inbound(msg, timeout=timeout):
                    count += 1

            return count

    def request(
        self,
        message: AgentMessage,
        timeout: float = 5.0,
    ) -> AgentMessage | None:
        """Send a request and wait for a response."""
        if not message.correlation_id:
            message.correlation_id = str(uuid.uuid4())

        # Send the request
        if not self.send(message):
            return None

        # Create a temporary queue for responses
        reply_queue = Queue[AgentMessage]()

        # Register a callback for this request
        def callback(response: AgentMessage) -> bool:
            if response.correlation_id == message.correlation_id:
                reply_queue.put(response)
                return True
            return False

        # Wait for response (simplified - in production would use proper async)
        start = time.time()
        while time.time() - start < timeout:
            # Check if we got a response
            try:
                return reply_queue.get_nowait()
            except Empty:
                time.sleep(0.01)

        return None

    def get_message(
        self,
        agent_id: str,
        timeout: float = 1.0,
    ) -> AgentMessage | None:
        """Get the next message for an agent."""
        with self._lock:
            queue = self._queues.get(agent_id)
            if not queue:
                return None
            return queue.get_inbound(timeout=timeout)

    def send_message(
        self,
        message: AgentMessage,
        timeout: float = 1.0,
    ) -> bool:
        """Send an outbound message from an agent."""
        if not message.sender_id:
            return False

        with self._lock:
            queue = self._queues.get(message.sender_id)
            if not queue:
                return False

            return queue.put_outbound(message, timeout=timeout)

    def start_delivery(self) -> None:
        """Start the background delivery thread."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._delivery_thread = threading.Thread(
                target=self._delivery_loop,
                daemon=True,
            )
            self._delivery_thread.start()

    def stop_delivery(self) -> None:
        """Stop the background delivery thread."""
        with self._lock:
            self._running = False
            if self._delivery_thread:
                self._delivery_thread.join(timeout=2.0)
                self._delivery_thread = None

    def _delivery_loop(self) -> None:
        """Background thread that delivers outbound messages."""
        while self._running:
            try:
                # Process outbound queues
                with self._lock:
                    for _agent_id, queue in self._queues.items():
                        msg = queue.get_outbound(timeout=0.1)
                        if msg:
                            self.send(msg, timeout=0.1)

                time.sleep(0.01)
            except Exception:
                pass

    def _add_to_history(self, message: AgentMessage) -> None:
        """Add a message to the history buffer."""
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(
        self,
        agent_id: str | None = None,
        msg_type: MessageType | None = None,
        limit: int = 100,
    ) -> list[AgentMessage]:
        """Get message history with optional filters."""
        with self._lock:
            results = self._history

            if agent_id:
                results = [
                    m for m in results if m.sender_id == agent_id or m.recipient_id == agent_id
                ]

            if msg_type:
                results = [m for m in results if m.msg_type == msg_type]

            return results[-limit:]

    def get_queue_sizes(self) -> dict[str, tuple[int, int]]:
        """Get the size of all agent queues."""
        with self._lock:
            return {agent_id: queue.size() for agent_id, queue in self._queues.items()}

    def get_bus_stats(self) -> dict[str, Any]:
        """Get statistics about the communication bus."""
        with self._lock:
            return {
                "registered_agents": len(self._queues),
                "topics": len(self._subscribers),
                "total_messages": len(self._history),
                "queue_sizes": self.get_queue_sizes(),
                "running": self._running,
            }
