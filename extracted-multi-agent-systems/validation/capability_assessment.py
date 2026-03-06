"""
Capability evaluation helpers for honest, evidence-based classification.

The evaluator is intentionally conservative: a capability is only marked as
implemented when concrete, verifiable evidence is provided (inputs, outputs,
and either a process description or an observable proof). Otherwise it is
categorized as unverified/fictional and the missing evidence is reported.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

EVIDENCE_REQUIREMENTS: dict[str, str] = {
    "inputs": "Provide concrete inputs or interface details",
    "outputs": "Provide concrete outputs or artifacts",
    "process": "Describe a reproducible process or steps",
    "observable": "Attach observable proof (logs, artifacts, command traces)",
}


@dataclass(frozen=True)
class CapabilityEvidence:
    """Structured evidence for a claimed capability."""

    inputs: list[str] | None = None
    outputs: list[str] | None = None
    process: str | None = None
    observable: str | None = None

    def provided_fields(self) -> set[str]:
        """Return the set of evidence fields that are present."""
        provided: set[str] = set()
        if self.inputs:
            provided.add("inputs")
        if self.outputs:
            provided.add("outputs")
        if self.process:
            provided.add("process")
        if self.observable:
            provided.add("observable")
        return provided

    def missing_fields(self) -> list[str]:
        """Return which evidence fields are still missing."""
        provided = self.provided_fields()
        return [field for field in EVIDENCE_REQUIREMENTS if field not in provided]

    def is_sufficient(self) -> bool:
        """Evidence is sufficient when inputs, outputs, and process/proof exist."""
        provided = self.provided_fields()
        has_io = "inputs" in provided and "outputs" in provided
        has_verification = "process" in provided or "observable" in provided
        return bool(has_io and has_verification)

    def to_summary(self) -> dict[str, Any]:
        """Compact dict representation without empty fields."""
        summary: dict[str, Any] = {}
        if self.inputs:
            summary["inputs"] = self.inputs
        if self.outputs:
            summary["outputs"] = self.outputs
        if self.process:
            summary["process"] = self.process
        if self.observable:
            summary["observable"] = self.observable
        return summary


@dataclass(frozen=True)
class CapabilityClaim:
    """Claimed capability with optional evidence."""

    name: str
    description: str = ""
    evidence: CapabilityEvidence | None = None


@dataclass(frozen=True)
class CapabilityAssessment:
    """Assessment result grouped by evidence-backed vs unverified claims."""

    implemented: list[dict[str, Any]]
    unverified: list[dict[str, Any]]
    missing_information: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Dictionary representation for serialization."""
        return {
            "implemented": self.implemented,
            "unverified": self.unverified,
            "missing_information": self.missing_information,
        }


def evaluate_capabilities(claims: Iterable[CapabilityClaim]) -> CapabilityAssessment:
    """Classify capabilities into implemented vs unverified/fictional buckets.

    A claim is only considered implemented when:
      * inputs AND outputs are provided, and
      * either a process description or an observable proof is present.

    Anything lacking that minimum evidence is treated as unverified/fictional
    with explicit evidence gaps reported.
    """
    implemented: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    missing_info: set[str] = set()

    for claim in claims:
        evidence = claim.evidence or CapabilityEvidence()
        missing_fields = evidence.missing_fields()
        provided = evidence.provided_fields()

        if evidence.is_sufficient():
            implemented.append(
                {
                    "name": claim.name,
                    "description": claim.description,
                    "reason": "Inputs/outputs plus a verifiable process are documented",
                    "evidence": evidence.to_summary(),
                    "evidence_needed": [],
                }
            )
        else:
            needed = [EVIDENCE_REQUIREMENTS[field] for field in missing_fields]
            missing_info.update(needed)
            if not provided:
                reason = (
                    "Unverified: no verifiable inputs, outputs, process, or proof were provided"
                )
            else:
                missing_list = ", ".join(sorted(missing_fields))
                reason = f"Unverified: missing evidence fields {missing_list}"

            unverified.append(
                {
                    "name": claim.name,
                    "description": claim.description,
                    "reason": reason,
                    "evidence": evidence.to_summary(),
                    "evidence_needed": needed,
                }
            )

    return CapabilityAssessment(
        implemented=implemented,
        unverified=unverified,
        missing_information=sorted(missing_info),
    )
