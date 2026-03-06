"""
Advanced Metrics Collector for Enterprise Validation.

Provides configurable metric collection including:
  - p95/p99 latency tracking
  - Code coverage change detection
  - Cyclomatic complexity tracking
  - Security vulnerability count
  - Progressive blocking (warn → block)
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validator import BaseValidator, Severity, ValidationIssue, ValidationResult

# ── Metric definitions ───────────────────────────────────────────────


class BlockingPolicy:
    """Progressive blocking: warn first, block after threshold."""

    IMMEDIATE = "immediate"  # block on first violation
    PROGRESSIVE = "progressive"  # warn → block after N consecutive violations


@dataclass
class MetricThreshold:
    """Configurable threshold for a single metric.

    Attributes:
        name: Human-readable metric name.
        min_value: Minimum acceptable value (None = no lower bound).
        max_value: Maximum acceptable value (None = no upper bound).
        regression_pct: Maximum allowed regression percentage vs baseline.
        higher_is_better: If True, decreasing values are regressions.
        blocking_policy: IMMEDIATE or PROGRESSIVE.
        warn_count_before_block: For PROGRESSIVE, how many consecutive
            warnings before escalating to a block.
    """

    name: str
    min_value: float | None = None
    max_value: float | None = None
    regression_pct: float = 0.10  # 10% default
    higher_is_better: bool = True
    blocking_policy: str = BlockingPolicy.IMMEDIATE
    warn_count_before_block: int = 3


@dataclass
class MetricResult:
    """Result of a single metric collection."""

    name: str
    value: float
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Percentile calculator ────────────────────────────────────────────


def percentile(data: list[float], pct: float) -> float:
    """Calculate the p-th percentile of a list of values.

    Uses the interpolation method consistent with NumPy's default.
    """
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    k = (n - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


# ── Metric collectors ────────────────────────────────────────────────


def collect_latency_metrics(
    durations: list[float],
) -> dict[str, MetricResult]:
    """Compute p50, p95, p99 from a list of durations (seconds)."""
    if not durations:
        return {}
    return {
        "latency_p50": MetricResult(
            name="latency_p50",
            value=percentile(durations, 50),
            unit="seconds",
        ),
        "latency_p95": MetricResult(
            name="latency_p95",
            value=percentile(durations, 95),
            unit="seconds",
        ),
        "latency_p99": MetricResult(
            name="latency_p99",
            value=percentile(durations, 99),
            unit="seconds",
        ),
        "latency_mean": MetricResult(
            name="latency_mean",
            value=sum(durations) / len(durations),
            unit="seconds",
        ),
    }


def collect_code_coverage(project_root: str | Path) -> MetricResult | None:
    """Attempt to read code coverage from coverage.json or .coverage.

    Returns None if coverage data is not available.
    """
    root = Path(project_root)

    # Try coverage.json (produced by `coverage json`)
    cov_json = root / "coverage.json"
    if cov_json.exists():
        with open(cov_json) as f:
            data = json.load(f)
        total = data.get("totals", {}).get("percent_covered", 0.0)
        return MetricResult(
            name="code_coverage",
            value=total,
            unit="percent",
            metadata={"source": str(cov_json)},
        )

    # Try htmlcov/status.json
    status_json = root / "htmlcov" / "status.json"
    if status_json.exists():
        with open(status_json) as f:
            data = json.load(f)
        total = data.get("totals", {}).get("percent_covered", 0.0)
        return MetricResult(
            name="code_coverage",
            value=total,
            unit="percent",
            metadata={"source": str(status_json)},
        )

    return None


def collect_file_metrics(project_root: str | Path) -> dict[str, MetricResult]:
    """Collect file-level metrics: count, total lines, avg complexity."""
    root = Path(project_root)
    src_path = root / "src"
    if not src_path.exists():
        src_path = root

    py_files = list(src_path.rglob("*.py"))
    total_lines = 0
    for f in py_files:
        try:
            total_lines += len(f.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            pass

    return {
        "file_count": MetricResult(
            name="file_count",
            value=float(len(py_files)),
            unit="files",
        ),
        "total_lines": MetricResult(
            name="total_lines",
            value=float(total_lines),
            unit="lines",
        ),
        "avg_lines_per_file": MetricResult(
            name="avg_lines_per_file",
            value=total_lines / max(len(py_files), 1),
            unit="lines/file",
        ),
    }


def collect_complexity_metrics(project_root: str | Path) -> MetricResult | None:
    """Attempt to measure average cyclomatic complexity via radon.

    Returns None if radon is not installed.
    """
    try:
        result = subprocess.run(
            ["radon", "cc", "-a", "-s", "-n", "C", str(Path(project_root) / "src")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Parse average complexity from last line
        for line in reversed(result.stdout.splitlines()):
            if "Average complexity" in line:
                # Format: "Average complexity: A (1.234)"
                parts = line.split("(")
                if len(parts) >= 2:
                    avg = float(parts[-1].rstrip(")"))
                    return MetricResult(
                        name="avg_cyclomatic_complexity",
                        value=avg,
                        unit="cc",
                        metadata={"raw_output": result.stdout[-500:]},
                    )
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def collect_security_vulnerability_count(
    project_root: str | Path,
) -> MetricResult | None:
    """Count known vulnerabilities via pip-audit (if available).

    Returns None if pip-audit is not installed.
    """
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json", "--output", "-"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            vuln_count = len(data) if isinstance(data, list) else 0
            return MetricResult(
                name="security_vulnerabilities",
                value=float(vuln_count),
                unit="vulnerabilities",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


# ── MetricsValidator ─────────────────────────────────────────────────


class MetricsValidator(BaseValidator):
    """Validator that collects and checks advanced metrics.

    Supports configurable thresholds and progressive blocking.
    """

    def __init__(
        self,
        thresholds: list[MetricThreshold] | None = None,
        strict_mode: bool = True,
        collect_coverage: bool = True,
        collect_complexity: bool = False,
        collect_security: bool = False,
    ) -> None:
        super().__init__(name="MetricsValidator", strict_mode=strict_mode)
        self._thresholds = {t.name: t for t in (thresholds or [])}
        self._collect_coverage = collect_coverage
        self._collect_complexity = collect_complexity
        self._collect_security = collect_security
        self._consecutive_warnings: dict[str, int] = {}

    def add_threshold(self, threshold: MetricThreshold) -> None:
        """Register a metric threshold."""
        self._thresholds[threshold.name] = threshold

    def validate(self, context: dict[str, Any]) -> ValidationResult:
        """Collect metrics and check against thresholds + baselines."""
        result = ValidationResult(validator_name=self.name)
        start = time.time()

        project_root = context.get("project_root", ".")
        metrics: dict[str, MetricResult] = {}

        # Always collect file metrics
        metrics.update(collect_file_metrics(project_root))

        # Optional collectors
        if self._collect_coverage:
            cov = collect_code_coverage(project_root)
            if cov:
                metrics[cov.name] = cov

        if self._collect_complexity:
            cc = collect_complexity_metrics(project_root)
            if cc:
                metrics[cc.name] = cc

        if self._collect_security:
            sec = collect_security_vulnerability_count(project_root)
            if sec:
                metrics[sec.name] = sec

        # Store collected values in result.metrics
        for name, mr in metrics.items():
            result.metrics[name] = {
                "value": mr.value,
                "unit": mr.unit,
                "timestamp": mr.timestamp,
            }

        # Check thresholds
        for name, mr in metrics.items():
            threshold = self._thresholds.get(name)
            if threshold:
                issue = self._check_threshold(mr, threshold)
                if issue:
                    result.add_issue(issue)

            # Check regression against baseline
            issue = self.check_regression(
                metric_name=name,
                current_value=mr.value,
                threshold=self._thresholds[name].regression_pct
                if name in self._thresholds
                else 0.10,
                higher_is_better=self._thresholds[name].higher_is_better
                if name in self._thresholds
                else True,
            )
            if issue:
                # Apply progressive blocking
                issue = self._apply_progressive_blocking(name, issue)
                result.add_issue(issue)

        # Update baseline with current values
        for name, mr in metrics.items():
            self._baseline[name] = mr.value

        result.duration_seconds = time.time() - start
        return result

    def _check_threshold(
        self, metric: MetricResult, threshold: MetricThreshold
    ) -> ValidationIssue | None:
        """Check a metric against its configured threshold."""
        if threshold.min_value is not None and metric.value < threshold.min_value:
            return ValidationIssue(
                issue_id=f"threshold_{metric.name}_below_min",
                severity=Severity.CRITICAL if self.strict_mode else Severity.WARNING,
                category="threshold",
                title=f"Metric below minimum: {metric.name}",
                description=(
                    f"Metric '{metric.name}' is {metric.value:.2f} {metric.unit}, "
                    f"below minimum {threshold.min_value:.2f}"
                ),
                metrics={
                    "current": metric.value,
                    "min_required": threshold.min_value,
                },
            )

        if threshold.max_value is not None and metric.value > threshold.max_value:
            return ValidationIssue(
                issue_id=f"threshold_{metric.name}_above_max",
                severity=Severity.CRITICAL if self.strict_mode else Severity.WARNING,
                category="threshold",
                title=f"Metric above maximum: {metric.name}",
                description=(
                    f"Metric '{metric.name}' is {metric.value:.2f} {metric.unit}, "
                    f"above maximum {threshold.max_value:.2f}"
                ),
                metrics={
                    "current": metric.value,
                    "max_allowed": threshold.max_value,
                },
            )

        return None

    def _apply_progressive_blocking(
        self, metric_name: str, issue: ValidationIssue
    ) -> ValidationIssue:
        """Downgrade severity for progressive blocking policy."""
        threshold = self._thresholds.get(metric_name)
        if not threshold or threshold.blocking_policy != BlockingPolicy.PROGRESSIVE:
            return issue

        count = self._consecutive_warnings.get(metric_name, 0) + 1
        self._consecutive_warnings[metric_name] = count

        if count < threshold.warn_count_before_block:
            # Downgrade to WARNING (non-blocking)
            issue.severity = Severity.WARNING
            issue.description = (
                f"[PROGRESSIVE {count}/{threshold.warn_count_before_block}] {issue.description}"
            )
        else:
            # Escalate to blocking
            issue.description = (
                f"[PROGRESSIVE ESCALATED after {count} consecutive warnings] {issue.description}"
            )

        return issue


# ── Default thresholds ───────────────────────────────────────────────


def get_default_thresholds() -> list[MetricThreshold]:
    """Return sensible default thresholds."""
    return [
        MetricThreshold(
            name="code_coverage",
            min_value=60.0,  # minimum 60% coverage
            regression_pct=0.05,  # 5% drop is a regression
            higher_is_better=True,
        ),
        MetricThreshold(
            name="file_count",
            regression_pct=0.10,
            higher_is_better=True,
        ),
        MetricThreshold(
            name="total_lines",
            regression_pct=0.20,  # 20% drop in total lines
            higher_is_better=True,
        ),
        MetricThreshold(
            name="avg_cyclomatic_complexity",
            max_value=10.0,  # max average CC of 10
            regression_pct=0.15,
            higher_is_better=False,  # lower complexity is better
        ),
        MetricThreshold(
            name="security_vulnerabilities",
            max_value=0.0,  # zero tolerance
            regression_pct=0.0,
            higher_is_better=False,  # fewer is better
        ),
        MetricThreshold(
            name="latency_p95",
            regression_pct=0.20,
            higher_is_better=False,  # lower latency is better
            blocking_policy=BlockingPolicy.PROGRESSIVE,
            warn_count_before_block=3,
        ),
        MetricThreshold(
            name="latency_p99",
            regression_pct=0.25,
            higher_is_better=False,
            blocking_policy=BlockingPolicy.PROGRESSIVE,
            warn_count_before_block=3,
        ),
    ]
