"""
Regression Testing for Enterprise Strict Engineering.

Ensures no functionality or performance regression occurs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .validator import BaseValidator, Severity, ValidationIssue, ValidationResult


@dataclass
class RegressionTest:
    """A single regression test."""

    test_id: str
    name: str
    description: str
    test_function: Callable[[dict[str, Any]], dict[str, Any]]
    baseline_result: dict[str, Any] | None = None
    category: str = "functional"
    timeout: float = 30.0
    enabled: bool = True


@dataclass
class RegressionSuite:
    """A suite of regression tests."""

    suite_id: str
    name: str
    tests: list[RegressionTest]
    baseline_path: str | None = None


class RegressionValidator(BaseValidator):
    """Validator for regression testing."""

    def __init__(
        self,
        strict_mode: bool = True,
        test_timeout: float = 30.0,
    ):
        super().__init__(
            name="RegressionValidator",
            strict_mode=strict_mode,
        )
        self.test_timeout = test_timeout
        self._test_suites: list[RegressionSuite] = []
        self._results: dict[str, dict[str, Any]] = {}

    def add_suite(self, suite: RegressionSuite) -> None:
        """Add a regression test suite."""
        self._test_suites.append(suite)

    def validate(self, context: dict[str, Any]) -> ValidationResult:
        """Run all regression tests."""
        result = ValidationResult(validator_name=self.name)
        start_time = time.time()

        project_root = context.get("project_root", ".")

        for suite in self._test_suites:
            suite_result = self._run_suite(suite, context, project_root)
            result.issues.extend(suite_result.issues)
            result.metrics[suite.suite_id] = suite_result.metrics

        result.duration_seconds = time.time() - start_time

        return result

    def _run_suite(
        self,
        suite: RegressionSuite,
        context: dict[str, Any],
        project_root: str,
    ) -> ValidationResult:
        """Run a single test suite."""
        result = ValidationResult(validator_name=f"{self.name}.{suite.suite_id}")

        for test in suite.tests:
            if not test.enabled:
                continue

            try:
                test_result = self._run_test(test, context)
                self._compare_with_baseline(test, test_result, result, context)
            except Exception as e:
                result.add_issue(
                    ValidationIssue(
                        issue_id=f"test_failure_{test.test_id}",
                        severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
                        category="regression",
                        title=f"Test failed: {test.name}",
                        description=f"Test '{test.name}' failed with exception: {str(e)}",
                    )
                )

        return result

    def _run_test(
        self,
        test: RegressionTest,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a single test."""
        start_time = time.time()

        try:
            result = test.test_function(context)
            duration = time.time() - start_time

            test_result = {
                "success": True,
                "result": result,
                "duration": duration,
                "timestamp": time.time(),
            }

            # Save as baseline if not set
            if test.baseline_result is None:
                test.baseline_result = test_result

            return test_result
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "timestamp": time.time(),
            }

    def _compare_with_baseline(
        self,
        test: RegressionTest,
        current_result: dict[str, Any],
        validation_result: ValidationResult,
        context: dict[str, Any],
    ) -> None:
        """Compare test result with baseline."""
        test_id = test.test_id

        # Save current result
        self._results[test_id] = current_result

        # Check for test failure
        if not current_result.get("success", False):
            validation_result.add_issue(
                ValidationIssue(
                    issue_id=f"test_failed_{test_id}",
                    severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
                    category="regression",
                    title=f"Test failed: {test.name}",
                    description=f"Test '{test.name}' failed: {current_result.get('error', 'Unknown error')}",
                )
            )
            return

        current_data = current_result.get("result", {})

        # Check for numeric metrics regression
        if test.baseline_result and isinstance(current_data, dict):
            baseline_data = test.baseline_result.get("result", {})

            # Compare all numeric metrics
            for key, current_value in current_data.items():
                if isinstance(current_value, (int, float)):
                    if key in baseline_data:
                        baseline_value = baseline_data[key]

                        if isinstance(baseline_value, (int, float)):
                            # Check for regression (value decreased by more than 10%)
                            if current_value < baseline_value * 0.9:
                                regression_pct = (
                                    (baseline_value - current_value) / baseline_value * 100
                                )

                                validation_result.add_issue(
                                    ValidationIssue(
                                        issue_id=f"metric_regression_{test_id}_{key}",
                                        severity=Severity.CRITICAL
                                        if self.strict_mode
                                        else Severity.ERROR,
                                        category="regression",
                                        title=f"Metric regression in {test.name}: {key}",
                                        description=(
                                            f"Metric '{key}' has regressed by {regression_pct:.1f}. "
                                            f"Baseline: {baseline_value}, Current: {current_value}. "
                                            f"{'STRICT MODE: This regression is BLOCKED!' if self.strict_mode else ''}"
                                        ),
                                        metrics={
                                            "metric_name": key,
                                            "baseline": baseline_value,
                                            "current": current_value,
                                            "regression_pct": regression_pct,
                                        },
                                    )
                                )

        # Check for exact result match (for non-numeric tests)
        if test.baseline_result:
            baseline = test.baseline_result.get("result", {})
            current = current_result.get("result", {})

            # Compare results (exclude numeric metrics which were already checked)
            non_numeric_baseline = {
                k: v for k, v in baseline.items() if not isinstance(v, (int, float))
            }
            non_numeric_current = {
                k: v for k, v in current.items() if not isinstance(v, (int, float))
            }

            if non_numeric_baseline and non_numeric_baseline != non_numeric_current:
                validation_result.add_issue(
                    ValidationIssue(
                        issue_id=f"result_mismatch_{test_id}",
                        severity=Severity.BLOCKER if self.strict_mode else Severity.ERROR,
                        category="regression",
                        title=f"Result mismatch: {test.name}",
                        description=(
                            f"Test '{test.name}' produced different result than baseline. "
                            f"STRICT MODE: This regression is BLOCKED!"
                        ),
                        metrics={
                            "baseline": non_numeric_baseline,
                            "current": non_numeric_current,
                        },
                    )
                )

        # Check for performance regression
        if test.baseline_result and "duration" in test.baseline_result:
            baseline_duration = test.baseline_result["duration"]
            current_duration = current_result.get("duration", 0)

            # Performance regression: 20% slower
            if current_duration > baseline_duration * 1.2:
                validation_result.add_issue(
                    ValidationIssue(
                        issue_id=f"perf_regression_{test_id}",
                        severity=Severity.CRITICAL if self.strict_mode else Severity.WARNING,
                        category="performance",
                        title=f"Performance regression: {test.name}",
                        description=(
                            f"Test '{test.name}' is {((current_duration / baseline_duration) - 1) * 100:.1f}% "
                            f"slower than baseline. "
                            f"Baseline: {baseline_duration:.3f}s, Current: {current_duration:.3f}s. "
                            f"{'STRICT MODE: Performance regression is BLOCKED!' if self.strict_mode else ''}"
                        ),
                        metrics={
                            "baseline_duration": baseline_duration,
                            "current_duration": current_duration,
                            "regression_pct": ((current_duration / baseline_duration) - 1) * 100,
                        },
                    )
                )

    def _results_match(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any],
    ) -> bool:
        """Check if results match baseline."""
        # Simple comparison - in production would be more sophisticated
        return baseline == current

    def save_results(self, output_path: Path | str) -> None:
        """Save test results."""
        import json

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._results, f, indent=2, ensure_ascii=False)
