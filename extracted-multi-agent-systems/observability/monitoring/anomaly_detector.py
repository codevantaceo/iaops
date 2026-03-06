from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SEVERITY_ORDER = ["debug", "info", "notice", "warning", "error", "critical", "emergency"]


@dataclass
class Anomaly:
    rule: str
    priority: str
    output: str


class AnomalyDetector:
    def __init__(self, min_priority: str = "critical") -> None:
        self.min_priority = min_priority.lower()

    def _priority_index(self, priority: str) -> int:
        try:
            return SEVERITY_ORDER.index(priority.lower())
        except ValueError:
            return -1

    def is_anomalous(self, event: dict) -> bool:
        priority = event.get("priority", "").lower()
        return self._priority_index(priority) >= self._priority_index(self.min_priority)

    def scan_events(self, events: Iterable[dict]) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        for event in events:
            if self.is_anomalous(event):
                anomalies.append(
                    Anomaly(
                        rule=event.get("rule", "unknown"),
                        priority=event.get("priority", "unknown"),
                        output=event.get("output", ""),
                    )
                )
        return anomalies

    def scan_file(self, path: str) -> list[Anomaly]:
        events: list[dict] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return self.scan_events(events)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect anomalies from Falco or monitoring event feeds.")
    parser.add_argument("--events-file", required=True, help="Path to JSONL event file.")
    parser.add_argument("--min-priority", default="critical", help="Minimum priority to treat as anomaly.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detector = AnomalyDetector(min_priority=args.min_priority)
    anomalies = detector.scan_file(args.events_file)
    if anomalies:
        raise SystemExit(f"Detected {len(anomalies)} anomalies at priority >= {args.min_priority}")


if __name__ == "__main__":
    main()
