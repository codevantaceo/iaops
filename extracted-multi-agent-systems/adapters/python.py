from __future__ import annotations

from typing import Any

from .generic import AdapterContext, GenericAdapter


class PythonAdapter(GenericAdapter):
    name = "python"

    def __init__(self, ctx: AdapterContext):
        super().__init__(ctx)

    def repair_plan(self, index: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if not (self.ctx.project_root / "src").exists():
            actions.append({"id": "add_src_dir", "kind": "mkdir", "path": "src"})
        return actions

    def required_files(self) -> list[str]:
        return ["pyproject.toml", "src"]
