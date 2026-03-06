"""
Whitelist / Exemption System for Validation.

Provides a mechanism to suppress known false-positive validation issues
with full audit trail, expiry dates, and approval tracking.

Design principles:
  - Every exemption requires a documented reason and approver.
  - Exemptions can expire automatically (time-boxed tolerance).
  - All exemption matches are logged for audit.
  - Pending-review state allows human-in-the-loop gating.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ExemptionStatus(Enum):
    """Status of a whitelist exemption."""

    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING_REVIEW = "pending_review"
    REVOKED = "revoked"


@dataclass
class WhitelistRule:
    """A single whitelist / exemption rule.

    Attributes:
        rule_id: Unique identifier for this rule.
        pattern: Regex pattern matched against issue_id.
        reason: Human-readable justification for the exemption.
        approved_by: Name or ID of the person who approved.
        created_at: Unix timestamp of creation.
        expires_at: Optional Unix timestamp after which the rule is void.
        category: Optional category filter (e.g. "regression", "performance").
        file_pattern: Optional regex matched against file_path of the issue.
        max_severity: Maximum severity this rule may suppress.
                      Issues above this severity are never suppressed.
        status: Current lifecycle status of the rule.
        audit_log: Append-only log of match events.
    """

    rule_id: str
    pattern: str
    reason: str
    approved_by: str
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    category: str | None = None
    file_pattern: str | None = None
    max_severity: str = "error"  # info | warning | error | critical (never blocker)
    status: ExemptionStatus = ExemptionStatus.ACTIVE
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    # ── helpers ──────────────────────────────────────────────────────

    def is_active(self) -> bool:
        """Return True when the rule can still suppress issues."""
        if self.status != ExemptionStatus.ACTIVE:
            return False
        if self.expires_at is not None and time.time() > self.expires_at:
            self.status = ExemptionStatus.EXPIRED
            return False
        return True

    def matches_issue(
        self, issue_id: str, category: str | None = None, file_path: str | None = None
    ) -> bool:
        """Check whether this rule matches a given issue."""
        if not self.is_active():
            return False

        # Pattern match on issue_id
        if not re.search(self.pattern, issue_id):
            return False

        # Optional category filter
        if self.category and category and self.category != category:
            return False

        # Optional file-path filter
        if self.file_pattern and file_path:
            if not re.search(self.file_pattern, file_path):
                return False

        return True

    def record_match(self, issue_id: str, timestamp: float | None = None) -> None:
        """Append an audit entry for a suppressed issue."""
        self.audit_log.append(
            {
                "issue_id": issue_id,
                "matched_at": timestamp or time.time(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "reason": self.reason,
            "approved_by": self.approved_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "category": self.category,
            "file_pattern": self.file_pattern,
            "max_severity": self.max_severity,
            "status": self.status.value,
            "audit_log": self.audit_log,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WhitelistRule:
        """Deserialise from a plain dict."""
        return cls(
            rule_id=data["rule_id"],
            pattern=data["pattern"],
            reason=data["reason"],
            approved_by=data["approved_by"],
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            category=data.get("category"),
            file_pattern=data.get("file_pattern"),
            max_severity=data.get("max_severity", "error"),
            status=ExemptionStatus(data.get("status", "active")),
            audit_log=data.get("audit_log", []),
        )


# ── severity ordering (for max_severity gate) ───────────────────────

_SEVERITY_ORDER = {
    "info": 0,
    "warning": 1,
    "error": 2,
    "critical": 3,
    "blocker": 4,
}


def _severity_rank(name: str) -> int:
    return _SEVERITY_ORDER.get(name.lower(), 99)


# ── WhitelistManager ────────────────────────────────────────────────


class WhitelistManager:
    """Manages a collection of whitelist rules with persistence.

    Typical lifecycle:
        1. Load rules from YAML/JSON config.
        2. For each validation issue, call ``should_suppress(issue)``.
        3. Suppressed issues are downgraded (not silently dropped).
        4. Save updated rules (with audit logs) after the run.
    """

    def __init__(self, rules: list[WhitelistRule] | None = None) -> None:
        self._rules: list[WhitelistRule] = rules or []
        self._suppressed_count: int = 0
        self._match_history: list[dict[str, Any]] = []

    # ── rule management ──────────────────────────────────────────────

    def add_rule(self, rule: WhitelistRule) -> None:
        """Register a new exemption rule."""
        # Prevent duplicates
        if any(r.rule_id == rule.rule_id for r in self._rules):
            raise ValueError(f"Duplicate rule_id: {rule.rule_id}")
        self._rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Revoke a rule by ID. Returns True if found."""
        for rule in self._rules:
            if rule.rule_id == rule_id:
                rule.status = ExemptionStatus.REVOKED
                return True
        return False

    def get_rule(self, rule_id: str) -> WhitelistRule | None:
        """Look up a rule by ID."""
        for rule in self._rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_active_rules(self) -> list[WhitelistRule]:
        """Return only currently active rules."""
        return [r for r in self._rules if r.is_active()]

    def get_expired_rules(self) -> list[WhitelistRule]:
        """Return rules that have expired (for audit)."""
        # Trigger expiry check
        for r in self._rules:
            r.is_active()
        return [r for r in self._rules if r.status == ExemptionStatus.EXPIRED]

    def get_pending_rules(self) -> list[WhitelistRule]:
        """Return rules awaiting human review."""
        return [r for r in self._rules if r.status == ExemptionStatus.PENDING_REVIEW]

    # ── suppression logic ────────────────────────────────────────────

    def should_suppress(
        self,
        issue_id: str,
        severity: str,
        category: str | None = None,
        file_path: str | None = None,
    ) -> tuple[bool, WhitelistRule | None]:
        """Decide whether an issue should be suppressed.

        Returns (suppressed, matching_rule).
        BLOCKER severity is *never* suppressed regardless of rules.
        """
        # Hard constraint: BLOCKER issues are never whitelisted
        if _severity_rank(severity) >= _SEVERITY_ORDER["blocker"]:
            return False, None

        for rule in self._rules:
            if not rule.matches_issue(issue_id, category, file_path):
                continue

            # Severity gate: rule only covers up to max_severity
            if _severity_rank(severity) > _severity_rank(rule.max_severity):
                continue

            # Match found — record audit trail
            rule.record_match(issue_id)
            self._suppressed_count += 1
            self._match_history.append(
                {
                    "issue_id": issue_id,
                    "severity": severity,
                    "rule_id": rule.rule_id,
                    "timestamp": time.time(),
                }
            )
            return True, rule

        return False, None

    def apply_whitelist(
        self,
        issues: list[Any],
    ) -> tuple[list[Any], int]:
        """Apply whitelist rules to a list of ValidationIssues.

        Suppressed issues are downgraded to INFO severity and annotated
        with the matching rule ID.  BLOCKER issues are never suppressed.

        Returns:
            ``(processed_issues, suppressed_count)``
        """
        from .validator import Severity

        processed: list[Any] = []
        suppressed_count = 0

        for issue in issues:
            # BLOCKER issues are never suppressed
            if issue.severity.value == Severity.BLOCKER.value:
                processed.append(issue)
                continue

            matched = False
            for rule in self._rules:
                if not rule.is_active():
                    continue

                if not rule.matches_issue(
                    issue.issue_id,
                    category=issue.category,
                    file_path=getattr(issue, "file_path", None),
                ):
                    continue

                # Severity gate
                if _severity_rank(issue.severity.value) > _severity_rank(rule.max_severity):
                    continue

                # Match — record audit and downgrade
                rule.record_match(issue.issue_id)
                self._suppressed_count += 1
                self._match_history.append(
                    {
                        "issue_id": issue.issue_id,
                        "severity": issue.severity.value,
                        "rule_id": rule.rule_id,
                        "timestamp": time.time(),
                    }
                )

                issue.severity = Severity.INFO
                issue.description = f"[SUPPRESSED by rule '{rule.rule_id}'] {issue.description}"
                if hasattr(issue, "metrics"):
                    issue.metrics["suppressed"] = True
                    issue.metrics["suppressed_by_rule"] = rule.rule_id
                    issue.metrics["suppression_reason"] = rule.reason

                processed.append(issue)
                suppressed_count += 1
                matched = True
                break

            if not matched:
                processed.append(issue)

        return processed, suppressed_count

    # ── persistence ──────────────────────────────────────────────────

    def save(self, path: Path | str) -> None:
        """Persist rules + audit logs to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "rules": [r.to_dict() for r in self._rules],
            "stats": {
                "total_rules": len(self._rules),
                "active_rules": len(self.get_active_rules()),
                "expired_rules": len(self.get_expired_rules()),
                "pending_rules": len(self.get_pending_rules()),
                "total_suppressions": self._suppressed_count,
            },
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path | str) -> WhitelistManager:
        """Load rules from a JSON file."""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = json.load(f)
        rules = [WhitelistRule.from_dict(r) for r in data.get("rules", [])]
        return cls(rules=rules)

    @classmethod
    def load_yaml(cls, path: Path | str) -> WhitelistManager:
        """Load rules from a YAML file (requires PyYAML)."""
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required for YAML whitelist configs: pip install pyyaml"
            ) from exc
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        rules = [WhitelistRule.from_dict(r) for r in data.get("rules", [])]
        return cls(rules=rules)

    # ── reporting ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "total_rules": len(self._rules),
            "active_rules": len(self.get_active_rules()),
            "expired_rules": len(self.get_expired_rules()),
            "pending_rules": len(self.get_pending_rules()),
            "total_suppressions": self._suppressed_count,
            "match_history": self._match_history,
        }

    def get_audit_report(self) -> str:
        """Generate a human-readable audit report."""
        lines = [
            "=" * 72,
            "WHITELIST AUDIT REPORT",
            "=" * 72,
            f"Total rules: {len(self._rules)}",
            f"Active: {len(self.get_active_rules())}",
            f"Expired: {len(self.get_expired_rules())}",
            f"Pending review: {len(self.get_pending_rules())}",
            f"Total suppressions this run: {self._suppressed_count}",
            "",
        ]

        if self._match_history:
            lines.append("Suppression History:")
            lines.append("-" * 72)
            for entry in self._match_history:
                lines.append(
                    f"  [{entry['severity'].upper()}] {entry['issue_id']} "
                    f"→ suppressed by rule '{entry['rule_id']}'"
                )
            lines.append("")

        expired = self.get_expired_rules()
        if expired:
            lines.append("⚠️  Expired Rules (should be reviewed):")
            lines.append("-" * 72)
            for rule in expired:
                lines.append(f"  {rule.rule_id}: {rule.reason}")
            lines.append("")

        pending = self.get_pending_rules()
        if pending:
            lines.append("🔍 Pending Review:")
            lines.append("-" * 72)
            for rule in pending:
                lines.append(f"  {rule.rule_id}: {rule.reason}")
            lines.append("")

        return "\n".join(lines)
