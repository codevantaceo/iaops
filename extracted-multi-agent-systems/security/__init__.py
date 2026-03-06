"""
Security Scanning Module

This module provides enterprise-grade security scanning capabilities with
support for multiple scanners (Snyk, Trivy, OWASP, etc.) and a unified
framework for vulnerability management.
"""

from .scanner import (
    ScannerRegistry,
    SecurityIssue,
    SecurityIssueType,
    SecurityScanner,
    SecurityScanResult,
    SecuritySeverity,
    scanner_registry,
)
from .snyk_scanner import (
    SnykScanner,
    create_snyk_scanner,
)

__all__ = [
    # Enums
    "SecuritySeverity",
    "SecurityIssueType",
    # Dataclasses
    "SecurityIssue",
    "SecurityScanResult",
    # Protocol
    "SecurityScanner",
    # Registry
    "ScannerRegistry",
    "scanner_registry",
    # Scanners
    "SnykScanner",
    "create_snyk_scanner",
]
