"""
File Check Validator.

Validates source file integrity: counts, presence of required files,
and detects unexpected removals compared to baseline.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .regression_detector import RegressionDetector
from .validator import BaseValidator, Severity, ValidationIssue, ValidationResult


class FileCheckValidator(BaseValidator):
    """Validator that checks source file integrity against baseline."""

    def __init__(
        self,
        strict_mode: bool = True,
        required_paths: list[str] | None = None,
    ) -> None:
        super().__init__(name="FileCheckValidator", strict_mode=strict_mode)
        self._required_paths = required_paths or []
        self._detector = RegressionDetector(
            metric_threshold=0.10,
            strict_mode=strict_mode,
        )

    def validate(self, context: dict[str, Any]) -> ValidationResult:
        """Run file integrity checks."""
        result = ValidationResult(validator_name=self.name)
        start = time.time()

        project_root = Path(context.get("project_root", "."))
        src_path = project_root / "src"
        if not src_path.exists():
            src_path = project_root

        # 1. Count source files
        py_files = sorted(str(f.relative_to(project_root)) for f in src_path.rglob("*.py"))
        file_count = len(py_files)

        result.metrics["source_file_count"] = file_count
        result.metrics["source_files"] = py_files[:50]  # cap for readability

        # Check regression against baseline
        issue = self.check_regression(
            metric_name="source_file_count",
            current_value=float(file_count),
            threshold=0.05,  # 5% — even 1 file removal is significant
            higher_is_better=True,
        )
        if issue:
            issue.source = "file_check"
            result.add_issue(issue)

        # 2. Check required paths
        for req_path in self._required_paths:
            full = project_root / req_path
            if not full.exists():
                result.add_issue(
                    ValidationIssue(
                        issue_id=f"missing_required_path_{req_path}",
                        severity=Severity.CRITICAL if self.strict_mode else Severity.ERROR,
                        category="file_integrity",
                        title=f"Required path missing: {req_path}",
                        description=f"Expected path '{req_path}' does not exist in project root.",
                        source="file_check",
                    )
                )

        # 3. Detect removed files vs baseline
        if "source_files" in self._baseline:
            baseline_files = set(self._baseline["source_files"])
            current_files = set(py_files)
            removed = baseline_files - current_files
            if removed:
                result.add_issue(
                    ValidationIssue(
                        issue_id="files_removed",
                        severity=Severity.CRITICAL if self.strict_mode else Severity.WARNING,
                        category="file_integrity",
                        title=f"{len(removed)} source file(s) removed",
                        description=f"Removed files: {', '.join(sorted(removed))}",
                        source="file_check",
                        metrics={"removed_files": sorted(removed)},
                    )
                )

        # Update baseline
        self._baseline["source_file_count"] = file_count
        self._baseline["source_files"] = py_files

        result.duration_seconds = time.time() - start
        return result
