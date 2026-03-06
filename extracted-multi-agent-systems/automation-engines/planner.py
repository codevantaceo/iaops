from __future__ import annotations

from pathlib import Path
from typing import Any


class Planner:
    def __init__(self, project_root: Path, adapter):
        self.root = project_root
        self.adapter = adapter

    def build_plan(self) -> dict[str, Any]:
        index = self.adapter.index()
        actions: list[dict[str, Any]] = []
        if not (self.root / ".github/workflows/ci.yml").exists():
            actions.append(
                {
                    "id": "add_ci",
                    "kind": "write_file_if_missing",
                    "path": ".github/workflows/ci.yml",
                    "templateRef": "internal:ci.yml",
                }
            )
        if not (self.root / "pyproject.toml").exists() and self.adapter.name == "python":
            actions.append(
                {
                    "id": "add_pyproject",
                    "kind": "write_file_if_missing",
                    "path": "pyproject.toml",
                    "templateRef": "internal:pyproject.toml",
                }
            )
        actions.extend(self.adapter.repair_plan(index))
        return {"ok": True, "adapter": self.adapter.name, "actions": actions}
