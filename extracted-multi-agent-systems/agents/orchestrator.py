"""
Multi-Agent Orchestrator for Complete System Integration.

This module provides the orchestrator that coordinates all agents
in the IndestructibleAutoOps system, from task distribution to
policy enforcement and observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .communication import AgentCommunicationBus
from .concrete import (
    ControlPlaneAgent,
    DataPlaneAgent,
    DeliveryAgent,
    ObservabilityAgent,
    PolicyAgent,
    ReasoningAgent,
)
from .coordination import AgentCoordinator, Task, TaskStatus
from .lifecycle import AgentLifecycle
from .policy_engine import Policy, PolicyEngine
from .registry import AgentRegistry


@dataclass
class OrchestratorConfig:
    """Configuration for the multi-agent orchestrator."""

    project_root: str
    state_dir: str | None = None
    max_concurrent_tasks: int = 10
    enable_observability: bool = True
    enable_policy_enforcement: bool = True
    auto_spawn_agents: bool = True


@dataclass
class OrchestrationResult:
    """Result of an orchestration operation."""

    success: bool
    task_ids: list[str]
    tasks_completed: int
    tasks_failed: int
    total_duration: float
    errors: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)


class MultiAgentOrchestrator:
    """Main orchestrator for multi-agent coordination."""

    def __init__(self, config: OrchestratorConfig):
        self.config = config

        # Core components
        self.registry = AgentRegistry()
        self.communication = AgentCommunicationBus()
        self.coordinator = AgentCoordinator(
            self.registry,
            self.communication,
            max_concurrent_tasks=config.max_concurrent_tasks,
        )
        self.lifecycle = AgentLifecycle(
            self.registry,
            self.communication,
        )

        # Policy engine
        self.policy_engine = PolicyEngine()

        # Start communication
        self.communication.start_delivery()

        # Register agent types
        self._register_agent_types()

    def _register_agent_types(self) -> None:
        """Register agent types with lifecycle manager."""
        self.lifecycle.register_agent_type("data_plane", DataPlaneAgent)
        self.lifecycle.register_agent_type("control_plane", ControlPlaneAgent)
        self.lifecycle.register_agent_type("reasoning", ReasoningAgent)
        self.lifecycle.register_agent_type("policy", PolicyAgent)
        self.lifecycle.register_agent_type("delivery", DeliveryAgent)
        self.lifecycle.register_agent_type("observability", ObservabilityAgent)

    async def initialize(
        self,
        spawn_all_agents: bool = True,
    ) -> None:
        """Initialize the orchestrator and spawn agents."""
        if spawn_all_agents:
            await self.spawn_default_agents()

        # Start monitoring
        self.lifecycle.start_monitoring()

        # Start coordinator
        self.coordinator.start()

    async def spawn_default_agents(self) -> None:
        """Spawn the default set of agents."""
        # Spawn core agents
        await self.lifecycle.spawn_agent(
            agent_type="data_plane",
            agent_id="data_plane_1",
            config={
                "project_root": self.config.project_root,
                "state_dir": self.config.state_dir,
            },
            tags=["data", "filesystem"],
        )

        await self.lifecycle.spawn_agent(
            agent_type="control_plane",
            agent_id="control_plane_1",
            config={
                "project_root": self.config.project_root,
                "state_dir": self.config.state_dir,
            },
            tags=["control", "execution"],
        )

        await self.lifecycle.spawn_agent(
            agent_type="reasoning",
            agent_id="reasoning_1",
            config={
                "state_dir": self.config.state_dir,
            },
            tags=["reasoning", "planning"],
        )

        await self.lifecycle.spawn_agent(
            agent_type="policy",
            agent_id="policy_1",
            config={
                "state_dir": self.config.state_dir,
            },
            tags=["policy", "governance"],
        )

        await self.lifecycle.spawn_agent(
            agent_type="delivery",
            agent_id="delivery_1",
            config={
                "state_dir": self.config.state_dir,
            },
            tags=["delivery", "cicd"],
        )

        if self.config.enable_observability:
            await self.lifecycle.spawn_agent(
                agent_type="observability",
                agent_id="observability_1",
                config={
                    "state_dir": self.config.state_dir,
                    "aggregate_metrics": True,
                },
                tags=["observability", "metrics"],
            )

    async def shutdown(self) -> None:
        """Shutdown the orchestrator and all agents."""
        # Stop coordinator
        self.coordinator.stop()

        # Stop monitoring
        self.lifecycle.stop_monitoring()

        # Terminate all agents
        await self.lifecycle.terminate_all(graceful=True)

        # Stop communication
        self.communication.stop_delivery()

    async def execute_pipeline(
        self,
        pipeline_steps: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """Execute a pipeline with multiple steps."""
        import time

        start_time = time.time()
        context = context or {}
        errors = []

        # Create tasks from pipeline steps
        tasks = []
        for step in pipeline_steps:
            task = Task(
                task_type=step.get("type", "generic"),
                payload=step.get("payload", {}),
                required_capabilities=step.get("required_capabilities", []),
                required_tags=step.get("required_tags", []),
                priority=step.get("priority", 0),
                context=context,
            )
            tasks.append(task)

        # Submit tasks
        task_ids = self.coordinator.submit_tasks(tasks)

        # Wait for completion
        results = self.coordinator.wait_for_tasks(task_ids)

        # Process results
        tasks_completed = 0
        tasks_failed = 0

        for task_id, result in results.items():
            if result.status == TaskStatus.COMPLETED:
                tasks_completed += 1
                # Update context with result
                context[f"task_{task_id}_result"] = result.result
            else:
                tasks_failed += 1
                errors.append(result.error or "Unknown error")

        total_duration = time.time() - start_time

        # Collect metrics if observability enabled
        metrics = {}
        if self.config.enable_observability:
            metrics = await self._collect_execution_metrics(task_ids)

        return OrchestrationResult(
            success=tasks_failed == 0,
            task_ids=task_ids,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            total_duration=total_duration,
            errors=errors,
            metrics=metrics,
        )

    async def analyze_project(
        self,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a project using the multi-agent system."""
        project_root = project_root or self.config.project_root
        context = {"project_root": project_root}

        # Step 1: Create project snapshot (DataPlane)
        snapshot_task = Task(
            task_type="create_snapshot",
            payload={
                "project_root": project_root,
                "state_dir": self.config.state_dir,
            },
            required_capabilities=["create_snapshot"],
            context=context,
        )
        snapshot_id = self.coordinator.submit_task(snapshot_task)
        snapshot_result = self.coordinator.wait_for_task(snapshot_id)

        if not snapshot_result or snapshot_result.status != TaskStatus.COMPLETED:
            return {
                "success": False,
                "error": "Failed to create snapshot",
            }

        snapshot = snapshot_result.result.get("snapshot")

        # Step 2: Analyze risks (Reasoning)
        risk_task = Task(
            task_type="analyze_risks",
            payload={
                "project_snapshot": snapshot,
            },
            required_capabilities=["analyze_risks"],
            context=context,
        )
        risk_id = self.coordinator.submit_task(risk_task)
        risk_result = self.coordinator.wait_for_task(risk_id)

        # Step 3: Evaluate policies (Policy)
        policy_task = Task(
            task_type="evaluate_policies",
            payload={
                "project_snapshot": snapshot,
                "context": context,
            },
            required_capabilities=["evaluate_policies"],
            context=context,
        )
        policy_id = self.coordinator.submit_task(policy_task)
        policy_result = self.coordinator.wait_for_task(policy_id)

        return {
            "success": True,
            "snapshot": snapshot,
            "risk_findings": risk_result.result if risk_result else None,
            "policy_evaluation": policy_result.result if policy_result else None,
        }

    async def create_repair_plan(
        self,
        project_root: str | None = None,
    ) -> dict[str, Any]:
        """Create a repair plan for a project."""
        # First analyze the project
        analysis = await self.analyze_project(project_root)

        if not analysis["success"]:
            return analysis

        snapshot = analysis["snapshot"]

        # Create repair plan
        plan_task = Task(
            task_type="create_repair_plan",
            payload={
                "project_snapshot": snapshot,
                "policy_set": analysis.get("policy_evaluation", {}),
            },
            required_capabilities=["create_repair_plan"],
            context={"project_root": project_root or self.config.project_root},
        )
        plan_id = self.coordinator.submit_task(plan_task)
        plan_result = self.coordinator.wait_for_task(plan_id)

        return {
            "success": plan_result and plan_result.status == TaskStatus.COMPLETED,
            "repair_plan": plan_result.result if plan_result else None,
            "analysis": analysis,
        }

    async def execute_repair(
        self,
        repair_plan: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a repair plan."""
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "message": "Dry run - no changes made",
            }

        steps = repair_plan.get("steps", [])

        # Execute repair steps
        repair_task = Task(
            task_type="execute_steps",
            payload={
                "steps": steps,
                "project_root": self.config.project_root,
            },
            required_capabilities=["execute_steps"],
            context={},
        )
        repair_id = self.coordinator.submit_task(repair_task)
        repair_result = self.coordinator.wait_for_task(repair_id)

        return {
            "success": repair_result and repair_result.status == TaskStatus.COMPLETED,
            "result": repair_result.result if repair_result else None,
        }

    async def generate_ci_config(
        self,
        provider: str = "github",
    ) -> dict[str, Any]:
        """Generate CI/CD configuration."""
        # First create snapshot
        analysis = await self.analyze_project()

        if not analysis["success"]:
            return analysis

        snapshot = analysis["snapshot"]

        # Generate CI config
        ci_task = Task(
            task_type="generate_ci_config",
            payload={
                "project_snapshot": snapshot,
                "provider": provider,
            },
            required_capabilities=["generate_ci_config"],
            context={},
        )
        ci_id = self.coordinator.submit_task(ci_task)
        ci_result = self.coordinator.wait_for_task(ci_id)

        return {
            "success": ci_result and ci_result.status == TaskStatus.COMPLETED,
            "ci_config": ci_result.result if ci_result else None,
        }

    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine."""
        self.policy_engine.add_policy(policy)

        # Also add to policy agent if available
        policy_agent = self.registry.get_agent("policy_1")
        if policy_agent and isinstance(policy_agent, PolicyAgent):
            policy_agent.add_policy(policy)

    def get_orchestrator_stats(self) -> dict[str, Any]:
        """Get statistics about the orchestrator."""
        return {
            "registry": self.registry.get_registry_stats(),
            "coordinator": self.coordinator.get_coordinator_stats(),
            "lifecycle": self.lifecycle.get_lifecycle_stats(),
            "communication": self.communication.get_bus_stats(),
            "policy_engine": self.policy_engine.get_engine_stats(),
        }

    async def _collect_execution_metrics(
        self,
        task_ids: list[str],
    ) -> dict[str, Any]:
        """Collect metrics from execution."""
        metrics = {
            "total_tasks": len(task_ids),
        }

        # Get task results
        for task_id in task_ids:
            result = self.coordinator.get_result(task_id)
            if result:
                metrics[f"task_{task_id}_duration"] = result.duration

        return metrics


async def create_orchestrator(
    project_root: str,
    state_dir: str | None = None,
    **kwargs,
) -> MultiAgentOrchestrator:
    """Factory function to create and initialize an orchestrator."""
    config = OrchestratorConfig(
        project_root=project_root,
        state_dir=state_dir,
        **kwargs,
    )

    orchestrator = MultiAgentOrchestrator(config)
    await orchestrator.initialize()

    return orchestrator
