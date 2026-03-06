"""
ControlPlane Agent for Execution and Rollback Management.

This agent handles task execution, steps, and rollback operations.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..base import Agent, AgentCapability


@dataclass
class PatchReport:
    """Report from a patching operation."""

    patch_id: str
    status: str
    files_modified: list[str]
    rollback_points: list[str]
    errors: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class ControlPlaneAgent(Agent):
    """Agent for control plane operations (execution, steps, rollback)."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="execute_steps",
                description="Execute a series of steps",
                input_types=["repair_plan", "steps"],
                output_types=["patch_report"],
            ),
            AgentCapability(
                name="create_rollback_point",
                description="Create a rollback point",
                input_types=["project_root"],
                output_types=["rollback_point"],
            ),
            AgentCapability(
                name="rollback",
                description="Rollback to a previous state",
                input_types=["rollback_point"],
                output_types=["rollback_result"],
            ),
            AgentCapability(
                name="validate_changes",
                description="Validate changes before applying",
                input_types=["changes"],
                output_types=["validation_result"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._rollback_points: dict[str, dict[str, Any]] = {}
        self._execution_history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        """Initialize the control plane agent."""
        # Load rollback points if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            state_path = Path(state_dir)
            if state_path.exists():
                await self._load_rollback_points(state_path)

    async def shutdown(self) -> None:
        """Shutdown the control plane agent."""
        # Save rollback points if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            state_path = Path(state_dir)
            state_path.mkdir(parents=True, exist_ok=True)
            await self._save_rollback_points(state_path)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "execute_steps":
                return await self._task_execute_steps(payload, context)
            elif task_type == "create_rollback_point":
                return await self._task_create_rollback_point(payload, context)
            elif task_type == "rollback":
                return await self._task_rollback(payload, context)
            elif task_type == "validate_changes":
                return await self._task_validate_changes(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_execute_steps(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Execute a series of steps."""
        steps = payload.get("steps", [])
        project_root = payload.get("project_root")

        if not steps:
            raise ValueError("steps are required")

        # Create rollback point before execution
        rollback_result = await self._task_create_rollback_point(
            {"project_root": project_root},
            context,
        )
        rollback_point_id = rollback_result.get("rollback_point_id")

        files_modified = []
        errors = []

        # Execute each step
        for step in steps:
            try:
                result = await self._execute_step(step, context)
                files_modified.extend(result.get("files_modified", []))
            except Exception as e:
                errors.append(f"Step {step.get('name', 'unknown')} failed: {str(e)}")
                break

        # Create patch report
        report = PatchReport(
            patch_id=f"patch_{int(time.time())}_{self.agent_id}",
            status="success" if not errors else "partial",
            files_modified=files_modified,
            rollback_points=[rollback_point_id] if rollback_point_id else [],
            errors=errors,
            metadata={
                "step_count": len(steps),
                "completed_steps": len(files_modified),
                "created_by": self.agent_id,
            },
        )

        # Record execution
        with self._lock:
            self._execution_history.append(
                {
                    "patch_id": report.patch_id,
                    "timestamp": time.time(),
                    "steps": steps,
                    "report": report.__dict__,
                }
            )

        return {
            "success": not errors,
            "patch_report": report.__dict__,
            "rollback_point_id": rollback_point_id,
        }

    async def _task_create_rollback_point(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Create a rollback point."""
        project_root = payload.get("project_root")
        if not project_root:
            raise ValueError("project_root is required")

        # In a real implementation, this would:
        # 1. Create a snapshot of the project state
        # 2. Store file contents that will be modified
        # 3. Save git commits or other state markers

        rollback_point_id = f"rollback_{int(time.time())}_{self.agent_id}"

        rollback_point = {
            "rollback_point_id": rollback_point_id,
            "project_root": project_root,
            "timestamp": time.time(),
            "created_by": self.agent_id,
            # In production, would include actual rollback data
            "snapshot_data": {},
        }

        with self._lock:
            self._rollback_points[rollback_point_id] = rollback_point

        return {
            "success": True,
            "rollback_point_id": rollback_point_id,
        }

    async def _task_rollback(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Rollback to a previous state."""
        rollback_point_id = payload.get("rollback_point_id")
        if not rollback_point_id:
            raise ValueError("rollback_point_id is required")

        with self._lock:
            rollback_point = self._rollback_points.get(rollback_point_id)

        if not rollback_point:
            raise ValueError(f"Rollback point not found: {rollback_point_id}")

        # In a real implementation, this would:
        # 1. Restore file contents from snapshot
        # 2. Revert git commits
        # 3. Clean up any artifacts

        return {
            "success": True,
            "rollback_point_id": rollback_point_id,
            "rolled_back": True,
        }

    async def _task_validate_changes(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Validate changes before applying."""
        changes = payload.get("changes", [])

        if not changes:
            raise ValueError("changes are required")

        validation_results = []
        all_valid = True

        for change in changes:
            result = await self._validate_change(change, context)
            validation_results.append(result)
            if not result.get("valid", False):
                all_valid = False

        return {
            "success": all_valid,
            "all_valid": all_valid,
            "validation_results": validation_results,
        }

    async def _execute_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single step."""
        step_type = step.get("type", "generic")

        if step_type == "file_write":
            return await self._step_file_write(step, context)
        elif step_type == "file_delete":
            return await self._step_file_delete(step, context)
        elif step_type == "command":
            return await self._step_command(step, context)
        else:
            raise ValueError(f"Unknown step type: {step_type}")

    async def _step_file_write(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a file write step."""
        file_path = step.get("file_path")
        content = step.get("content")

        if not file_path or content is None:
            raise ValueError("file_path and content are required")

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "files_modified": [file_path],
        }

    async def _step_file_delete(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a file delete step."""
        file_path = step.get("file_path")

        if not file_path:
            raise ValueError("file_path is required")

        path = Path(file_path)

        if path.exists():
            path.unlink()

        return {
            "success": True,
            "files_modified": [file_path],
        }

    async def _step_command(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a command step."""
        # In a real implementation, this would execute shell commands
        # For now, just simulate success
        command = step.get("command", "")
        return {
            "success": True,
            "command": command,
            "files_modified": [],
        }

    async def _validate_change(
        self,
        change: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate a single change."""
        change_type = change.get("type", "generic")

        if change_type == "file_write":
            file_path = change.get("file_path")
            if not file_path:
                return {
                    "valid": False,
                    "reason": "file_path is required",
                }

            # Check for path traversal
            if ".." in Path(file_path).parts:
                return {
                    "valid": False,
                    "reason": "Path traversal detected",
                }

            return {"valid": True}

        return {
            "valid": True,
            "reason": "No validation performed for this change type",
        }

    async def _load_rollback_points(self, state_dir: Path) -> None:
        """Load rollback points from state directory."""
        # Implementation would load from JSON file
        pass

    async def _save_rollback_points(self, state_dir: Path) -> None:
        """Save rollback points to state directory."""
        # Implementation would save to JSON file
        pass

    def get_rollback_point(self, rollback_point_id: str) -> dict[str, Any] | None:
        """Get a rollback point by ID."""
        with self._lock:
            return self._rollback_points.get(rollback_point_id)

    def list_rollback_points(self) -> list[dict[str, Any]]:
        """List all rollback points."""
        with self._lock:
            return list(self._rollback_points.values())
