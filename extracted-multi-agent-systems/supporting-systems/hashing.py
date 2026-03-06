from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blake3 import blake3


@dataclass
class Hasher:
    algorithms: list[str]

    def hash_bytes(self, data: bytes) -> dict[str, str]:
        out: dict[str, str] = {}
        for a in self.algorithms:
            if a == "sha3_512":
                out[a] = hashlib.sha3_512(data).hexdigest()
            elif a == "blake3":
                out[a] = blake3(data).hexdigest()
            else:
                raise ValueError("unsupported_hash")
        return out

    def hash_file(self, p: Path) -> dict[str, Any]:
        data = p.read_bytes()
        return {"path": str(p), "size": len(data), "hash": self.hash_bytes(data)}

    def hash_tree(self, root: Path, exclude_dirs: set[str] | None = None) -> dict[str, Any]:
        ex = exclude_dirs or set()
        files: list[dict[str, Any]] = []
        for p in sorted(root.rglob("*")):
            if p.is_dir():
                continue
            if any(part in ex for part in p.parts):
                continue
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            data = p.read_bytes()
            files.append({"path": str(rel), "size": len(data), "hash": self.hash_bytes(data)})
        return {"root": str(root), "algorithms": list(self.algorithms), "files": files}
