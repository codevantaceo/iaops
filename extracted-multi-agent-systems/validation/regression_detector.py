"""
Standalone Regression Detector.

Provides pure-function and class-based APIs for detecting numeric,
performance, and structural regressions against baseline data.
"""

from __future__ import annotations

from typing import Any

from .validator import Severity, ValidationIssue

# ── Pure functions ───────────────────────────────────────────────────


def detect_numeric_regression(
    current_value: float,
    baseline_value: float,
    threshold: float = 0.10,
    metric_type: str = "general",
) -> tuple[bool, str]:
    """Detect numeric metric regression.

    Args:
        current_value: Current metric value.
        baseline_value: Baseline metric value.
        threshold: Maximum allowed deviation (0.10 = 10%).
        metric_type: ``"general"`` (lower is worse) or
                     ``"performance"`` (higher is worse, e.g. latency).

    Returns:
        ``(has_regressed, description)``
    """
    if current_value is None or baseline_value is None:
        return False, "Missing baseline value"

    if baseline_value == 0:
        return False, "Baseline is zero — skipped"

    if metric_type == "performance":
        # Higher is worse (e.g. latency, duration)
        change = (current_value - baseline_value) / baseline_value
        if change > threshold:
            return True, (
                f"Performance regression: increased {abs(change) * 100:.2f}% "
                f"(baseline={baseline_value:.4f}, current={current_value:.4f})"
            )
    else:
        # Lower is worse (e.g. throughput, coverage, file count)
        change = (baseline_value - current_value) / baseline_value
        if change > threshold:
            return True, (
                f"Metric regression: decreased {abs(change) * 100:.2f}% "
                f"(baseline={baseline_value:.4f}, current={current_value:.4f})"
            )

    return False, "Normal"


def detect_structural_regression(
    current_data: dict[str, Any],
    baseline_data: dict[str, Any],
) -> tuple[bool, str]:
    """Detect structural changes between current and baseline results.

    Checks for:
      1. Missing or added keys
      2. Type changes on existing keys

    Returns:
        ``(has_regressed, description)``
    """
    if not baseline_data:
        return False, "No baseline data"

    current_keys = set(current_data.keys())
    baseline_keys = set(baseline_data.keys())

    if current_keys != baseline_keys:
        missing = baseline_keys - current_keys
        added = current_keys - baseline_keys
        parts = []
        if missing:
            parts.append(f"missing keys: {', '.join(sorted(missing))}")
        if added:
            parts.append(f"added keys: {', '.join(sorted(added))}")
        return True, f"Structural change: {'; '.join(parts)}"

    for key in baseline_data:
        if not isinstance(current_data.get(key), type(baseline_data[key])):
            return True, (
                f"Type change on '{key}': "
                f"{type(baseline_data[key]).__name__} → "
                f"{type(current_data[key]).__name__}"
            )

    return False, "Structure intact"


# ── Class-based API ──────────────────────────────────────────────────


class RegressionDetector:
    """Stateful regression detector with configurable thresholds.

    Wraps the pure functions and produces ``ValidationIssue`` objects
    ready for the validation pipeline.
    """

    def __init__(
        self,
        performance_threshold: float = 0.20,
        metric_threshold: float = 0.10,
        strict_mode: bool = True,
    ) -> None:
        self.performance_threshold = performance_threshold
        self.metric_threshold = metric_threshold
        self.strict_mode = strict_mode

    def detect_numeric(
        self,
        current: float,
        baseline: float,
        metric_type: str = "general",
        metric_name: str = "",
        source: str = "",
    ) -> ValidationIssue | None:
        """Detect numeric regression and return a ValidationIssue or None."""
        threshold = (
            self.performance_threshold if metric_type == "performance" else self.metric_threshold
        )
        has_regressed, description = detect_numeric_regression(
            current, baseline, threshold, metric_type
        )
        if not has_regressed:
            return None

        return ValidationIssue(
            issue_id=f"{metric_type}_regression_{metric_name}"
            if metric_name
            else f"{metric_type}_regression",
            severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
            category=metric_type,
            title=f"Regression detected: {metric_name or metric_type}",
            description=description,
            source=source,
            metrics={
                "baseline": baseline,
                "current": current,
                "threshold": threshold,
                "metric_type": metric_type,
            },
        )

    def detect_structural(
        self,
        current: dict[str, Any],
        baseline: dict[str, Any],
        test_name: str = "",
        source: str = "",
    ) -> ValidationIssue | None:
        """Detect structural regression and return a ValidationIssue or None."""
        has_regressed, description = detect_structural_regression(current, baseline)
        if not has_regressed:
            return None

        return ValidationIssue(
            issue_id=f"structural_change_{test_name}" if test_name else "structural_change",
            severity=Severity.BLOCKER,
            category="regression",
            title=f"Structural regression: {test_name or 'unknown'}",
            description=description,
            source=source,
            metrics={
                "baseline_keys": sorted(baseline.keys()),
                "current_keys": sorted(current.keys()),
            },
        )
