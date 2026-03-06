"""
Snyk Security Scanner

This module provides integration with Snyk for dependency vulnerability scanning.
It wraps the Snyk CLI and parses JSON output to produce SecurityIssue objects.

Requirements:
- Snyk CLI must be installed and available in PATH
- Snyk API token must be configured (via SNYK_TOKEN environment variable or snyk auth)
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from .scanner import (
    SecurityIssue,
    SecurityIssueType,
    SecurityScanResult,
    SecuritySeverity,
)


class SnykScanner:
    """Scanner implementation for Snyk dependency vulnerability scanning."""

    SCANNER_NAME = "Snyk"
    SCANNER_VERSION = "CLI"

    def __init__(self, token: str | None = None, binary_path: str = "snyk"):
        """
        Initialize the Snyk scanner.

        Args:
            token: Optional Snyk API token. If None, reads from SNYK_TOKEN env var.
            binary_path: Path to Snyk binary (default: 'snyk')
        """
        self._token = token or None
        self._binary_path = binary_path
        self._version = None

    @property
    def scanner_name(self) -> str:
        return self.SCANNER_NAME

    @property
    def scanner_version(self) -> str:
        if self._version is None:
            self._version = self._get_snyk_version()
        return self._version

    def _get_snyk_version(self) -> str:
        """Get the installed Snyk version."""
        try:
            result = subprocess.run(
                [self._binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def _get_snyk_token(self) -> str | None:
        """Get Snyk token from instance or environment."""
        if self._token:
            return self._token
        import os

        return os.environ.get("SNYK_TOKEN")

    def is_available(self) -> bool:
        """Check if Snyk CLI is available and configured."""
        try:
            # Check if binary exists
            result = subprocess.run(
                [self._binary_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def scan(
        self,
        target: str,
        config: dict[str, Any] | None = None,
    ) -> SecurityScanResult:
        """
        Perform a Snyk scan on the specified target.

        Args:
            target: Path to the project directory to scan
            config: Optional configuration with keys:
                - severity_threshold: Minimum severity to report (default: 'low')
                -scan_all_dependencies: Scan all dependencies including dev (default: True)
                - org: Snyk organization ID (optional)
                - project: Snyk project name (optional)

        Returns:
            SecurityScanResult containing the scan findings
        """
        config = config or {}

        # Generate scan_id using a timestamp if target doesn't exist
        try:
            scan_id = f"snyk-{int(Path(target).stat().st_mtime)}"
        except (FileNotFoundError, OSError):
            import time

            scan_id = f"snyk-{int(time.time())}"

        result = SecurityScanResult(
            scanner_name=self.scanner_name,
            scan_id=scan_id,
            target=target,
            status="running",
        )

        if not self.is_available():
            result.status = "failed"
            result.error_message = "Snyk CLI is not available or not configured"
            return result

        try:
            # Build Snyk command
            cmd = self._build_snyk_command(target, config)

            # Execute Snyk scan
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if output.returncode != 0:
                result.status = "failed"
                result.error_message = f"Snyk scan failed: {output.stderr}"
                return result

            # Parse JSON output
            snyk_data = json.loads(output.stdout)

            # Convert to SecurityIssue objects
            issues = self._parse_snyk_results(snyk_data)

            for issue in issues:
                result.add_issue(issue)

            result.status = "success"

        except subprocess.TimeoutExpired:
            result.status = "failed"
            result.error_message = "Snyk scan timed out"
        except json.JSONDecodeError as e:
            result.status = "failed"
            result.error_message = f"Failed to parse Snyk JSON output: {e}"
        except Exception as e:
            result.status = "failed"
            result.error_message = f"Unexpected error during Snyk scan: {e}"

        return result

    def _build_snyk_command(self, target: str, config: dict[str, Any]) -> list[str]:
        """Build the Snyk CLI command."""
        cmd = [
            self._binary_path,
            "test",
            target,
            "--json",
        ]

        # Add optional flags
        severity_threshold = config.get("severity_threshold", "low")
        cmd.append(f"--severity-threshold={severity_threshold}")

        scan_all = config.get("scan_all_dependencies", True)
        if scan_all:
            cmd.append("--all-projects")

        # Add organization if specified
        if "org" in config:
            cmd.extend(["--org", config["org"]])

        # Add project name if specified
        if "project" in config:
            cmd.extend(["--project-name", config["project"]])

        return cmd

    def _parse_snyk_results(self, snyk_data: dict[str, Any]) -> list[SecurityIssue]:
        """
        Parse Snyk JSON output into SecurityIssue objects.

        Snyk JSON format:
        {
            "vulnerabilities": [
                {
                    "id": "SNYK-PY-XXXXX",
                    "title": "Title",
                    "description": "Description",
                    "severity": "high",
                    "cvssScore": 7.5,
                    "cvssVector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    "references": ["https://..."],
                    "packageManager": "pip",
                    "packageName": "requests",
                    "version": "2.0.0",
                    "semver": {"vulnerable": ["2.0.0"], "patched": ["2.31.0"]},
                    "identifiers": {
                        "CVE": ["CVE-2024-1234"],
                        "CWE": ["CWE-79"]
                    },
                    "credit": [...],
                    "publicationTime": "2024-01-15T10:00:00.000Z",
                    "disclosureTime": "2024-01-01T00:00:00.000Z",
                },
                ...
            ],
            "ok": false,
            ...
        }
        """
        issues = []
        vulnerabilities = snyk_data.get("vulnerabilities", [])

        for vuln in vulnerabilities:
            # Map Snyk severity to SecuritySeverity
            severity = self._map_snyk_severity(vuln.get("severity", "low"))

            # Extract identifiers
            cve_ids = []
            cwe_ids = []

            identifiers = vuln.get("identifiers", {})
            if "CVE" in identifiers:
                cve_ids = identifiers["CVE"]
            if "CWE" in identifiers:
                cwe_ids = identifiers["CWE"]

            # Extract semver info for fixed version
            semver = vuln.get("semver", {})
            patched_versions = semver.get("patched", [])
            fixed_version = patched_versions[0] if patched_versions else None

            # Create SecurityIssue
            issue = SecurityIssue(
                issue_id=vuln.get("id", "unknown"),
                title=vuln.get("title", "Unknown vulnerability"),
                description=vuln.get("description", ""),
                severity=severity,
                issue_type=SecurityIssueType.DEPENDENCY,
                scanner_name=self.scanner_name,
                # Vulnerability details
                cve_id=cve_ids[0] if cve_ids else None,
                cwe_id=cwe_ids[0] if cwe_ids else None,
                cvss_score=vuln.get("cvssScore"),
                cvss_vector=vuln.get("cvssVector"),
                # Dependency details
                package_name=vuln.get("packageName"),
                package_version=vuln.get("version"),
                fixed_version=fixed_version,
                # References
                references=vuln.get("references", []),
            )

            issues.append(issue)

        return issues

    def _map_snyk_severity(self, snyk_severity: str) -> SecuritySeverity:
        """
        Map Snyk severity levels to SecuritySeverity.

        Snyk severity levels: critical, high, medium, low
        """
        severity_map = {
            "critical": SecuritySeverity.CRITICAL,
            "high": SecuritySeverity.HIGH,
            "medium": SecuritySeverity.MEDIUM,
            "low": SecuritySeverity.LOW,
        }

        return severity_map.get(snyk_severity.lower(), SecuritySeverity.LOW)


def create_snyk_scanner(
    token: str | None = None,
    binary_path: str = "snyk",
) -> SnykScanner:
    """
    Factory function to create a Snyk scanner instance.

    Args:
        token: Optional Snyk API token
        binary_path: Path to Snyk binary

    Returns:
        Configured SnykScanner instance
    """
    return SnykScanner(token=token, binary_path=binary_path)
