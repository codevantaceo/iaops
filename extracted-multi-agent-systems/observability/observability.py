from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .io import ensure_dir, write_text
from .verifier import load_jsonschema


class EventStream:
    def __init__(self, path: Path, schema_path: Path):
        self.path = path
        self.schema = load_jsonschema(schema_path)
        ensure_dir(self.path.parent)
        if not self.path.exists():
            write_text(self.path, "")

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    def emit(self, trace_id: str, step_id: str, typ: str, payload: dict[str, Any]) -> None:
        ev = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "traceId": trace_id,
            "stepId": step_id,
            "type": typ,
            "payload": payload,
        }
        self.schema.validate(ev)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
