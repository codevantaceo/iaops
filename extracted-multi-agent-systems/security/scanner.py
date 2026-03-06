from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class NarrativeSecretScanner:
    narrative_patterns: list[str]
    forbid_question_patterns: list[str]
    secret_patterns: list[str] | None

    def scan_index(self, index: dict[str, Any]) -> dict[str, Any]:
        files = index.get("files", [])
        narrative_hits: list[dict[str, Any]] = []
        question_hits: list[dict[str, Any]] = []
        for f in files:
            path = f.get("path", "")
            for pat in self.narrative_patterns:
                if re.search(pat, path):
                    narrative_hits.append({"path": path, "pattern": pat})
            for pat in self.forbid_question_patterns:
                if re.search(pat, path):
                    question_hits.append({"path": path, "pattern": pat})

        blocked = bool(narrative_hits or question_hits)
        reason = (
            "narrative_detected" if narrative_hits else "question_detected" if question_hits else ""
        )
        return {
            "blocked": blocked,
            "reason": reason,
            "narrativeHits": narrative_hits,
            "questionHits": question_hits,
        }
