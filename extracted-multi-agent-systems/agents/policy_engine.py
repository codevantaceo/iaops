"""
Policy Engine for Rule Evaluation and Enforcement.

This module provides the PolicyEngine class which evaluates
policies against agent actions and enforces governance rules.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicySeverity(Enum):
    """Severity level of a policy violation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PolicyType(Enum):
    """Types of policies."""

    SECURITY = "security"
    GOVERNANCE = "governance"
    COMPLIANCE = "compliance"
    OPERATIONAL = "operational"
    RESOURCE = "resource"


@dataclass
class Policy:
    """A policy rule that can be evaluated."""

    policy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    policy_type: PolicyType = PolicyType.SECURITY
    severity: PolicySeverity = PolicySeverity.WARNING
    enabled: bool = True

    # Policy definition
    rule_pattern: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)

    # Scope
    applies_to_agents: list[str] = field(default_factory=list)
    applies_to_tags: list[str] = field(default_factory=list)
    applies_to_actions: list[str] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    author: str = ""
    version: str = "1.0.0"

    def matches_agent(self, agent_id: str, agent_tags: list[str] | None = None) -> bool:
        """Check if policy applies to an agent."""
        # Check explicit agent list
        if self.applies_to_agents and agent_id not in self.applies_to_agents:
            return False

        # Check tags
        if self.applies_to_tags:
            if not agent_tags or not any(tag in agent_tags for tag in self.applies_to_tags):
                return False

        return True

    def matches_action(self, action: str) -> bool:
        """Check if policy applies to an action."""
        if not self.applies_to_actions:
            return True
        return action in self.applies_to_actions

    def to_dict(self) -> dict[str, Any]:
        """Convert policy to dictionary."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "policy_type": self.policy_type.value,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "rule_pattern": self.rule_pattern,
            "conditions": self.conditions,
            "actions": self.actions,
            "applies_to_agents": self.applies_to_agents,
            "applies_to_tags": self.applies_to_tags,
            "applies_to_actions": self.applies_to_actions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "version": self.version,
        }


@dataclass
class PolicyViolation:
    """A policy violation that occurred."""

    violation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str = ""
    policy_name: str = ""
    severity: PolicySeverity = PolicySeverity.WARNING

    # Context
    agent_id: str = ""
    action: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    # Details
    violated_condition: str = ""
    actual_value: Any = None
    expected_value: Any = None

    # Timestamp
    occurred_at: float = field(default_factory=time.time)

    # Actions taken
    actions_taken: list[str] = field(default_factory=list)
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary."""
        return {
            "violation_id": self.violation_id,
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "action": self.action,
            "context": self.context,
            "violated_condition": self.violated_condition,
            "actual_value": self.actual_value,
            "expected_value": self.expected_value,
            "occurred_at": self.occurred_at,
            "actions_taken": self.actions_taken,
            "blocked": self.blocked,
        }


