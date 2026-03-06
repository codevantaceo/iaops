"""
Reasoning Agent for Planning and DAG Analysis.

This agent handles repair planning, risk assessment, and DAG analysis.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..base import Agent, AgentCapability


@dataclass
class RepairPlan:
    """Plan for repairing a project."""

    plan_id: str
    issues_found: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    risk_assessment: dict[str, Any]
    estimated_duration: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskFindings:
    """Risk assessment findings."""

    total_risks: int
    by_severity: dict[str, int]
    risks: list[dict[str, Any]]
    recommendations: list[str]


class ReasoningAgent(Agent):
    """Agent for reasoning and planning operations."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="create_repair_plan",
                description="Create a repair plan from project analysis",
                input_types=["project_snapshot", "policy_set"],
                output_types=["repair_plan"],
            ),
            AgentCapability(
                name="analyze_risks",
                description="Analyze risks in a project",
                input_types=["project_snapshot"],
                output_types=["risk_findings"],
            ),
            AgentCapability(
                name="validate_dag",
                description="Validate a DAG structure",
                input_types=["dag_definition"],
                output_types=["dag_validation"],
            ),
            AgentCapability(
                name="optimize_execution",
                description="Optimize execution order and parallelism",
                input_types=["dag_definition", "resource_constraints"],
                output_types=["optimized_plan"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._repair_plans: dict[str, RepairPlan] = {}
        self._risk_assessments: dict[str, RiskFindings] = {}
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        """Initialize the reasoning agent."""
        # Load previous plans if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            await self._load_plans(state_dir)

    async def shutdown(self) -> None:
        """Shutdown the reasoning agent."""
        # Save plans if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            await self._save_plans(state_dir)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "create_repair_plan":
                return await self._task_create_repair_plan(payload, context)
            elif task_type == "analyze_risks":
                return await self._task_analyze_risks(payload, context)
            elif task_type == "validate_dag":
                return await self._task_validate_dag(payload, context)
            elif task_type == "optimize_execution":
                return await self._task_optimize_execution(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_create_repair_plan(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Create a repair plan."""
        project_snapshot = payload.get("project_snapshot")
        policy_set = payload.get("policy_set", {})

        if not project_snapshot:
            raise ValueError("project_snapshot is required")

        # Analyze issues
        issues = await self._analyze_issues(project_snapshot, policy_set)

        # Create steps to fix issues
        steps = await self._create_fix_steps(issues, context)

        # Assess risks
        risk_assessment = await self._assess_plan_risks(steps, context)

        # Create plan
        plan = RepairPlan(
            plan_id=f"plan_{int(time.time())}_{self.agent_id}",
            issues_found=issues,
            steps=steps,
            risk_assessment=risk_assessment,
            estimated_duration=len(steps) * 30.0,  # Estimate 30s per step
            metadata={
                "created_by": self.agent_id,
                "project_root": project_snapshot.get("project_root"),
            },
        )

        with self._lock:
            self._repair_plans[plan.plan_id] = plan

        return {
            "success": True,
            "repair_plan": plan.__dict__,
        }

    async def _task_analyze_risks(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Analyze risks in a project."""
        project_snapshot = payload.get("project_snapshot")

        if not project_snapshot:
            raise ValueError("project_snapshot is required")

        # Analyze various risk categories
        risks = []
        recommendations = []

        # File structure risks
        file_index = project_snapshot.get("file_index", {})
        risks.extend(await self._analyze_file_structure_risks(file_index))

        # Content risks
        risks.extend(await self._analyze_content_risks(file_index, context))

        # Dependency risks
        risks.extend(await self._analyze_dependency_risks(file_index, context))

        # Categorize by severity
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for risk in risks:
            severity = risk.get("severity", "low")
            by_severity[severity] = by_severity.get(severity, 0) + 1

        # Generate recommendations
        recommendations = await self._generate_recommendations(risks, context)

        findings = RiskFindings(
            total_risks=len(risks),
            by_severity=by_severity,
            risks=risks,
            recommendations=recommendations,
        )

        return {
            "success": True,
            "risk_findings": findings.__dict__,
        }

    async def _task_validate_dag(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Validate a DAG structure."""
        dag_definition = payload.get("dag_definition")

        if not dag_definition:
            raise ValueError("dag_definition is required")

        nodes = dag_definition.get("nodes", [])
        edges = dag_definition.get("edges", [])

        errors = []
        warnings = []

        # Check for cycles
        has_cycle = await self._detect_cycle(nodes, edges)
        if has_cycle:
            errors.append("DAG contains cycles")

        # Check for orphan nodes
        referenced_nodes = set()
        for edge in edges:
            referenced_nodes.add(edge[0])
            referenced_nodes.add(edge[1])

        orphan_nodes = [n for n in nodes if n not in referenced_nodes]
        if orphan_nodes:
            warnings.append(f"Orphan nodes detected: {orphan_nodes}")

        # Check for missing dependencies
        for edge in edges:
            if edge[0] not in nodes:
                errors.append(f"Edge references missing node: {edge[0]}")
            if edge[1] not in nodes:
                errors.append(f"Edge references missing node: {edge[1]}")

        return {
            "success": not errors,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        }

    async def _task_optimize_execution(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Optimize execution order and parallelism."""
        dag_definition = payload.get("dag_definition")
        resource_constraints = payload.get("resource_constraints", {})

        if not dag_definition:
            raise ValueError("dag_definition is required")

        # Compute topological order
        nodes = dag_definition.get("nodes", [])
        edges = dag_definition.get("edges", [])

        execution_order = await self._topological_sort(nodes, edges)

        # Identify parallel tasks
        parallel_groups = await self._identify_parallel_groups(nodes, edges)

        # Apply resource constraints
        max_parallel = resource_constraints.get("max_parallel", 4)
        optimized_groups = await self._apply_resource_limits(
            parallel_groups,
            max_parallel,
        )

        return {
            "success": True,
            "execution_order": execution_order,
            "parallel_groups": optimized_groups,
            "estimated_parallelism": sum(len(g) for g in optimized_groups) / len(optimized_groups),
        }

    async def _analyze_issues(
        self,
        project_snapshot: dict[str, Any],
        policy_set: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Analyze issues in a project."""
        issues = []
        file_index = project_snapshot.get("file_index", {})

        # Check for security issues
        for path, _info in file_index.items():
            # Check for sensitive file extensions
            if any(ext in path.lower() for ext in [".env", ".secret", ".key", ".pem"]):
                issues.append(
                    {
                        "type": "security",
                        "severity": "high",
                        "path": path,
                        "description": "Potentially sensitive file detected",
                    }
                )

        # Check for missing essential files
        essential_files = ["README.md", "LICENSE"]
        for essential in essential_files:
            if essential not in file_index:
                issues.append(
                    {
                        "type": "documentation",
                        "severity": "low",
                        "path": essential,
                        "description": f"Missing essential file: {essential}",
                    }
                )

        return issues

    async def _create_fix_steps(
        self,
        issues: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Create fix steps for issues."""
        steps = []

        for issue in issues:
            if issue["type"] == "security":
                steps.append(
                    {
                        "type": "review",
                        "name": f"Review security issue: {issue['path']}",
                        "description": issue["description"],
                        "action": "manual_review",
                        "priority": "high",
                    }
                )
            elif issue["type"] == "documentation":
                steps.append(
                    {
                        "type": "file_write",
                        "name": f"Create {issue['path']}",
                        "file_path": issue["path"],
                        "content": f"# {issue['path']}\n",
                        "priority": "low",
                    }
                )

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        steps.sort(key=lambda s: priority_order.get(s.get("priority", "low"), 3))

        return steps

    async def _assess_plan_risks(
        self,
        steps: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Assess risks of a repair plan."""
        risks = []

        # Check for high-priority steps that modify files
        for step in steps:
            if step.get("priority") == "high" and step.get("type") == "file_write":
                risks.append(
                    {
                        "severity": "medium",
                        "description": f"High-priority file modification: {step.get('name')}",
                        "mitigation": "Review file changes before applying",
                    }
                )

        return {
            "total_risks": len(risks),
            "risks": risks,
        }

    async def _analyze_file_structure_risks(
        self,
        file_index: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Analyze file structure risks."""
        risks = []

        # Check for deeply nested files
        for path in file_index.keys():
            depth = path.count("/")
            if depth > 10:
                risks.append(
                    {
                        "type": "structure",
                        "severity": "low",
                        "description": f"Deeply nested file: {path}",
                        "recommendation": "Consider flattening directory structure",
                    }
                )

        return risks

    async def _analyze_content_risks(
        self,
        file_index: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Analyze content risks."""
        # In production, would scan file contents
        return []

    async def _analyze_dependency_risks(
        self,
        file_index: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Analyze dependency risks."""
        risks = []

        # Check for dependency files
        dep_files = ["requirements.txt", "package.json", "go.mod", "Cargo.toml"]
        for dep_file in dep_files:
            if dep_file in file_index:
                risks.append(
                    {
                        "type": "dependencies",
                        "severity": "low",
                        "description": f"Dependency file found: {dep_file}",
                        "recommendation": "Regularly update dependencies",
                    }
                )

        return risks

    async def _generate_recommendations(
        self,
        risks: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[str]:
        """Generate recommendations from risks."""
        recommendations = set()

        for risk in risks:
            if "recommendation" in risk:
                recommendations.add(risk["recommendation"])

        return list(recommendations)

    async def _detect_cycle(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> bool:
        """Detect if a DAG has cycles."""
        # Build adjacency list
        adj = {node: [] for node in nodes}
        for src, dst in edges:
            if src in adj:
                adj[src].append(dst)

        # DFS for cycle detection
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in nodes:
            if node not in visited:
                if dfs(node):
                    return True

        return False

    async def _topological_sort(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> list[str]:
        """Compute topological order of nodes."""
        # Build in-degree count
        in_degree = {node: 0 for node in nodes}
        adj = {node: [] for node in nodes}

        for src, dst in edges:
            if src in adj and dst in in_degree:
                adj[src].append(dst)
                in_degree[dst] += 1

        # Queue for nodes with no dependencies
        from collections import deque

        queue = deque([node for node in nodes if in_degree[node] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)

            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    async def _identify_parallel_groups(
        self,
        nodes: list[str],
        edges: list[tuple[str, str]],
    ) -> list[list[str]]:
        """Identify groups of tasks that can run in parallel."""
        # Simplified: use topological levels
        topo_order = await self._topological_sort(nodes, edges)

        groups = []
        current_group = []

        # Build dependency map
        dependencies = {node: set() for node in nodes}
        for src, dst in edges:
            if dst in dependencies:
                dependencies[dst].add(src)

        for node in topo_order:
            # Check if all dependencies are in completed groups
            all_deps_done = True
            for dep in dependencies.get(node, set()):
                dep_completed = any(dep in group for group in groups)
                if not dep_completed:
                    all_deps_done = False
                    break

            if all_deps_done and current_group:
                groups.append(current_group)
                current_group = []

            current_group.append(node)

        if current_group:
            groups.append(current_group)

        return groups

    async def _apply_resource_limits(
        self,
        parallel_groups: list[list[str]],
        max_parallel: int,
    ) -> list[list[str]]:
        """Apply resource limits to parallel groups."""
        optimized = []

        for group in parallel_groups:
            # Split group if it exceeds max_parallel
            for i in range(0, len(group), max_parallel):
                optimized.append(group[i : i + max_parallel])

        return optimized

    async def _load_plans(self, state_dir: str) -> None:
        """Load previous plans."""
        pass

    async def _save_plans(self, state_dir: str) -> None:
        """Save plans."""
        pass

    def get_plan(self, plan_id: str) -> RepairPlan | None:
        """Get a repair plan by ID."""
        with self._lock:
            return self._repair_plans.get(plan_id)

    def list_plans(self) -> list[RepairPlan]:
        """List all repair plans."""
        with self._lock:
            return list(self._repair_plans.values())
