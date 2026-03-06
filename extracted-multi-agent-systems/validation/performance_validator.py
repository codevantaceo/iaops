"""
Performance Validator.

Measures execution performance of configurable test functions and
detects regressions against baseline timings.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .metrics import collect_latency_metrics
from .regression_detector import RegressionDetector
from .validator import BaseValidator, Severity, ValidationIssue, ValidationResult


@dataclass
class PerformanceTest:
    """A single performance test definition.

    Attributes:
        test_id: Unique identifier.
        name: Human-readable name.
        test_function: Callable that returns a numeric result (duration/latency).
        iterations: Number of times to run the test for statistical significance.
        source: Source identifier for traceability.
    """

    test_id: str
    name: str
    test_function: Callable[[], float]
    iterations: int = 5
    source: str = ""


class PerformanceValidator(BaseValidator):
    """Validator that runs performance tests and detects regressions.

    Collects p50/p95/p99 latencies per test and compares against
    baseline using configurable thresholds.
    """

    def __init__(
        self,
        strict_mode: bool = True,
        performance_threshold: float = 0.20,
    ) -> None:
        super().__init__(name="PerformanceValidator", strict_mode=strict_mode)
        self._tests: list[PerformanceTest] = []
        self._detector = RegressionDetector(
            performance_threshold=performance_threshold,
            strict_mode=strict_mode,
        )

    def add_test(self, test: PerformanceTest) -> None:
        """Register a performance test."""
        self._tests.append(test)

    def validate(self, context: dict[str, Any]) -> ValidationResult:
        """Run all performance tests and check for regressions."""
        result = ValidationResult(validator_name=self.name)
        start = time.time()

        for test in self._tests:
            self._run_perf_test(test, result)

        result.duration_seconds = time.time() - start
        return result

    def _run_perf_test(
        self,
        test: PerformanceTest,
        result: ValidationResult,
    ) -> None:
        """Execute a single performance test and check results."""
        durations: list[float] = []

        for _ in range(test.iterations):
            try:
                t0 = time.perf_counter()
                test.test_function()
                elapsed = time.perf_counter() - t0
                durations.append(elapsed)
            except Exception as e:
                result.add_issue(
                    ValidationIssue(
                        issue_id=f"perf_test_error_{test.test_id}",
                        severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
                        category="performance",
                        title=f"Performance test failed: {test.name}",
                        description=f"Test '{test.name}' raised: {e}",
                        source=test.source or test.test_id,
                    )
                )
                return

        if not durations:
            return

        # Compute latency metrics
        latency_metrics = collect_latency_metrics(durations)
        p50 = latency_metrics["latency_p50"].value
        p95 = latency_metrics["latency_p95"].value
        p99 = latency_metrics["latency_p99"].value
        mean = latency_metrics["latency_mean"].value

        # Store in result metrics
        result.metrics[test.test_id] = {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "mean": mean,
            "iterations": test.iterations,
            "durations": durations,
        }

        # Check p95 regression against baseline
        baseline_key = f"{test.test_id}_p95"
        issue = self._detector.detect_numeric(
            current=p95,
            baseline=self._baseline.get(baseline_key, p95),
            metric_type="performance",
            metric_name=f"{test.test_id}_p95",
            source=test.source or test.test_id,
        )
        if issue:
            result.add_issue(issue)

        # Check p99 regression against baseline
        baseline_key_p99 = f"{test.test_id}_p99"
        issue_p99 = self._detector.detect_numeric(
            current=p99,
            baseline=self._baseline.get(baseline_key_p99, p99),
            metric_type="performance",
            metric_name=f"{test.test_id}_p99",
            source=test.source or test.test_id,
        )
        if issue_p99:
            result.add_issue(issue_p99)

        # Update baseline
        self._baseline[baseline_key] = p95
        self._baseline[baseline_key_p99] = p99
