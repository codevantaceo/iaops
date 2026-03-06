"""
Observability Agent for Events, Metrics, and Reports.

This agent handles event stream processing, metrics collection, and report generation.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..base import Agent, AgentCapability


@dataclass
class Metric:
    """A metric data point."""

    metric_id: str
    name: str
    value: float
    unit: str
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """An alert generated from metrics or events."""

    alert_id: str
    severity: str
    title: str
    description: str
    metric_name: str | None = None
    threshold: float | None = None
    current_value: float | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    """A generated report."""

    report_id: str
    report_type: str
    title: str
    content: str
    generated_at: float
    format: str = "markdown"
    metadata: dict[str, Any] = field(default_factory=dict)


class ObservabilityAgent(Agent):
    """Agent for observability operations (events, metrics, reports)."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="process_events",
                description="Process event stream and extract insights",
                input_types=["event_stream"],
                output_types=["metrics", "alerts"],
            ),
            AgentCapability(
                name="collect_metrics",
                description="Collect and aggregate metrics",
                input_types=["metric_data"],
                output_types=["aggregated_metrics"],
            ),
            AgentCapability(
                name="generate_report",
                description="Generate reports from data",
                input_types=["report_type", "data"],
                output_types=["report"],
            ),
            AgentCapability(
                name="check_alerts",
                description="Check metrics against alert thresholds",
                input_types=["metrics"],
                output_types=["alerts"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._metrics: list[Metric] = []
        self._alerts: list[Alert] = []
        self._reports: list[Report] = []
        self._event_buffer: list[dict[str, Any]] = []

        self._alert_rules: dict[str, dict[str, Any]] = {}
        self._metric_aggregates: dict[str, dict[str, Any]] = {}

        self._lock = threading.RLock()

        # Load default alert rules
        self._load_default_alert_rules()

    async def initialize(self) -> None:
        """Initialize the observability agent."""
        # Start metrics aggregation timer if configured
        if self.config.get("aggregate_metrics", True):
            self._start_aggregation_timer()

    async def shutdown(self) -> None:
        """Shutdown the observability agent."""
        # Save metrics and reports if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            await self._save_observability_state(state_dir)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "process_events":
                return await self._task_process_events(payload, context)
            elif task_type == "collect_metrics":
                return await self._task_collect_metrics(payload, context)
            elif task_type == "generate_report":
                return await self._task_generate_report(payload, context)
            elif task_type == "check_alerts":
                return await self._task_check_alerts(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_process_events(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Process event stream and extract insights."""
        event_stream = payload.get("event_stream", [])

        if not event_stream:
            return {
                "success": True,
                "events_processed": 0,
                "metrics": [],
                "alerts": [],
            }

        metrics_generated = []
        alerts_generated = []

        for event in event_stream:
            # Add to event buffer
            with self._lock:
                self._event_buffer.append(event)

            # Extract metrics from event
            event_metrics = await self._extract_metrics_from_event(event)
            metrics_generated.extend(event_metrics)

            # Check for alerts
            event_alerts = await self._check_event_alerts(event)
            alerts_generated.extend(event_alerts)

        return {
            "success": True,
            "events_processed": len(event_stream),
            "metrics": [m.__dict__ for m in metrics_generated],
            "alerts": [a.__dict__ for a in alerts_generated],
        }

    async def _task_collect_metrics(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Collect and aggregate metrics."""
        metric_data = payload.get("metric_data", [])

        collected_metrics = []

        for data in metric_data:
            metric = Metric(
                metric_id=f"metric_{int(time.time() * 1000)}_{len(collected_metrics)}",
                name=data.get("name", "unknown"),
                value=float(data.get("value", 0)),
                unit=data.get("unit", "count"),
                timestamp=data.get("timestamp", time.time()),
                tags=data.get("tags", {}),
                metadata=data.get("metadata", {}),
            )
            collected_metrics.append(metric)

            with self._lock:
                self._metrics.append(metric)

        # Aggregate metrics
        aggregated = await self._aggregate_metrics(collected_metrics)

        return {
            "success": True,
            "metrics_collected": len(collected_metrics),
            "aggregated_metrics": aggregated,
        }

    async def _task_generate_report(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Generate reports from data."""
        report_type = payload.get("report_type")
        data = payload.get("data", {})

        if not report_type:
            raise ValueError("report_type is required")

        if report_type == "summary":
            content = await self._generate_summary_report(data, context)
        elif report_type == "metrics":
            content = await self._generate_metrics_report(data, context)
        elif report_type == "alerts":
            content = await self._generate_alerts_report(data, context)
        elif report_type == "execution":
            content = await self._generate_execution_report(data, context)
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        report = Report(
            report_id=f"report_{int(time.time())}_{self.agent_id}",
            report_type=report_type,
            title=f"{report_type.capitalize()} Report",
            content=content,
            generated_at=time.time(),
            format="markdown",
        )

        with self._lock:
            self._reports.append(report)

        return {
            "success": True,
            "report": report.__dict__,
        }

    async def _task_check_alerts(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Check metrics against alert thresholds."""
        metrics = payload.get("metrics", [])

        alerts = []

        for metric in metrics:
            metric_alerts = await self._check_metric_alerts(metric)
            alerts.extend(metric_alerts)

        return {
            "success": True,
            "alerts": [a.__dict__ for a in alerts],
            "total_alerts": len(alerts),
        }

    async def _extract_metrics_from_event(
        self,
        event: dict[str, Any],
    ) -> list[Metric]:
        """Extract metrics from an event."""
        metrics = []

        # Common metrics to extract
        event_type = event.get("event_type", "unknown")

        # Count events by type
        metrics.append(
            Metric(
                metric_id=f"event_count_{event_type}_{int(time.time())}",
                name="event_count",
                value=1.0,
                unit="count",
                timestamp=event.get("timestamp", time.time()),
                tags={
                    "event_type": event_type,
                    "agent_id": event.get("agent_id", ""),
                },
            )
        )

        # Extract duration if available
        duration = event.get("duration")
        if duration is not None:
            metrics.append(
                Metric(
                    metric_id=f"event_duration_{event_type}_{int(time.time())}",
                    name="event_duration",
                    value=float(duration),
                    unit="seconds",
                    timestamp=event.get("timestamp", time.time()),
                    tags={
                        "event_type": event_type,
                        "agent_id": event.get("agent_id", ""),
                    },
                )
            )

        return metrics

    async def _check_event_alerts(
        self,
        event: dict[str, Any],
    ) -> list[Alert]:
        """Check event for alert conditions."""
        alerts = []

        # Check for error events
        if event.get("status") == "error":
            alerts.append(
                Alert(
                    alert_id=f"alert_error_{int(time.time())}",
                    severity="high",
                    title=f"Error in {event.get('event_type', 'unknown')}",
                    description=event.get("error_message", "Unknown error"),
                    timestamp=event.get("timestamp", time.time()),
                )
            )

        # Check for long-running events
        duration = event.get("duration")
        if duration and duration > 300:  # 5 minutes
            alerts.append(
                Alert(
                    alert_id=f"alert_long_duration_{int(time.time())}",
                    severity="warning",
                    title=f"Long running event: {event.get('event_type', 'unknown')}",
                    description=f"Event took {duration} seconds to complete",
                    current_value=duration,
                    threshold=300,
                    timestamp=event.get("timestamp", time.time()),
                )
            )

        return alerts

    async def _check_metric_alerts(
        self,
        metric: dict[str, Any],
    ) -> list[Alert]:
        """Check metric against alert rules."""
        alerts = []

        metric_name = metric.get("name")
        metric_value = metric.get("value", 0)

        for rule_name, rule in self._alert_rules.items():
            if rule.get("metric_name") == metric_name:
                condition = rule.get("condition")
                threshold = rule.get("threshold")
                severity = rule.get("severity", "warning")

                should_alert = False

                if condition == "gt" and metric_value > threshold:
                    should_alert = True
                elif condition == "lt" and metric_value < threshold:
                    should_alert = True
                elif condition == "eq" and metric_value == threshold:
                    should_alert = True
                elif condition == "ne" and metric_value != threshold:
                    should_alert = True

                if should_alert:
                    alerts.append(
                        Alert(
                            alert_id=f"alert_{rule_name}_{int(time.time())}",
                            severity=severity,
                            title=f"Alert: {rule_name}",
                            description=rule.get("description", ""),
                            metric_name=metric_name,
                            threshold=threshold,
                            current_value=metric_value,
                            timestamp=time.time(),
                        )
                    )

        return alerts

    async def _aggregate_metrics(
        self,
        metrics: list[Metric],
    ) -> dict[str, Any]:
        """Aggregate metrics by name."""
        aggregated = {}

        for metric in metrics:
            name = metric.name

            if name not in aggregated:
                aggregated[name] = {
                    "count": 0,
                    "sum": 0.0,
                    "min": float("inf"),
                    "max": float("-inf"),
                    "avg": 0.0,
                }

            aggregated[name]["count"] += 1
            aggregated[name]["sum"] += metric.value
            aggregated[name]["min"] = min(aggregated[name]["min"], metric.value)
            aggregated[name]["max"] = max(aggregated[name]["max"], metric.value)
            aggregated[name]["avg"] = aggregated[name]["sum"] / aggregated[name]["count"]

        return aggregated

    async def _generate_summary_report(
        self,
        data: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate a summary report."""
        with self._lock:
            total_metrics = len(self._metrics)
            total_alerts = len(self._alerts)
            total_reports = len(self._reports)

        report = f"""# Summary Report

Generated at: {datetime.fromtimestamp(time.time()).isoformat()}

## Overview

- Total Metrics: {total_metrics}
- Total Alerts: {total_alerts}
- Total Reports: {total_reports}

## Recent Activity

Recent events processed: {len(self._event_buffer)}

## System Status

All systems operational.
"""

        return report

    async def _generate_metrics_report(
        self,
        data: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate a metrics report."""
        with self._lock:
            recent_metrics = self._metrics[-100:]  # Last 100 metrics

        report = "# Metrics Report\n\n"
        report += f"Generated at: {datetime.fromtimestamp(time.time()).isoformat()}\n\n"

        # Aggregate recent metrics
        aggregated = await self._aggregate_metrics(recent_metrics)

        for name, stats in aggregated.items():
            report += f"## {name}\n"
            report += f"- Count: {stats['count']}\n"
            report += f"- Average: {stats['avg']:.2f}\n"
            report += f"- Min: {stats['min']:.2f}\n"
            report += f"- Max: {stats['max']:.2f}\n"
            report += f"- Sum: {stats['sum']:.2f}\n\n"

        return report

    async def _generate_alerts_report(
        self,
        data: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate an alerts report."""
        with self._lock:
            recent_alerts = self._alerts[-50:]  # Last 50 alerts

        report = "# Alerts Report\n\n"
        report += f"Generated at: {datetime.fromtimestamp(time.time()).isoformat()}\n\n"
        report += f"Total Alerts: {len(recent_alerts)}\n\n"

        # Group by severity
        by_severity = {}
        for alert in recent_alerts:
            severity = alert.severity
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(alert)

        for severity, alerts in sorted(by_severity.items()):
            report += f"## {severity.upper()} ({len(alerts)})\n\n"
            for alert in alerts:
                report += f"- **{alert.title}**\n"
                report += f"  - {alert.description}\n"
                report += f"  - Time: {datetime.fromtimestamp(alert.timestamp).isoformat()}\n\n"

        return report

    async def _generate_execution_report(
        self,
        data: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Generate an execution report."""
        report = "# Execution Report\n\n"
        report += f"Generated at: {datetime.fromtimestamp(time.time()).isoformat()}\n\n"

        # Extract execution data from context
        tasks_completed = context.get("tasks_completed", 0)
        tasks_failed = context.get("tasks_failed", 0)
        total_duration = context.get("total_duration", 0)

        report += "## Summary\n\n"
        report += f"- Tasks Completed: {tasks_completed}\n"
        report += f"- Tasks Failed: {tasks_failed}\n"
        report += f"- Total Duration: {total_duration:.2f}s\n\n"

        if tasks_failed > 0:
            report += "## ⚠️ Issues\n\n"
            report += f"{tasks_failed} tasks failed. Review logs for details.\n\n"
        else:
            report += "## ✅ Success\n\n"
            report += "All tasks completed successfully.\n\n"

        return report

    def _load_default_alert_rules(self) -> None:
        """Load default alert rules."""
        self._alert_rules["high_error_rate"] = {
            "metric_name": "error_count",
            "condition": "gt",
            "threshold": 10,
            "severity": "critical",
            "description": "High error rate detected",
        }

        self._alert_rules["long_execution_time"] = {
            "metric_name": "execution_duration",
            "condition": "gt",
            "threshold": 300,
            "severity": "warning",
            "description": "Long execution time detected",
        }

        self._alert_rules["low_success_rate"] = {
            "metric_name": "success_rate",
            "condition": "lt",
            "threshold": 0.95,
            "severity": "high",
            "description": "Low success rate detected",
        }

    def _start_aggregation_timer(self) -> None:
        """Start background aggregation timer."""
        # In production, would use a proper scheduler
        pass

    async def _save_observability_state(self, state_dir: str) -> None:
        """Save observability state."""
        pass

    def add_metric(self, metric: Metric) -> None:
        """Add a metric."""
        with self._lock:
            self._metrics.append(metric)

    def get_metrics(
        self,
        name: str | None = None,
        limit: int = 100,
    ) -> list[Metric]:
        """Get metrics with optional filters."""
        with self._lock:
            metrics = self._metrics

            if name:
                metrics = [m for m in metrics if m.name == name]

            return metrics[-limit:]

    def get_alerts(
        self,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Get alerts with optional filters."""
        with self._lock:
            alerts = self._alerts

            if severity:
                alerts = [a for a in alerts if a.severity == severity]

            return alerts[-limit:]

    def add_alert_rule(
        self,
        rule_name: str,
        rule: dict[str, Any],
    ) -> None:
        """Add an alert rule."""
        self._alert_rules[rule_name] = rule

    def get_report(self, report_id: str) -> Report | None:
        """Get a report by ID."""
        with self._lock:
            return self._reports.get(report_id)

    def list_reports(self) -> list[Report]:
        """List all reports."""
        with self._lock:
            return list(self._reports)
