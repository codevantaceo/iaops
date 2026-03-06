from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class DependencyFinding:
    name: str
    version: str
    severity: str | None
    cves: list[str]
    license: str | None

    @property
    def is_blocking(self) -> bool:
        return (self.severity or "").lower() in {"critical", "high"}


def _extract_components(data: dict) -> list[dict]:
    return data.get("components") or data.get("bom", {}).get("components") or []


def _extract_vulnerabilities(data: dict) -> list[dict]:
    return data.get("vulnerabilities") or data.get("bom", {}).get("vulnerabilities") or []


def _map_vulnerabilities(vulnerabilities: list[dict]) -> dict[str, dict]:
    mapped: dict[str, dict] = {}
    for vuln in vulnerabilities:
        for ref in vuln.get("affects", []):
            ref_id = ref.get("ref")
            if not ref_id:
                continue
            current = mapped.get(ref_id, {"severity": vuln.get("severity", "").lower(), "ids": []})
            current["severity"] = max(current["severity"], vuln.get("severity", "").lower())
            current["ids"].append(vuln.get("id"))
            mapped[ref_id] = current
    return mapped


def load_sbom(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_dependencies(
    sbom: dict,
    *,
    allowed_licenses: set[str] | None = None,
) -> list[DependencyFinding]:
    components = _extract_components(sbom)
    vulnerabilities = _extract_vulnerabilities(sbom)
    vuln_map = _map_vulnerabilities(vulnerabilities)

    findings: list[DependencyFinding] = []
    for component in components:
        comp_ref = component.get("bom-ref") or component.get("purl") or component.get("name")
        license_name = None
        licenses = component.get("licenses") or []
        if licenses:
            license_name = licenses[0].get("license", {}).get("name") or licenses[0].get("license", {}).get("id")

        vuln_info = vuln_map.get(comp_ref, {})
        severity = vuln_info.get("severity")
        cves = vuln_info.get("ids", [])

        if allowed_licenses and license_name and license_name not in allowed_licenses:
            severity = severity or "policy"
            cves.append("LICENSE_POLICY")

        findings.append(
            DependencyFinding(
                name=component.get("name", "unknown"),
                version=component.get("version", "unknown"),
                severity=severity,
                cves=cves,
                license=license_name,
            )
        )
    return findings


def summarize(findings: list[DependencyFinding]) -> tuple[int, int]:
    total = len(findings)
    blockers = sum(1 for finding in findings if finding.is_blocking)
    return total, blockers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dependency and vulnerability gate using SBOM data.")
    parser.add_argument("--sbom", required=True, help="Path to SBOM in CycloneDX JSON format.")
    parser.add_argument("--allowed-licenses", default="", help="Comma-separated license allowlist (e.g., Apache-2.0,MIT).")
    parser.add_argument("--fail-on-severity", default="high", choices=["high", "critical"], help="Minimum severity that fails the gate.")
    parser.add_argument("--output", default="dependency-report.json", help="Where to write the evaluation report.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    allowed = {item.strip() for item in args.allowed_licenses.split(",") if item.strip()}
    sbom = load_sbom(args.sbom)
    findings = evaluate_dependencies(sbom, allowed_licenses=allowed or None)
    total, blockers = summarize(findings)

    report = {
        "total_components": total,
        "blocking_findings": blockers,
        "findings": [finding.__dict__ for finding in findings],
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")

    fail_levels = {"high": {"critical", "high"}, "critical": {"critical"}}
    if any((finding.severity or "").lower() in fail_levels[args.fail_on_severity] for finding in findings):
        raise SystemExit("Dependency gate failed due to high-severity vulnerabilities or policy violations.")


if __name__ == "__main__":
    main()
