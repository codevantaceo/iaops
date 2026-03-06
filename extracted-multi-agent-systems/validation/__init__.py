"""
Enterprise Strict Engineering Validation System.

Provides comprehensive validation tools to detect and block
critical regressions in quality, performance, and functionality,
with false-positive suppression via a whitelist mechanism.
"""

from .engine import ValidationEngine
from .file_validator import FileCheckValidator
from .functional_validator import FunctionalTest, FunctionalValidator
from .metrics import (
    BlockingPolicy,
    MetricResult,
    MetricsValidator,
    MetricThreshold,
    get_default_thresholds,
    percentile,
)
from .performance_validator import PerformanceTest, PerformanceValidator
from .regression import RegressionSuite, RegressionTest, RegressionValidator
from .regression_detector import (
    RegressionDetector,
    detect_numeric_regression,
    detect_structural_regression,
)
from .strict_validator import (
    StrictValidationConfig,
    StrictValidator,
    run_strict_validation,
)
from .validator import STRICT_MODE, BaseValidator, Severity, ValidationResult
from .whitelist import ExemptionStatus, WhitelistManager, WhitelistRule

__all__ = [
    # Core validation
    "BaseValidator",
    "ValidationResult",
    "Severity",
    "STRICT_MODE",
    # Validation engine
    "ValidationEngine",
    # Regression testing
    "RegressionTest",
    "RegressionSuite",
    "RegressionValidator",
    # Standalone regression detector
    "RegressionDetector",
    "detect_numeric_regression",
    "detect_structural_regression",
    # File validator
    "FileCheckValidator",
    # Functional validator
    "FunctionalValidator",
    "FunctionalTest",
    # Performance validator
    "PerformanceValidator",
    "PerformanceTest",
    # Advanced metrics
    "MetricsValidator",
    "MetricThreshold",
    "MetricResult",
    "BlockingPolicy",
    "get_default_thresholds",
    "percentile",
    # Strict validation
    "StrictValidator",
    "StrictValidationConfig",
    "run_strict_validation",
    # Whitelist / exemptions
    "WhitelistManager",
    "WhitelistRule",
    "ExemptionStatus",
]
