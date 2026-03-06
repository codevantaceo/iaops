"""
Validation Engine — pluggable validator pipeline.

Provides a base class that orchestrates an ordered pipeline of
validators, applies whitelist suppression, and produces a
consolidated report.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .validator import BaseValidator, Severity, ValidationResult
from .whitelist import WhitelistManager


class ValidationEngine:
    """Pluggable validation engine with ordered pipeline.

    Usage::

        engine = ValidationEngine(
            project_root="/path/to/project",
            strict_mode=True,
            whitelist_path="configs/validation_whitelist.yaml",
        )
        engine.register("files", FileCheckValidator(strict_mode=True))
        engine.register("performance", PerformanceValidator(strict_mode=True))

        results = engine.run()
        engine.print_summary(results)
    """

    def __init__(
        self,
        project_root: str,
        strict_mode: bool = True,
        baseline_dir: str = ".baselines",
        output_dir: str = ".validation",
        whitelist_path: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.strict_mode = strict_mode
        self._baseline_dir = Path(baseline_dir)
        self._output_dir = Path(output_dir)
        self._whitelist = self._load_whitelist(whitelist_path)

        # Ordered pipeline: list of (name, validator) tuples
        self._pipeline: list[tuple[str, BaseValidator]] = []

    # ── pipeline management ──────────────────────────────────────────

    def register(self, name: str, validator: BaseValidator) -> None:
        """Append a validator to the pipeline."""
        self._pipeline.append((name, validator))

    @property
    def pipeline_names(self) -> list[str]:
        """Return the ordered list of validator names."""
        return [name for name, _ in self._pipeline]

    # ── execution ────────────────────────────────────────────────────

    def run(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute the full validation pipeline.

        Returns a consolidated results dict compatible with
        ``StrictValidator.validate_all()`` output format.
        """
        context = context or {}
        context["project_root"] = self.project_root

        results: dict[str, Any] = {
            "timestamp": time.time(),
            "strict_mode": self.strict_mode,
            "project_root": self.project_root,
            "pipeline": self.pipeline_names,
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

        for name, validator in self._pipeline:
            result = validator.validate(context)

            # Apply whitelist suppression
            suppressed = self._apply_whitelist(result)
            results["summary"]["suppressed_issues"] += suppressed

            results["validators"][name] = result.to_dict()

            # Update summary
            results["summary"]["total_validators"] += 1
            if result.passed:
                results["summary"]["passed_validators"] += 1
            else:
                results["summary"]["failed_validators"] += 1
                results["overall_passed"] = False

            results["summary"]["total_issues"] += len(result.issues)
            results["summary"]["blocking_issues"] += len(result.get_blocking_issues())

            for issue in result.issues:
                cat = issue.category
                if cat not in results["summary"]["by_category"]:
                    results["summary"]["by_category"][cat] = 0
                results["summary"]["by_category"][cat] += 1

        results["whitelist_stats"] = self._whitelist.get_stats()

        # Persist
        self._save_results(results)
        return results

    # ── baseline management ──────────────────────────────────────────

    def create_baseline(self) -> None:
        """Save current validator baselines."""
        self._baseline_dir.mkdir(parents=True, exist_ok=True)
        for name, validator in self._pipeline:
            path = self._baseline_dir / f"{name}.json"
            validator.save_baseline(path)

    def load_baseline(self) -> None:
        """Load baselines for all registered validators."""
        for name, validator in self._pipeline:
            path = self._baseline_dir / f"{name}.json"
            if path.exists():
                validator.load_baseline(path)

    # ── whitelist ────────────────────────────────────────────────────

    def _load_whitelist(self, path: str | None) -> WhitelistManager:
        if path is None:
            return WhitelistManager()
        p = Path(path)
        if not p.exists():
            return WhitelistManager()
        if p.suffix in (".yaml", ".yml"):
            return WhitelistManager.load_yaml(p)
        return WhitelistManager.load(p)

    def _apply_whitelist(self, result: ValidationResult) -> int:
        suppressed = 0
        for issue in result.issues:
            should_suppress, rule = self._whitelist.should_suppress(
                issue_id=issue.issue_id,
                severity=issue.severity.value,
                category=issue.category,
                file_path=issue.file_path,
            )
            if should_suppress and rule is not None:
                issue.severity = Severity.INFO
                issue.description = f"[SUPPRESSED by rule '{rule.rule_id}'] {issue.description}"
                issue.metrics["suppressed"] = True
                issue.metrics["suppressed_by_rule"] = rule.rule_id
                suppressed += 1

        # Recalculate pass status
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

    # ── persistence ──────────────────────────────────────────────────

    def _save_results(self, results: dict[str, Any]) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        with open(self._output_dir / f"validation_{ts}.json", "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        with open(self._output_dir / "validation_latest.json", "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # ── reporting ────────────────────────────────────────────────────

    def print_summary(self, results: dict[str, Any]) -> None:
        """Print a human-readable summary."""
        print("\n" + "=" * 80)
        print("VALIDATION ENGINE RESULTS")
        print("=" * 80)
        print(f"Pipeline: {' → '.join(results.get('pipeline', []))}")
        print(f"Strict Mode: {'ENABLED' if results['strict_mode'] else 'DISABLED'}")

        summary = results["summary"]
        print(f"\nValidators: {summary['passed_validators']}/{summary['total_validators']} passed")
        print(f"Issues: {summary['total_issues']} total, {summary['blocking_issues']} blocking")
        print(f"Suppressed: {summary.get('suppressed_issues', 0)}")

        if results["overall_passed"]:
            print("\n✅ VALIDATION PASSED")
        else:
            print("\n❌ VALIDATION FAILED — deployment blocked")

        print("=" * 80)
