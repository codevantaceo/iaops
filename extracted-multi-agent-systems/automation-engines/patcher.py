from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import ensure_dir, write_text


class Patcher:
    def __init__(self, project_root: Path, allow_writes: bool):
        self.root = project_root.resolve()
        self.allow_writes = allow_writes

    def _safe_resolve(self, rel: str) -> Path | None:
        """Resolve *rel* under project root; return None if it escapes."""
        if Path(rel).is_absolute():
            return None
        resolved = (self.root / rel).resolve()
        # Ensure the resolved path is within project root
        try:
            resolved.relative_to(self.root)
        except ValueError:
            return None
        return resolved

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        actions = plan.get("actions", [])
        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for a in actions:
            kind = a.get("kind")
            if kind == "mkdir":
                rel = a["path"]
                p = self._safe_resolve(rel)
                if p is None:
                    skipped.append({"action": a, "reason": "path_traversal_blocked"})
                    continue
                if p.exists():
                    skipped.append({"action": a, "reason": "exists"})
                    continue
                if not self.allow_writes:
                    skipped.append({"action": a, "reason": "writes_disabled"})
                    continue
                ensure_dir(p)
                applied.append({"action": a})
                continue
            if kind == "write_file_if_missing":
                rel = a["path"]
                p = self._safe_resolve(rel)
                if p is None:
                    skipped.append({"action": a, "reason": "path_traversal_blocked"})
                    continue
                if p.exists():
                    skipped.append({"action": a, "reason": "exists"})
                    continue
                if not self.allow_writes:
                    skipped.append({"action": a, "reason": "writes_disabled"})
                    continue
                ensure_dir(p.parent)
                write_text(p, f"# generated placeholder: {rel}\n")
                applied.append({"action": a})
                continue
            skipped.append({"action": a, "reason": "unsupported"})
        return {
            "ok": True,
            "allowWrites": self.allow_writes,
            "applied": applied,
            "skipped": skipped,
        }
