from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .graph import GraphError, topological_sort


class PipelineDAG:
    """DAG for pipeline step ordering.

    Delegates cycle detection and topological sorting to the shared
    ``graph.topological_sort`` implementation so that behaviour stays
    consistent across the codebase.
    """

    def __init__(self, nodes: list[str], edges: list[tuple[str, str]]):
        self.nodes = nodes
        self.edges = edges

    def has_cycle(self) -> bool:
        try:
            topological_sort(self.nodes, self.edges)
            return False
        except GraphError:
            return True

    def topological_order(self) -> list[str] | None:
        try:
            return topological_sort(self.nodes, self.edges)
        except GraphError:
            return None

    def execute(self, steps: dict[str, Callable[[dict[str, Any]], Any]]) -> dict[str, Any]:
        order = self.topological_order()
        if order is None:
            raise ValueError("dag_cycle")
        ctx: dict[str, Any] = {}
        for step in order:
            if step not in steps:
                raise KeyError(f"missing step: {step}")
            ctx[step] = steps[step](ctx)
        return ctx


class FileSecurityScanner:
    """Scan files on disk for forbidden patterns.

    Renamed from ``SecurityScanner`` to avoid confusion with
    ``security.SecurityScanner`` which operates on (path, content) pairs
    and returns structured report dicts.
    """

    def __init__(self, forbidden_patterns: Iterable[str] | None = None):
        pats = list(forbidden_patterns or [])
        pats.extend(
            [
                r"(?i)aws_access_key_id",
                r"(?i)aws_secret_access_key",
                r"(?i)-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----",
                r"(?i)password\s*=",
            ]
        )
        self.patterns = [re.compile(p) for p in pats]

    def scan(self, path: Path, content: str | None = None) -> dict[str, Any]:
        """Scan the given path/content for forbidden patterns.

        Returns a report dictionary with ``ok``, ``path``, and ``issues`` keys.
        """
        issues: list[str] = []

        if re.search(r"\.(env|secret)$", path.name):
            return {"path": str(path), "ok": False, "issues": ["skipped_disallowed_extension"]}

        if content is None:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return {"path": str(path), "ok": False, "issues": ["read_error"]}

        for pat in self.patterns:
            if pat.search(content):
                issues.append(f"matched_pattern:{pat.pattern}")

        return {
            "path": str(path),
            "ok": not issues,
            "issues": issues,
        }

    def scan_file(self, path: Path) -> bool:
        """Backwards-compatible wrapper that returns a simple boolean.

        ``True`` indicates the file passed all checks; ``False`` indicates a
        problem (skipped, read error, or forbidden pattern match).
        """
        report = self.scan(path)
        return bool(report.get("ok"))


# Backward-compatible alias so existing imports keep working.
SecurityScanner = FileSecurityScanner


class CIManager:
    def __init__(self, root: Path):
        self.root = root

    def apply_template(self, template_name: str) -> Path:
        ci_dir = self.root / ".indestructibleautoops" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        p = ci_dir / f"{template_name}.yaml"
        contents = (
            "# Generated minimal CI template\n"
            "name: generated\n"
            "on: [push]\n"
            "jobs:\n"
            "  noop:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo 'noop'\n"
        )
        p.write_text(contents, encoding="utf-8")
        return p

    def update_dependencies(self) -> Path | None:
        if os.getenv("ALLOW_UPDATES") != "true":
            return None
        deps_dir = self.root / ".indestructibleautoops" / "deps"
        deps_dir.mkdir(parents=True, exist_ok=True)
        p = deps_dir / "updated.log"
        p.write_text(f"Dependencies updated at {datetime.now().isoformat()}\n", encoding="utf-8")
        return p


@dataclass
class GovernanceSystem:
    require_strategy: bool = True

    def request_approval(self, strategy: str) -> dict[str, Any]:
        approved = bool(strategy or not self.require_strategy)
        return {
            "status": "approved" if approved else "rejected",
            "strategy": strategy,
            "ts": datetime.now().isoformat(),
        }

    def continuous_monitoring(self) -> dict[str, Any]:
        return {"status": "ok", "ts": datetime.now().isoformat()}


class AgentOrchestrator:
    def __init__(
        self,
        dag: PipelineDAG,
        scanner: FileSecurityScanner,
        governance: GovernanceSystem,
    ):
        self.dag = dag
        self.scanner = scanner
        self.governance = governance

    def validate_strategy(self, strategy: str) -> bool:
        if not strategy:
            return False
        return re.match(r"^[a-zA-Z0-9 _-]+$", strategy) is not None

    def execute(
        self,
        agents: dict[str, Callable[[dict[str, Any]], Any]],
        files_to_scan: Iterable[Path] | None = None,
        strategy: str = "",
    ) -> dict[str, Any]:
        if not self.validate_strategy(strategy):
            return {"ok": False, "error": "invalid_strategy"}
        approval = self.governance.request_approval(strategy)
        if approval["status"] != "approved":
            return {"ok": False, "error": "approval_denied", "approval": approval}

        for f in files_to_scan or []:
            if not self.scanner.scan_file(f):
                return {"ok": False, "error": "security_blocked", "file": str(f)}

        order = self.dag.topological_order()
        if order is None:
            return {"ok": False, "error": "dag_cycle"}

        ctx: dict[str, Any] = {}
        for step in order:
            fn = agents.get(step)
            if not fn:
                return {"ok": False, "error": f"missing_agent:{step}"}
            ctx[step] = fn(ctx)

        monitoring = self.governance.continuous_monitoring()
        return {
            "ok": True,
            "order": order,
            "results": ctx,
            "approval": approval,
            "monitor": monitoring,
        }
