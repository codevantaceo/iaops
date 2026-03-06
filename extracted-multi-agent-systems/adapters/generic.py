from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..orchestration import FileSecurityScanner


@dataclass(frozen=True)
class AdapterContext:
    project_root: Path
    state_dir: Path


def load_adapters_config(p: Path) -> dict[str, Any]:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def detect_adapter(project_root: Path, adapters_cfg: dict[str, Any]) -> str:
    detectors = adapters_cfg["spec"]["detectors"]
    for d in detectors:
        for f in d.get("matchAnyFiles", []):
            if (project_root / f).exists():
                return d["id"]
    return "generic"


class GenericAdapter:
    name = "generic"

    def __init__(self, ctx: AdapterContext):
        self.ctx = ctx

    def index(self) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        for p in self.ctx.project_root.rglob("*"):
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(self.ctx.project_root)
            except ValueError:
                rel = p
            files.append({"path": str(rel), "size": p.stat().st_size})
        return {"root": str(self.ctx.project_root), "files": files}

    def snapshot(self) -> dict[str, Any]:
        return {"root": str(self.ctx.project_root), "ts": "local"}

    def security_scan(self) -> dict[str, Any]:
        scanner = FileSecurityScanner()
        findings: list[dict[str, Any]] = []
        blocked = False

        for p in self.ctx.project_root.rglob("*"):
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(self.ctx.project_root)
            except ValueError:
                rel = p

            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                report = scanner.scan(p, content)

                if not report["ok"]:
                    blocked = True
                    findings.append(
                        {
                            "path": str(rel),
                            "issues": report["issues"],
                        }
                    )
            except OSError:
                continue

        return {
            "blocked": blocked,
            "checks": findings,
        }

    def repair_plan(self, index: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def required_files(self) -> list[str]:
        return ["README.md"]
