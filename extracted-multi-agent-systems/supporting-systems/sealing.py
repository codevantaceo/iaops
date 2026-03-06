from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import Hasher
from .io import ensure_dir, write_text


class Sealer:
    def __init__(self, project_root: Path, state_dir: Path, evidence_dir: Path, hasher: Hasher):
        self.root = project_root
        self.state_dir = state_dir
        self.evidence_dir = evidence_dir
        self.hasher = hasher

    def seal(self) -> dict[str, Any]:
        seal_dir = self.state_dir / "seal"
        ensure_dir(seal_dir)
        tree = self.hasher.hash_tree(self.root, exclude_dirs={self.state_dir.name, ".git"})
        manifest_path = seal_dir / "manifest.json"
        write_text(manifest_path, json.dumps(tree, indent=2, sort_keys=True))
        evidence_link = self.evidence_dir / "seal.manifest.json"
        write_text(
            evidence_link,
            json.dumps({"manifest": str(manifest_path)}, indent=2, sort_keys=True),
        )
        return {"ok": True, "manifest": str(manifest_path), "evidence": str(evidence_link)}
