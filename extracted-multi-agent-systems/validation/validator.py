"""
Core Validation Validator for Enterprise Strict Engineering.

This module provides the base validation framework with strict
enforcement of quality standards and regression prevention.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# 禁止降級的嚴格模式
STRICT_MODE = True


class Severity(Enum):
    """Severity level for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    BLOCKER = "blocker"  # 完全禁止，必須修復


@dataclass
class ValidationIssue:
    """A validation issue found during checking."""

    issue_id: str
    severity: Severity
    category: str
    title: str
    description: str
    source: str = ""
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None
    code_snippet: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def is_blocking(self) -> bool:
        """Check if this issue blocks deployment."""
        if STRICT_MODE:
            return self.severity in (Severity.ERROR, Severity.CRITICAL, Severity.BLOCKER)
        return self.severity == Severity.BLOCKER

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_id": self.issue_id,
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
            "blocking": self.is_blocking(),
        }


@dataclass
class ValidationResult:
    """Result of a validation check."""

    validator_name: str
    timestamp: float = field(default_factory=time.time)
    passed: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    # 嚴格模式下的統計
    blocked_by_critical: bool = False
    blocked_by_error: bool = False
    blocked_by_regression: bool = False

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add an issue to the result."""
        self.issues.append(issue)

        # Update pass status based on severity
        if issue.is_blocking():
            self.passed = False
            if issue.severity == Severity.BLOCKER:
                self.blocked_by_regression = True
            elif issue.severity == Severity.CRITICAL:
                self.blocked_by_critical = True
            elif issue.severity == Severity.ERROR:
                self.blocked_by_error = True

    def get_issues_by_severity(
        self,
        severity: Severity,
    ) -> list[ValidationIssue]:
        """Get issues filtered by severity."""
        return [i for i in self.issues if i.severity == severity]

    def get_blocking_issues(self) -> list[ValidationIssue]:
        """Get all blocking issues."""
        return [i for i in self.issues if i.is_blocking()]

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        by_severity = {s.value: 0 for s in Severity}
        for issue in self.issues:
            by_severity[issue.severity.value] += 1

        return {
            "total_issues": len(self.issues),
            "blocking_issues": len(self.get_blocking_issues()),
            "by_severity": by_severity,
            "passed": self.passed,
            "strict_mode": STRICT_MODE,
            "blocked_by_critical": self.blocked_by_critical,
            "blocked_by_error": self.blocked_by_error,
            "blocked_by_regression": self.blocked_by_regression,
            "duration_seconds": self.duration_seconds,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "validator_name": self.validator_name,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "summary": self.get_summary(),
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class BaseValidator(ABC):
    """Base class for all validators."""

    def __init__(
        self,
        name: str,
        strict_mode: bool = STRICT_MODE,
        allow_blocking: bool = False,  # 嚴格模式下不允許通過
    ):
        self.name = name
        self.strict_mode = strict_mode
        self.allow_blocking = allow_blocking
        self._baseline: dict[str, Any] = {}

    @abstractmethod
    def validate(
        self,
        context: dict[str, Any],
    ) -> ValidationResult:
        """Run validation checks."""
        pass

    def load_baseline(
        self,
        baseline_path: Path | str,
    ) -> None:
        """Load baseline metrics for regression detection."""
        path = Path(baseline_path)
        if path.exists():
            with open(path) as f:
                self._baseline = json.load(f)
        else:
            raise ValueError(f"Baseline file not found: {baseline_path}")

    def save_baseline(
        self,
        baseline_path: Path | str,
    ) -> None:
        """Save current metrics as baseline."""
        path = Path(baseline_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._baseline, f, indent=2, ensure_ascii=False)

    def check_regression(
        self,
        metric_name: str,
        current_value: float,
        threshold: float = 0.1,  # 10% regression threshold
        higher_is_better: bool = False,
    ) -> ValidationIssue | None:
        """Check if a metric has regressed compared to baseline."""

        if metric_name not in self._baseline:
            # No baseline, save current value
            self._baseline[metric_name] = current_value
            return None

        baseline_value = self._baseline[metric_name]

        # Guard against division by zero
        if baseline_value == 0:
            if current_value == 0:
                return None
            self._baseline[metric_name] = current_value
            return None

        # Calculate regression magnitude
        if higher_is_better:
            regression_pct = (baseline_value - current_value) / baseline_value
            has_regressed = current_value < baseline_value * (1 - threshold)
        else:
            regression_pct = (current_value - baseline_value) / baseline_value
            has_regressed = current_value > baseline_value * (1 + threshold)

        # Strict mode: regressions are CRITICAL (whitelistable), not BLOCKER
        severity = Severity.CRITICAL if self.strict_mode and has_regressed else Severity.ERROR

        if has_regressed:
            return ValidationIssue(
                issue_id=f"regression_{metric_name}",
                severity=severity,
                category="regression",
                title=f"Regression detected in {metric_name}",
                description=(
                    f"Metric '{metric_name}' has regressed by {abs(regression_pct):.1%}. "
                    f"Baseline: {baseline_value:.2f}, Current: {current_value:.2f}. "
                    f"{'STRICT MODE: This change is BLOCKED!' if self.strict_mode else ''}"
                ),
                metrics={
                    "baseline": baseline_value,
                    "current": current_value,
                    "regression_pct": abs(regression_pct),
                    "threshold": threshold,
                },
            )

        return None

    def check_threshold(
        self,
        metric_name: str,
        current_value: float,
        min_value: float | None = None,
        max_value: float | None = None,
        exact_value: float | None = None,
    ) -> ValidationIssue | None:
        """Check if a metric meets threshold requirements."""

        if exact_value is not None and current_value != exact_value:
            return ValidationIssue(
                issue_id=f"threshold_{metric_name}_exact",
                severity=Severity.ERROR if self.strict_mode else Severity.WARNING,
                category="threshold",
                title=f"Threshold violation for {metric_name}",
                description=(
                    f"Metric '{metric_name}' must be exactly {exact_value}, but is {current_value}"
                ),
                metrics={
                    "expected": exact_value,
                    "actual": current_value,
                },
            )

        if min_value is not None and current_value < min_value:
            return ValidationIssue(
                issue_id=f"threshold_{metric_name}_min",
                severity=Severity.ERROR if self.strict_mode else Severity.WARNING,
                category="threshold",
                title=f"Threshold violation for {metric_name}",
                description=(
                    f"Metric '{metric_name}' must be at least {min_value}, but is {current_value}"
                ),
                metrics={
                    "min_required": min_value,
                    "actual": current_value,
                },
            )

        if max_value is not None and current_value > max_value:
            return ValidationIssue(
                issue_id=f"threshold_{metric_name}_max",
                severity=Severity.ERROR if self.strict_mode else Severity.WARNING,
                category="threshold",
                title=f"Threshold violation for {metric_name}",
                description=(
                    f"Metric '{metric_name}' must be at most {max_value}, but is {current_value}"
                ),
                metrics={
                    "max_allowed": max_value,
                    "actual": current_value,
                },
            )

        return None
