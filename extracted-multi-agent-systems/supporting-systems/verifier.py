from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema


@dataclass
class SchemaWrapper:
    schema: dict[str, Any]

    def validate(self, data: Any) -> None:
        jsonschema.Draft202012Validator(self.schema).validate(data)


def load_jsonschema(p: Path | str) -> SchemaWrapper:
    p = Path(p)
    return SchemaWrapper(schema=json.loads(p.read_text(encoding="utf-8")))


class Verifier:
    def __init__(self, project_root: Path, adapter):
        self.root = project_root
        self.adapter = adapter

    def run(self) -> dict[str, Any]:
        required = self.adapter.required_files()
        missing = [r for r in required if not (self.root / r).exists()]
        ok = len(missing) == 0
        return {"ok": ok, "adapter": self.adapter.name, "missing": missing, "required": required}
