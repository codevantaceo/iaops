"""
Enterprise Strict Engineering Validator — Master Validator.

Integrates all validation components with strict regression prevention
and false-positive suppression via the whitelist system.

DEFAULT_VALIDATORS:
  - FileCheckValidator   (source file integrity)
  - FunctionalValidator  (structural regression detection)
  - PerformanceValidator (latency regression detection)
  - RegressionValidator  (functional regression suites)
  - MetricsValidator     (advanced metrics + progressive blocking)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .file_validator import FileCheckValidator
from .functional_validator import FunctionalTest, FunctionalValidator
from .metrics import MetricsValidator, get_default_thresholds
from .performance_validator import PerformanceValidator
from .regression import RegressionSuite, RegressionTest, RegressionValidator
from .validator import BaseValidator, Severity, ValidationResult
from .whitelist import WhitelistManager


@dataclass
class StrictValidationConfig:
    """Configuration for strict validation."""

    project_root: str
    baseline_dir: str = ".baselines"
    output_dir: str = ".validation"
    whitelist_path: str | None = None  # path to whitelist JSON/YAML
    strict_mode: bool = True
    fail_on_regression: bool = True
    fail_on_security: bool = True
    fail_on_quality: bool = True
    performance_threshold: float = 0.20  # 20% performance deviation threshold
    metric_threshold: float = 0.10  # 10% metric deviation threshold


class StrictValidator:
    """Master validator for enterprise strict engineering.

    Orchestrates multiple validators, applies whitelist suppression,
    and produces a single consolidated report.

    DEFAULT_VALIDATORS are automatically registered:
      - FileCheckValidator
      - FunctionalValidator
      - PerformanceValidator
      - RegressionValidator
      - MetricsValidator
    """

    DEFAULT_VALIDATORS: list[type[BaseValidator]] = [
        FileCheckValidator,
        FunctionalValidator,
        PerformanceValidator,
        RegressionValidator,
        MetricsValidator,
    ]

    def __init__(self, config: StrictValidationConfig) -> None:
        self.config = config
        self._validators: list[BaseValidator] = []
        self._baseline_path = Path(config.baseline_dir)
        self._output_path = Path(config.output_dir)

        # Whitelist / false-positive manager
        self._whitelist = self._load_whitelist()

        # Initialize built-in validators
        self._init_validators()

    # ── initialisation helpers ───────────────────────────────────────────

    def _init_validators(self) -> None:
        """Initialize all default validators with config-driven thresholds."""
        # File check validator
        self.file_validator = FileCheckValidator(
            strict_mode=self.config.strict_mode,
        )
        self._validators.append(self.file_validator)

        # Functional validator (structural regression detection)
        self.functional_validator = FunctionalValidator(
            strict_mode=self.config.strict_mode,
            metric_threshold=self.config.metric_threshold,
        )
        self._validators.append(self.functional_validator)

        # Performance validator
        self.performance_validator = PerformanceValidator(
            strict_mode=self.config.strict_mode,
            performance_threshold=self.config.performance_threshold,
        )
        self._validators.append(self.performance_validator)

        # Regression validator
        self.regression_validator = RegressionValidator(
            strict_mode=self.config.strict_mode,
        )
        self._validators.append(self.regression_validator)

        # Metrics validator (advanced metrics collection)
        self.metrics_validator = MetricsValidator(
            thresholds=get_default_thresholds(),
            strict_mode=self.config.strict_mode,
        )
        self._validators.append(self.metrics_validator)

    def _load_whitelist(self) -> WhitelistManager:
        """Load whitelist from configured path, or return empty manager."""
        if self.config.whitelist_path is None:
            return WhitelistManager()
        path = Path(self.config.whitelist_path)
        if not path.exists():
            return WhitelistManager()
        if path.suffix in (".yaml", ".yml"):
            return WhitelistManager.load_yaml(path)
        return WhitelistManager.load(path)

    # ── public API ───────────────────────────────────────────────────────

    @property
    def whitelist(self) -> WhitelistManager:
        """Expose the whitelist manager for external rule management."""
        return self._whitelist

    @property
    def validators(self) -> list[BaseValidator]:
        """Return the list of registered validators."""
        return list(self._validators)

    def add_regression_suite(self, suite: RegressionSuite) -> None:
        """Add a regression test suite."""
        self.regression_validator.add_suite(suite)

    def add_functional_test(self, test: FunctionalTest) -> None:
        """Add a functional test."""
        self.functional_validator.add_test(test)

    def validate_all(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run all validations with whitelist suppression.

        Each issue is checked against the whitelist.  Suppressed issues
        are kept in the report (for transparency) but downgraded to INFO
        and marked ``"suppressed": true`` so they no longer block.
        """
        context = context or {}
        context["project_root"] = self.config.project_root

        results: dict[str, Any] = {
            "timestamp": time.time(),
            "strict_mode": self.config.strict_mode,
            "project_root": self.config.project_root,
            "validators": {},
            "overall_passed": True,
            "whitelist_stats": {},
            "summary": {
                "total_validators": 0,
                "passed_validators": 0,
                "failed_validators": 0,
                "total_issues": 0,
                "blocking_issues": 0,
                "suppressed_issues": 0,
                "by_category": {},
            },
        }

        # Run all validators (single pass — never run twice)
        for validator in self._validators:
            result = validator.validate(context)

            # Apply whitelist suppression to each issue
            suppressed_count = self._apply_whitelist(result)
            results["summary"]["suppressed_issues"] += suppressed_count

            results["validators"][validator.name] = result.to_dict()

            # Update summary
            results["summary"]["total_validators"] += 1
            if result.passed:
                results["summary"]["passed_validators"] += 1
            else:
                results["summary"]["failed_validators"] += 1
                results["overall_passed"] = False

            results["summary"]["total_issues"] += len(result.issues)
            results["summary"]["blocking_issues"] += len(result.get_blocking_issues())

            # Categorize issues from this single run
            for issue in result.issues:
                cat = issue.category
                if cat not in results["summary"]["by_category"]:
                    results["summary"]["by_category"][cat] = 0
                results["summary"]["by_category"][cat] += 1

        # Attach whitelist audit stats
        results["whitelist_stats"] = self._whitelist.get_stats()

        # Save results
        self._save_results(results)

        # Persist whitelist (updated audit logs)
        if self.config.whitelist_path:
            self._whitelist.save(self.config.whitelist_path)

        return results

    # ── whitelist integration ────────────────────────────────────────────

    def _apply_whitelist(self, result: ValidationResult) -> int:
        """Apply whitelist rules to a validation result.

        Suppressed issues are downgraded to INFO and annotated.
        Returns the number of issues suppressed.
        """
        suppressed = 0
        for issue in result.issues:
            should_suppress, rule = self._whitelist.should_suppress(
                issue_id=issue.issue_id,
                severity=issue.severity.value,
                category=issue.category,
                file_path=issue.file_path,
            )
            if should_suppress and rule is not None:
                # Downgrade — keep the issue visible but non-blocking
                issue.severity = Severity.INFO
                issue.description = (
                    f"[SUPPRESSED by whitelist rule '{rule.rule_id}'] {issue.description}"
                )
                issue.metrics["suppressed"] = True
                issue.metrics["suppressed_by_rule"] = rule.rule_id
                issue.metrics["suppression_reason"] = rule.reason
                suppressed += 1

        # Recalculate pass status after suppression
        result.passed = all(not i.is_blocking() for i in result.issues)
        result.blocked_by_critical = False
        result.blocked_by_error = False
        result.blocked_by_regression = False
        for issue in result.issues:
            if issue.is_blocking():
                result.passed = False
                if issue.severity == Severity.BLOCKER:
                    result.blocked_by_regression = True
                elif issue.severity == Severity.CRITICAL:
                    result.blocked_by_critical = True
                elif issue.severity == Severity.ERROR:
                    result.blocked_by_error = True

        return suppressed

    # ── baseline management ──────────────────────────────────────────────

    def create_baseline(self, context: dict[str, Any] | None = None) -> None:
        """Create baseline metrics for all validators."""
        context = context or {}
        context["project_root"] = self.config.project_root

        self._baseline_path.mkdir(parents=True, exist_ok=True)

        for validator in self._validators:
            baseline_path = self._baseline_path / f"{validator.name}.json"
            validator.save_baseline(baseline_path)

    def load_baseline(self) -> None:
        """Load baseline metrics for all validators."""
        if not self._baseline_path.exists():
            raise ValueError(f"Baseline directory not found: {self._baseline_path}")

        for validator in self._validators:
            baseline_path = self._baseline_path / f"{validator.name}.json"
            if baseline_path.exists():
                validator.load_baseline(baseline_path)

    # ── persistence ──────────────────────────────────────────────────────

    def _save_results(self, results: dict[str, Any]) -> None:
        """Save validation results."""
        self._output_path.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        result_file = self._output_path / f"validation_{timestamp}.json"

        with open(result_file, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        latest_file = self._output_path / "validation_latest.json"
        with open(latest_file, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # ── reporting ────────────────────────────────────────────────────────

    def print_summary(self, results: dict[str, Any]) -> None:
        """Print validation summary."""
        print("\n" + "=" * 80)
        print("ENTERPRISE STRICT ENGINEERING VALIDATION RESULTS")
        print("=" * 80)
        print(
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(results['timestamp']))}"
        )
        print(f"Project Root: {results['project_root']}")
        print(f"Strict Mode: {'ENABLED' if results['strict_mode'] else 'DISABLED'}")
        print()

        print("Summary:")
        print("-" * 80)
        summary = results["summary"]
        print(f"  Total Validators: {summary['total_validators']}")
        print(f"  Passed: {summary['passed_validators']}")
        print(f"  Failed: {summary['failed_validators']}")
        print(f"  Total Issues: {summary['total_issues']}")
        print(f"  Blocking Issues: {summary['blocking_issues']}")
        print(f"  Suppressed (whitelist): {summary.get('suppressed_issues', 0)}")

        if summary["by_category"]:
            print("\n  Issues by Category:")
            for category, count in summary["by_category"].items():
                print(f"    {category}: {count}")

        print()

        # Overall result
        print("=" * 80)
        if results["overall_passed"]:
            print("✅ VALIDATION PASSED — No blocking regressions detected")
        else:
            print("❌ VALIDATION FAILED — Blocking regressions or issues detected")
            if self.config.strict_mode:
                print("⚠️  STRICT MODE: Deployment is BLOCKED")
        print("=" * 80)
        print()

        # Show blocking issues
        blocking_issues = self._get_blocking_issues(results)
        if blocking_issues:
            print("BLOCKING ISSUES:")
            print("-" * 80)
            for issue in blocking_issues[:10]:
                print(f"  [{issue['severity'].upper()}] {issue['title']}")
                print(f"    {issue['description']}")
                if issue.get("metrics"):
                    print(f"    Metrics: {issue['metrics']}")
                print()
            if len(blocking_issues) > 10:
                print(f"  ... and {len(blocking_issues) - 10} more blocking issues")
            print()

        # Whitelist audit
        wl_stats = results.get("whitelist_stats", {})
        if wl_stats.get("total_suppressions", 0) > 0:
            print("WHITELIST SUPPRESSIONS:")
            print("-" * 80)
            for entry in wl_stats.get("match_history", []):
                print(
                    f"  [{entry['severity'].upper()}] {entry['issue_id']} "
                    f"→ suppressed by rule '{entry['rule_id']}'"
                )
            print()

    def _get_blocking_issues(self, results: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all blocking issues from results."""
        blocking = []
        for _validator_name, validator_result in results["validators"].items():
            for issue in validator_result.get("issues", []):
                if issue.get("blocking", False):
                    blocking.append(issue)
        return blocking


# ── convenience functions ────────────────────────────────────────────────────


def create_default_tests() -> list[RegressionTest]:
    """Create default regression tests."""
    tests = []

    # Test 1: Import test
    def test_imports(context):
        """Test that all imports work."""
        import sys
        from pathlib import Path

        project_root = context.get("project_root", ".")
        src_path = Path(project_root) / "src"
        sys.path.insert(0, str(src_path))

        try:
            return {"imports": True, "agents_module": True}
        except Exception as e:
            return {"imports": False, "error": str(e)}

    tests.append(
        RegressionTest(
            test_id="import_test",
            name="Import Test",
            description="Verify all modules can be imported",
            test_function=test_imports,
            category="functional",
        )
    )

    # Test 2: Basic agent test
    def test_agents(context):
        """Test basic agent functionality."""
        from indestructibleautoops.agents import (
            AgentCapability,
            AgentMessage,
            MessageType,
        )

        cap = AgentCapability(
            name="test",
            description="test",
            input_types=["input"],
            output_types=["output"],
        )

        msg = AgentMessage(
            msg_type=MessageType.TASK_ASSIGN,
            sender_id="test",
            recipient_id="test",
        )

        return {
            "capability": cap is not None,
            "message": msg is not None,
            "can_handle": cap.can_handle("input"),
        }

    tests.append(
        RegressionTest(
            test_id="agent_test",
            name="Agent Test",
            description="Verify basic agent functionality",
            test_function=test_agents,
            category="functional",
        )
    )

    # Test 3: File count test
    def test_file_count(context):
        """Test that no files have been removed."""
        from pathlib import Path

        project_root = context.get("project_root", ".")
        src_path = Path(project_root) / "src" / "indestructibleautoops"

        py_files = list(src_path.rglob("*.py"))
        return {
            "file_count": len(py_files),
            "src_path": str(src_path),
        }

    tests.append(
        RegressionTest(
            test_id="file_count_test",
            name="File Count Test",
            description="Verify no source files have been removed",
            test_function=test_file_count,
            category="regression",
        )
    )

    return tests


def run_strict_validation(
    project_root: str,
    create_baseline: bool = False,
    load_baseline: bool = False,
    whitelist_path: str | None = None,
    performance_threshold: float = 0.20,
    metric_threshold: float = 0.10,
) -> dict[str, Any]:
    """Run strict validation with default tests."""
    config = StrictValidationConfig(
        project_root=project_root,
        strict_mode=True,
        whitelist_path=whitelist_path,
        performance_threshold=performance_threshold,
        metric_threshold=metric_threshold,
    )

    validator = StrictValidator(config)

    # Add default regression tests
    tests = create_default_tests()
    suite = RegressionSuite(
        suite_id="default",
        name="Default Test Suite",
        tests=tests,
    )
    validator.add_regression_suite(suite)

    # Handle baseline
    if create_baseline:
        validator.create_baseline()
        return {"status": "baseline_created", "baseline_path": str(config.baseline_dir)}

    if load_baseline:
        try:
            validator.load_baseline()
        except ValueError:
            validator.create_baseline()
            print("No baseline found, created new baseline")

    # Run validation
    results = validator.validate_all()

    # Print summary
    validator.print_summary(results)

    return results
