"""
Agent Coordination Engine for Task Distribution and Execution.

This module provides the AgentCoordinator class which manages
task scheduling, distribution, and execution across multiple agents.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import AgentMessage, MessageType
from .communication import AgentCommunicationBus
from .registry import AgentRegistry


class TaskStatus(Enum):
    """Status of a task in the coordination system."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class Task:
    """A task that can be executed by an agent."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    required_tags: list[str] = field(default_factory=list)
    priority: int = 0
    timeout: float = 300.0
    max_retries: int = 3
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    assigned_to: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "required_capabilities": self.required_capabilities,
            "required_tags": self.required_tags,
            "priority": self.priority,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "assigned_to": self.assigned_to,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "context": self.context,
        }


@dataclass
class TaskResult:
    """Result of a task execution."""

    task_id: str
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    agent_id: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    duration: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration,
        }


@dataclass
class AgentSelection:
    """Result of agent selection for a task."""

    agent_id: str
    score: float
    reasons: list[str] = field(default_factory=list)


class AgentCoordinator:
    """Coordinates task execution across multiple agents."""

    def __init__(
        self,
        registry: AgentRegistry,
        communication: AgentCommunicationBus,
        max_concurrent_tasks: int = 10,
    ):
        self.registry = registry
        self.communication = communication
        self.max_concurrent_tasks = max_concurrent_tasks

        self._tasks: dict[str, Task] = {}
        self._results: dict[str, TaskResult] = {}
        self._running_tasks: dict[str, str] = {}  # task_id -> agent_id
        self._pending_tasks: list[str] = []
        self._completed_tasks: list[str] = []

        self._lock = threading.RLock()
        self._running = False
        self._scheduler_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the coordination system."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
            )
            self._scheduler_thread.start()

    def stop(self) -> None:
        """Stop the coordination system."""
        with self._lock:
            self._running = False
            if self._scheduler_thread:
                self._scheduler_thread.join(timeout=5.0)
                self._scheduler_thread = None

    def submit_task(self, task: Task) -> str:
        """Submit a task for execution."""
        with self._lock:
            self._tasks[task.task_id] = task
            self._pending_tasks.append(task.task_id)
            return task.task_id

    def submit_tasks(self, tasks: Iterable[Task]) -> list[str]:
        """Submit multiple tasks for execution."""
        task_ids = []
        with self._lock:
            for task in tasks:
                self._tasks[task.task_id] = task
                self._pending_tasks.append(task.task_id)
                task_ids.append(task.task_id)
        return task_ids

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task = self._tasks[task_id]

            # Can only cancel pending tasks
            if task.status != TaskStatus.PENDING:
                return False

            task.status = TaskStatus.CANCELLED

            if task_id in self._pending_tasks:
                self._pending_tasks.remove(task_id)

            return True

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get the result of a task."""
        with self._lock:
            return self._results.get(task_id)

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """Get the status of a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.status if task else None

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
    ) -> list[Task]:
        """List tasks with optional filters."""
        with self._lock:
            tasks = list(self._tasks.values())

            if status:
                tasks = [t for t in tasks if t.status == status]

            if agent_id:
                tasks = [t for t in tasks if t.assigned_to == agent_id]

            return tasks

    def wait_for_task(
        self,
        task_id: str,
        timeout: float = 300.0,
    ) -> TaskResult | None:
        """Wait for a task to complete."""
        start = time.time()

        while time.time() - start < timeout:
            with self._lock:
                result = self._results.get(task_id)
                if result:
                    if result.status in (
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                        TaskStatus.CANCELLED,
                    ):
                        return result

            time.sleep(0.1)

        return None

    def wait_for_tasks(
        self,
        task_ids: list[str],
        timeout: float = 300.0,
    ) -> dict[str, TaskResult]:
        """Wait for multiple tasks to complete."""
        results: dict[str, TaskResult] = {}
        start = time.time()

        while time.time() - start < timeout and len(results) < len(task_ids):
            for task_id in task_ids:
                if task_id not in results:
                    with self._lock:
                        result = self._results.get(task_id)
                        if result and result.status in (
                            TaskStatus.COMPLETED,
                            TaskStatus.FAILED,
                            TaskStatus.CANCELLED,
                        ):
                            results[task_id] = result

            time.sleep(0.1)

        return results

    def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                self._schedule_tasks()
                self._monitor_tasks()
                time.sleep(0.1)
            except Exception:
                pass

    def _schedule_tasks(self) -> None:
        """Schedule pending tasks to available agents."""
        with self._lock:
            # Check if we have capacity
            if len(self._running_tasks) >= self.max_concurrent_tasks:
                return

            # Get ready tasks (dependencies satisfied)
            ready_tasks = []
            for task_id in self._pending_tasks:
                task = self._tasks[task_id]
                if self._are_dependencies_satisfied(task):
                    ready_tasks.append(task)

            # Sort by priority (higher first)
            ready_tasks.sort(key=lambda t: t.priority, reverse=True)

            # Schedule as many as we can
            for task in ready_tasks[: self.max_concurrent_tasks - len(self._running_tasks)]:
                agent = self._select_agent_for_task(task)
                if agent:
                    self._assign_task_to_agent(task, agent)

    def _monitor_tasks(self) -> None:
        """Monitor running tasks for timeouts."""
        with self._lock:
            now = time.time()

            for task_id, agent_id in list(self._running_tasks.items()):
                task = self._tasks.get(task_id)
                if not task:
                    continue

                # Check for timeout
                if now - task.created_at > task.timeout:
                    self._handle_task_timeout(task, agent_id)

    def _select_agent_for_task(self, task: Task) -> AgentSelection | None:
        """Select the best agent for a task."""
        # Find agents with required capabilities
        candidates = self.registry.find_by_capabilities(task.required_capabilities)

        if not candidates:
            return None

        # Filter by tags if specified
        if task.required_tags:
            tagged_candidates = []
            for agent_id in candidates:
                metadata = self.registry.get_metadata(agent_id)
                if metadata and all(tag in metadata.tags for tag in task.required_tags):
                    tagged_candidates.append(agent_id)
            candidates = tagged_candidates

        if not candidates:
            return None

        # Score candidates
        scored = []
        for agent_id in candidates:
            metadata = self.registry.get_metadata(agent_id)
            if not metadata or metadata.state != "idle":
                continue

            score = 0.0
            reasons = []

            # Prefer idle agents
            if metadata.state == "idle":
                score += 10.0
                reasons.append("agent_idle")

            # Consider load (fewer running tasks is better)
            running_count = sum(1 for t in self._running_tasks.values() if t == agent_id)
            score -= running_count * 2.0
            if running_count == 0:
                reasons.append("no_load")

            # Consider task completion history
            # (simplified - in production would use more sophisticated metrics)

            scored.append(AgentSelection(agent_id=agent_id, score=score, reasons=reasons))

        if not scored:
            return None

        # Return the best candidate
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[0]

    def _assign_task_to_agent(self, task: Task, selection: AgentSelection) -> None:
        """Assign a task to an agent."""
        task.assigned_to = selection.agent_id
        task.status = TaskStatus.ASSIGNED

        self._running_tasks[task.task_id] = selection.agent_id
        if task.task_id in self._pending_tasks:
            self._pending_tasks.remove(task.task_id)

        # Send task assignment message
        message = AgentMessage(
            msg_type=MessageType.TASK_ASSIGN,
            sender_id="coordinator",
            recipient_id=selection.agent_id,
            payload={
                "task": task.to_dict(),
                "context": task.context,
            },
        )

        self.communication.send(message)

        # Update registry
        self.registry.update_agent_state(selection.agent_id, "busy")

    def _handle_task_complete(
        self,
        task_id: str,
        result: TaskResult,
    ) -> None:
        """Handle a completed task."""
        with self._lock:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

            task = self._tasks.get(task_id)
            if task:
                task.status = result.status
                if result.agent_id:
                    self.registry.update_agent_state(result.agent_id, "idle")

            self._results[task_id] = result
            self._completed_tasks.append(task_id)

    def _handle_task_timeout(self, task: Task, agent_id: str) -> None:
        """Handle a task that has timed out."""
        if task.retry_count < task.max_retries:
            # Retry the task
            task.retry_count += 1
            task.status = TaskStatus.RETRYING
            task.assigned_to = None

            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]

            self._pending_tasks.append(task.task_id)
            self.registry.update_agent_state(agent_id, "idle")
        else:
            # Mark as failed
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error="Task timed out",
                agent_id=agent_id,
            )
            self._handle_task_complete(task.task_id, result)

    def _are_dependencies_satisfied(self, task: Task) -> bool:
        """Check if all task dependencies are satisfied."""
        for dep_id in task.depends_on:
            dep_result = self._results.get(dep_id)
            if not dep_result or dep_result.status != TaskStatus.COMPLETED:
                return False
        return True

    def get_coordinator_stats(self) -> dict[str, Any]:
        """Get statistics about the coordinator."""
        with self._lock:
            return {
                "total_tasks": len(self._tasks),
                "pending_tasks": len(self._pending_tasks),
                "running_tasks": len(self._running_tasks),
                "completed_tasks": len(self._completed_tasks),
                "max_concurrent": self.max_concurrent_tasks,
                "running": self._running,
            }