class PolicyEvaluator:
    """Evaluates a single policy against a context."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(
        self,
        context: dict[str, Any],
    ) -> bool:
        """Evaluate if the policy passes."""
        if not self.policy.enabled:
            return True

        # Check conditions
        for key, expected_value in self.policy.conditions.items():
            actual_value = self._get_nested_value(context, key)

            if not self._evaluate_condition(
                actual_value,
                expected_value,
            ):
                return False

        # Check rule pattern if specified
        if self.policy.rule_pattern:
            context_str = str(context)
            if not re.search(self.policy.rule_pattern, context_str):
                return False

        return True

    def _get_nested_value(
        self,
        data: dict[str, Any],
        key: str,
    ) -> Any:
        """Get a nested value from a dictionary using dot notation."""
        keys = key.split(".")
        value = data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None

        return value

    def _evaluate_condition(
        self,
        actual: Any,
        expected: Any,
    ) -> bool:
        """Evaluate a single condition."""
        # Handle dict-based conditions (operators)
        if isinstance(expected, dict):
            for operator, value in expected.items():
                if operator == "eq":
                    if actual != value:
                        return False
                elif operator == "ne":
                    if actual == value:
                        return False
                elif operator == "gt":
                    if not (isinstance(actual, (int, float)) and actual > value):
                        return False
                elif operator == "lt":
                    if not (isinstance(actual, (int, float)) and actual < value):
                        return False
                elif operator == "gte":
                    if not (isinstance(actual, (int, float)) and actual >= value):
                        return False
                elif operator == "lte":
                    if not (isinstance(actual, (int, float)) and actual <= value):
                        return False
                elif operator == "in":
                    if actual not in value:
                        return False
                elif operator == "not_in":
                    if actual in value:
                        return False
                elif operator == "contains":
                    if value not in str(actual):
                        return False
                elif operator == "regex":
                    if not re.search(value, str(actual)):
                        return False
                elif operator == "not_contains":
                    if value in str(actual):
                        return False

        else:
            # Simple equality check
            return actual == expected

        return True


class PolicyEngine:
    """Engine for evaluating and enforcing policies."""

    def __init__(self):
        self._policies: dict[str, Policy] = {}
        self._violations: list[PolicyViolation] = []
        self._evaluators: dict[str, PolicyEvaluator] = {}

        self._lock = threading.RLock()
        self._violation_callbacks: list[Callable[[PolicyViolation], None]] = []

    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine."""
        with self._lock:
            self._policies[policy.policy_id] = policy
            self._evaluators[policy.policy_id] = PolicyEvaluator(policy)

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy from the engine."""
        with self._lock:
            if policy_id in self._policies:
                del self._policies[policy_id]
                del self._evaluators[policy_id]
                return True
            return False

    def get_policy(self, policy_id: str) -> Policy | None:
        """Get a policy by ID."""
        with self._lock:
            return self._policies.get(policy_id)

    def list_policies(
        self,
        policy_type: PolicyType | None = None,
        enabled_only: bool = False,
    ) -> list[Policy]:
        """List policies with optional filters."""
        with self._lock:
            policies = list(self._policies.values())

            if policy_type:
                policies = [p for p in policies if p.policy_type == policy_type]

            if enabled_only:
                policies = [p for p in policies if p.enabled]

            return policies

    def evaluate_action(
        self,
        agent_id: str,
        action: str,
        context: dict[str, Any],
        agent_tags: list[str] | None = None,
        block_on_critical: bool = True,
    ) -> tuple[bool, list[PolicyViolation]]:
        """Evaluate an action against all applicable policies."""
        violations: list[PolicyViolation] = []
        blocked = False

        with self._lock:
            for policy_id, evaluator in self._evaluators.items():
                policy = self._policies[policy_id]

                # Check if policy applies
                if not policy.matches_agent(agent_id, agent_tags):
                    continue

                if not policy.matches_action(action):
                    continue

                # Evaluate policy
                if not evaluator.evaluate(context):
                    violation = PolicyViolation(
                        policy_id=policy_id,
                        policy_name=policy.name,
                        severity=policy.severity,
                        agent_id=agent_id,
                        action=action,
                        context=context,
                    )

                    # Determine action to take
                    should_block = False
                    for action_name in policy.actions:
                        if action_name == "block" and policy.severity in (
                            PolicySeverity.ERROR,
                            PolicySeverity.CRITICAL,
                        ):
                            should_block = True
                            violation.actions_taken.append("blocked")
                        elif action_name == "log":
                            violation.actions_taken.append("logged")
                        elif action_name == "alert":
                            violation.actions_taken.append("alerted")

                    violation.blocked = should_block
                    violations.append(violation)

                    # Store violation
                    self._violations.append(violation)

                    # Notify callbacks
                    for callback in self._violation_callbacks:
                        try:
                            callback(violation)
                        except Exception:
                            pass

                    # Check if we should block
                    if should_block and block_on_critical:
                        blocked = True

        return (not blocked, violations)

    def get_violations(
        self,
        agent_id: str | None = None,
        severity: PolicySeverity | None = None,
        limit: int = 100,
    ) -> list[PolicyViolation]:
        """Get policy violations with optional filters."""
        with self._lock:
            violations = self._violations

            if agent_id:
                violations = [v for v in violations if v.agent_id == agent_id]

            if severity:
                violations = [v for v in violations if v.severity == severity]

            return violations[-limit:]

    def clear_violations(self, older_than: float | None = None) -> int:
        """Clear violations, optionally older than a timestamp."""
        with self._lock:
            if older_than is None:
                count = len(self._violations)
                self._violations.clear()
                return count

            original_count = len(self._violations)
            self._violations = [v for v in self._violations if v.occurred_at >= older_than]

            return original_count - len(self._violations)

    def add_violation_callback(
        self,
        callback: Callable[[PolicyViolation], None],
    ) -> None:
        """Add a callback for policy violations."""
        self._violation_callbacks.append(callback)

    def remove_violation_callback(
        self,
        callback: Callable[[PolicyViolation], None],
    ) -> None:
        """Remove a violation callback."""
        if callback in self._violation_callbacks:
            self._violation_callbacks.remove(callback)

    def get_engine_stats(self) -> dict[str, Any]:
        """Get statistics about the policy engine."""
        with self._lock:
            return {
                "total_policies": len(self._policies),
                "enabled_policies": sum(1 for p in self._policies.values() if p.enabled),
                "by_type": {
                    policy_type.value: len(
                        [p for p in self._policies.values() if p.policy_type == policy_type]
                    )
                    for policy_type in PolicyType
                },
                "total_violations": len(self._violations),
                "by_severity": {
                    severity.value: len([v for v in self._violations if v.severity == severity])
                    for severity in PolicySeverity
                },
            }
