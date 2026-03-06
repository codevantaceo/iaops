"""
Policy Agent for Governance and Compliance.

This agent handles policy evaluation, compliance checking, and governance gates.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..base import Agent, AgentCapability
from ..policy_engine import Policy, PolicyEngine, PolicySeverity, PolicyType


@dataclass
class PolicySet:
    """A set of policies for evaluation."""

    set_id: str
    policies: list[Policy]
    version: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GovernanceGate:
    """A governance gate that must be passed."""

    gate_id: str
    name: str
    description: str
    required_policies: list[str]
    approval_required: bool = False
    approvers: list[str] = field(default_factory=list)
    status: str = "pending"


class PolicyAgent(Agent):
    """Agent for policy and governance operations."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="evaluate_policies",
                description="Evaluate policies against context",
                input_types=["policies_config", "context"],
                output_types=["policy_set", "gates"],
            ),
            AgentCapability(
                name="check_compliance",
                description="Check compliance with standards",
                input_types=["context", "standards"],
                output_types=["compliance_result"],
            ),
            AgentCapability(
                name="create_gates",
                description="Create governance gates",
                input_types=["policies"],
                output_types=["gates"],
            ),
            AgentCapability(
                name="request_approval",
                description="Request approval for actions",
                input_types=["gate_id", "request"],
                output_types=["approval_result"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._policy_engine = PolicyEngine()
        self._policy_sets: dict[str, PolicySet] = {}
        self._gates: dict[str, GovernanceGate] = {}
        self._approvals: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Load default policies
        self._load_default_policies()

    async def initialize(self) -> None:
        """Initialize the policy agent."""
        # Load policies from config
        policies_config = self.config.get("policies_config")
        if policies_config:
            await self._load_policies_from_config(policies_config)

    async def shutdown(self) -> None:
        """Shutdown the policy agent."""
        # Save policy state if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            await self._save_policy_state(state_dir)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "evaluate_policies":
                return await self._task_evaluate_policies(payload, context)
            elif task_type == "check_compliance":
                return await self._task_check_compliance(payload, context)
            elif task_type == "create_gates":
                return await self._task_create_gates(payload, context)
            elif task_type == "request_approval":
                return await self._task_request_approval(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_evaluate_policies(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Evaluate policies against context."""
        policies_config = payload.get("policies_config", {})
        eval_context = payload.get("context", {})
        agent_id = payload.get("agent_id", "")

        # Create or update policy set
        if policies_config:
            policy_set = await self._create_policy_set(policies_config)
            set_id = policy_set.set_id
        else:
            set_id = payload.get("set_id", "default")

        # Evaluate policies
        passed, violations = self._policy_engine.evaluate_action(
            agent_id=agent_id,
            action="execute",
            context=eval_context,
            block_on_critical=True,
        )

        return {
            "success": passed,
            "set_id": set_id,
            "passed": passed,
            "violations": [v.to_dict() for v in violations],
        }

    async def _task_check_compliance(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Check compliance with standards."""
        eval_context = payload.get("context", {})
        standards = payload.get("standards", [])

        if not standards:
            raise ValueError("standards are required")

        compliance_results = {}
        all_compliant = True

        for standard in standards:
            result = await self._check_standard_compliance(
                standard,
                eval_context,
                context,
            )
            compliance_results[standard] = result
            if not result.get("compliant", False):
                all_compliant = False

        return {
            "success": all_compliant,
            "all_compliant": all_compliant,
            "compliance_results": compliance_results,
        }

    async def _task_create_gates(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Create governance gates."""
        gate_definitions = payload.get("gates", [])

        created_gates = []

        # Create gates from definitions
        for gate_def in gate_definitions:
            gate = GovernanceGate(
                gate_id=gate_def.get("gate_id", f"gate_{len(self._gates)}"),
                name=gate_def.get("name", ""),
                description=gate_def.get("description", ""),
                required_policies=gate_def.get("required_policies", []),
                approval_required=gate_def.get("approval_required", False),
                approvers=gate_def.get("approvers", []),
                status="pending",
            )

            self._gates[gate.gate_id] = gate
            created_gates.append(gate.__dict__)

        return {
            "success": True,
            "gates": created_gates,
        }

    async def _task_request_approval(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Request approval for actions."""
        gate_id = payload.get("gate_id")
        request = payload.get("request", {})

        if not gate_id:
            raise ValueError("gate_id is required")

        gate = self._gates.get(gate_id)
        if not gate:
            raise ValueError(f"Gate not found: {gate_id}")

        # Check if approval is required
        if not gate.approval_required:
            # Auto-approve if no approval required
            gate.status = "approved"
            return {
                "success": True,
                "approved": True,
                "gate_id": gate_id,
                "auto_approved": True,
            }

        # Create approval request
        approval_id = f"approval_{int(time.time())}_{self.agent_id}"
        approval = {
            "approval_id": approval_id,
            "gate_id": gate_id,
            "request": request,
            "status": "pending",
            "created_at": time.time(),
            "approvers": gate.approvers,
        }

        self._approvals[approval_id] = approval

        # In a real implementation, this would:
        # - Send notifications to approvers
        # - Wait for approval responses
        # - Track approval status

        # For now, simulate pending approval
        return {
            "success": True,
            "approved": False,
            "approval_id": approval_id,
            "status": "pending",
        }

    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine."""
        self._policy_engine.add_policy(policy)

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy from the engine."""
        return self._policy_engine.remove_policy(policy_id)

    def get_policy(self, policy_id: str) -> Policy | None:
        """Get a policy by ID."""
        return self._policy_engine.get_policy(policy_id)

    def list_policies(
        self,
        policy_type: PolicyType | None = None,
        enabled_only: bool = False,
    ) -> list[Policy]:
        """List policies."""
        return self._policy_engine.list_policies(policy_type, enabled_only)

    def get_gate(self, gate_id: str) -> GovernanceGate | None:
        """Get a gate by ID."""
        with self._lock:
            return self._gates.get(gate_id)

    def list_gates(self) -> list[GovernanceGate]:
        """List all gates."""
        with self._lock:
            return list(self._gates.values())

    def approve_gate(self, gate_id: str, approver: str) -> bool:
        """Approve a gate."""
        with self._lock:
            gate = self._gates.get(gate_id)
            if not gate:
                return False

            if approver not in gate.approvers:
                return False

            gate.status = "approved"
            return True

    def reject_gate(self, gate_id: str, approver: str, reason: str) -> bool:
        """Reject a gate."""
        with self._lock:
            gate = self._gates.get(gate_id)
            if not gate:
                return False

            if approver not in gate.approvers:
                return False

            gate.status = "rejected"
            return True

    async def _create_policy_set(
        self,
        policies_config: dict[str, Any],
    ) -> PolicySet:
        """Create a policy set from configuration."""
        policies = []

        for policy_config in policies_config.get("policies", []):
            policy = Policy(
                name=policy_config.get("name", ""),
                description=policy_config.get("description", ""),
                policy_type=PolicyType(policy_config.get("type", "security")),
                severity=PolicySeverity(policy_config.get("severity", "warning")),
                enabled=policy_config.get("enabled", True),
                conditions=policy_config.get("conditions", {}),
                actions=policy_config.get("actions", []),
            )
            policies.append(policy)
            self._policy_engine.add_policy(policy)

        policy_set = PolicySet(
            set_id=f"set_{int(time.time())}_{self.agent_id}",
            policies=policies,
            version=policies_config.get("version", "1.0.0"),
            metadata=policies_config.get("metadata", {}),
        )

        with self._lock:
            self._policy_sets[policy_set.set_id] = policy_set

        return policy_set

    async def _check_standard_compliance(
        self,
        standard: str,
        eval_context: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check compliance with a specific standard."""
        # Standard-specific compliance checks
        if standard == "SOC2":
            return await self._check_soc2_compliance(eval_context, context)
        elif standard == "GDPR":
            return await self._check_gdpr_compliance(eval_context, context)
        elif standard == "HIPAA":
            return await self._check_hipaa_compliance(eval_context, context)
        else:
            return {
                "compliant": True,
                "standard": standard,
                "checks": [],
            }

    async def _check_soc2_compliance(
        self,
        eval_context: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check SOC2 compliance."""
        checks = []
        all_passed = True

        # Check for audit logging
        has_audit_logs = eval_context.get("audit_logging_enabled", False)
        checks.append(
            {
                "check": "audit_logging",
                "passed": has_audit_logs,
                "description": "Audit logging must be enabled",
            }
        )
        if not has_audit_logs:
            all_passed = False

        # Check for access controls
        has_access_controls = eval_context.get("access_controls_enabled", False)
        checks.append(
            {
                "check": "access_controls",
                "passed": has_access_controls,
                "description": "Access controls must be implemented",
            }
        )
        if not has_access_controls:
            all_passed = False

        return {
            "compliant": all_passed,
            "standard": "SOC2",
            "checks": checks,
        }

    async def _check_gdpr_compliance(
        self,
        eval_context: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check GDPR compliance."""
        checks = []
        all_passed = True

        # Check for data minimization
        has_data_minimization = eval_context.get("data_minimization", False)
        checks.append(
            {
                "check": "data_minimization",
                "passed": has_data_minimization,
                "description": "Data minimization must be implemented",
            }
        )
        if not has_data_minimization:
            all_passed = False

        # Check for consent management
        has_consent = eval_context.get("consent_management", False)
        checks.append(
            {
                "check": "consent_management",
                "passed": has_consent,
                "description": "Consent management must be implemented",
            }
        )
        if not has_consent:
            all_passed = False

        return {
            "compliant": all_passed,
            "standard": "GDPR",
            "checks": checks,
        }

    async def _check_hipaa_compliance(
        self,
        eval_context: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check HIPAA compliance."""
        checks = []
        all_passed = True

        # Check for encryption at rest
        has_encryption = eval_context.get("encryption_at_rest", False)
        checks.append(
            {
                "check": "encryption_at_rest",
                "passed": has_encryption,
                "description": "Encryption at rest must be enabled",
            }
        )
        if not has_encryption:
            all_passed = False

        # Check for audit trails
        has_audit_trails = eval_context.get("audit_trails", False)
        checks.append(
            {
                "check": "audit_trails",
                "passed": has_audit_trails,
                "description": "Audit trails must be maintained",
            }
        )
        if not has_audit_trails:
            all_passed = False

        return {
            "compliant": all_passed,
            "standard": "HIPAA",
            "checks": checks,
        }

    def _load_default_policies(self) -> None:
        """Load default security policies."""
        # Security policies
        self.add_policy(
            Policy(
                name="no_secrets_in_code",
                description="Prevent secrets in code files",
                policy_type=PolicyType.SECURITY,
                severity=PolicySeverity.ERROR,
                conditions={
                    "file_extension": {"not_in": [".env", ".secret", ".key"]},
                },
                actions=["block", "log"],
            )
        )

        self.add_policy(
            Policy(
                name="require_readme",
                description="Require README.md in project",
                policy_type=PolicyType.SECURITY,
                severity=PolicySeverity.WARNING,
                conditions={
                    "has_readme": {"eq": True},
                },
                actions=["log"],
            )
        )

        # Governance policies
        self.add_policy(
            Policy(
                name="require_approval_for_destructive",
                description="Require approval for destructive operations",
                policy_type=PolicyType.GOVERNANCE,
                severity=PolicySeverity.CRITICAL,
                conditions={
                    "operation_type": {"in": ["delete", "truncate", "drop"]},
                },
                actions=["block", "alert"],
            )
        )

    async def _load_policies_from_config(
        self,
        policies_config: dict[str, Any],
    ) -> None:
        """Load policies from configuration file."""
        await self._create_policy_set(policies_config)

    async def _save_policy_state(self, state_dir: str) -> None:
        """Save policy state."""
        pass
