"""
Functional Validator.

Tests core functionality and detects structural regressions
by comparing current test output against baseline using the
RegressionDetector.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .regression_detector import RegressionDetector
from .validator import BaseValidator, Severity, ValidationIssue, ValidationResult


@dataclass
class FunctionalTest:
    """A single functional test definition.

    Attributes:
        test_id: Unique identifier.
        name: Human-readable name.
        test_function: Callable that returns a dict of results.
        source: Source identifier for traceability.
    """

    test_id: str
    name: str
    test_function: Callable[[dict[str, Any]], dict[str, Any]]
    source: str = ""


class FunctionalValidator(BaseValidator):
    """Validator that runs functional tests and detects structural regressions.

    Each registered test function returns a dict.  On subsequent runs the
    validator compares the current dict against the baseline using
    ``RegressionDetector.detect_structural`` (key/type changes → BLOCKER)
    and ``RegressionDetector.detect_numeric`` (metric drops → CRITICAL).
    """

    def __init__(
        self,
        strict_mode: bool = True,
        metric_threshold: float = 0.10,
    ) -> None:
        super().__init__(name="FunctionalValidator", strict_mode=strict_mode)
        self._tests: list[FunctionalTest] = []
        self._detector = RegressionDetector(
            metric_threshold=metric_threshold,
            strict_mode=strict_mode,
        )

    def add_test(self, test: FunctionalTest) -> None:
        """Register a functional test."""
        self._tests.append(test)

    def validate(self, context: dict[str, Any]) -> ValidationResult:
        """Run all functional tests and check for regressions."""
        result = ValidationResult(validator_name=self.name)
        start = time.time()

        for test in self._tests:
            self._run_functional_test(test, context, result)

        result.duration_seconds = time.time() - start
        return result

    def _run_functional_test(
        self,
        test: FunctionalTest,
        context: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Execute a single functional test and compare with baseline."""
        try:
            current_data = test.test_function(context)
        except Exception as e:
            result.add_issue(
                ValidationIssue(
                    issue_id=f"functional_test_error_{test.test_id}",
                    severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
                    category="functional",
                    title=f"Functional test failed: {test.name}",
                    description=f"Test '{test.name}' raised: {e}",
                    source=test.source or test.test_id,
                )
            )
            return

        if not isinstance(current_data, dict):
            result.add_issue(
                ValidationIssue(
                    issue_id=f"functional_test_invalid_{test.test_id}",
                    severity=Severity.ERROR,
                    category="functional",
                    title=f"Invalid test output: {test.name}",
                    description=(
                        f"Test '{test.name}' must return a dict, got {type(current_data).__name__}"
                    ),
                    source=test.source or test.test_id,
                )
            )
            return

        # Store in result metrics
        result.metrics[test.test_id] = current_data

        # Load baseline for this test
        baseline_key = f"functional_{test.test_id}"
        baseline_data = self._baseline.get(baseline_key)

        if baseline_data is not None and isinstance(baseline_data, dict):
            # 1. Structural regression (key/type changes → BLOCKER)
            structural_issue = self._detector.detect_structural(
                current=current_data,
                baseline=baseline_data,
                test_name=test.test_id,
                source=test.source or test.test_id,
            )
            if structural_issue:
                structural_issue.category = "functional"
                result.add_issue(structural_issue)

            # 2. Numeric metric regressions (value drops → CRITICAL)
            for key, current_value in current_data.items():
                if isinstance(current_value, (int, float)) and key in baseline_data:
                    baseline_value = baseline_data[key]
                    if isinstance(baseline_value, (int, float)):
                        numeric_issue = self._detector.detect_numeric(
                            current=float(current_value),
                            baseline=float(baseline_value),
                            metric_type="general",
                            metric_name=f"{test.test_id}_{key}",
                            source=test.source or test.test_id,
                        )
                        if numeric_issue:
                            numeric_issue.category = "functional"
                            result.add_issue(numeric_issue)

        # Update baseline
        self._baseline[baseline_key] = current_data
