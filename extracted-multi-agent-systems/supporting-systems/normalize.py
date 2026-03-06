from __future__ import annotations

from pathlib import Path


class Normalizer:
    def __init__(self, project_root: Path):
        self.root = project_root

    def run(self) -> dict:
        created: list[str] = []
        for d in [".github/workflows", "configs", "schemas", "src", "tests"]:
            p = self.root / d
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(d)
        return {"ok": True, "createdDirs": created}
