from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .adapters.generic import AdapterContext, GenericAdapter, detect_adapter, load_adapters_config
from .adapters.go import GoAdapter
from .adapters.node import NodeAdapter
from .adapters.python import PythonAdapter
from .graph import DAG, GraphError, dag_is_acyclic, topological_sort
from .hashing import Hasher
from .io import ensure_dir, read_text, write_text
from .normalize import Normalizer
from .observability import EventStream
from .patcher import Patcher
from .planner import Planner
from .scanner import NarrativeSecretScanner
from .sealing import Sealer
from .verifier import Verifier, load_jsonschema


@dataclass(frozen=True)
class EngineConfig:
    raw: dict[str, Any]
    config_path: Path
    project_root: Path
    mode: str

    @property
    def state_dir(self) -> Path:
        return self.project_root / self.raw["spec"]["stateDir"]

    @property
    def evidence_dir(self) -> Path:
        return self.project_root / self.raw["spec"]["evidenceDir"]

    @property
    def event_stream_path(self) -> Path:
        return self.project_root / self.raw["spec"]["eventStream"]

    @property
    def outputs(self) -> dict[str, str]:
        return self.raw["spec"]["outputs"]

    @property
    def inputs(self) -> dict[str, Any]:
        return self.raw["spec"]["inputs"]

    @property
    def dag_nodes(self) -> list[dict[str, Any]]:
        return self.raw["spec"]["dag"]["nodes"]

    @property
    def allow_writes(self) -> bool:
        return bool(self.raw["spec"].get("repair", {}).get("allowWrites", False))

    @property
    def governance(self) -> dict[str, Any]:
        return self.raw["spec"]["governance"]

    @property
    def config_base(self) -> Path:
        """The base directory for resolving input paths in the config.

        Config paths like 'configs/...' and 'schemas/...' are relative to the
        repository root that contains the config file, i.e. config_path's
        grandparent when the config lives in a 'configs/' subdirectory.
        We walk up from config_path.parent until we find a directory that
        makes the relative path resolve, falling back to config_path.parent.
        """
        return self.config_path.resolve().parent.parent

    def resolve_input(self, rel: str) -> Path:
        """Resolve an input path: try config_base first, then project_root."""
        p = self.config_base / rel
        if p.exists():
            return p
        p2 = self.project_root / rel
        if p2.exists():
            return p2
        return p


class Engine:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg
        ensure_dir(self.cfg.state_dir)
        ensure_dir(self.cfg.evidence_dir)
        ensure_dir(self.cfg.event_stream_path.parent)
        self.events = EventStream(
            self.cfg.event_stream_path,
            schema_path=self.cfg.resolve_input(self.cfg.inputs["schemas"]["event"]),
        )
        self.hasher = Hasher(self.cfg.governance["hash"]["algorithms"])
        self.scanner = NarrativeSecretScanner(
            narrative_patterns=self.cfg.governance["banNarrative"]["patterns"],
            forbid_question_patterns=self.cfg.governance["forbidQuestions"]["patterns"],
            secret_patterns=None,
        )
        adapters_cfg = load_adapters_config(
            self.cfg.resolve_input(self.cfg.inputs["adaptersConfig"])
        )
        adapter_id = detect_adapter(self.cfg.project_root, adapters_cfg)
        self.adapter = self._build_adapter(adapter_id)

    @staticmethod
    def from_config(config_path: Path, project_root: Path, mode: str | None = None) -> Engine:
        raw = yaml.safe_load(read_text(config_path))
        config_base = config_path.resolve().parent.parent
        schema_rel = raw["spec"]["inputs"]["schemas"]["pipeline"]
        schema_path = config_base / schema_rel
        if not schema_path.exists():
            schema_path = project_root / schema_rel
        load_jsonschema(schema_path).validate(raw)
        m = mode or raw["spec"]["modes"]["default"]
        cfg = EngineConfig(raw=raw, config_path=config_path, project_root=project_root, mode=m)
        return Engine(cfg)

    def _build_adapter(self, adapter_id: str):
        ctx = AdapterContext(project_root=self.cfg.project_root, state_dir=self.cfg.state_dir)
        if adapter_id == "python":
            return PythonAdapter(ctx)
        if adapter_id == "node":
            return NodeAdapter(ctx)
        if adapter_id == "go":
            return GoAdapter(ctx)
        return GenericAdapter(ctx)

    def _get_execution_plan(self, trace_id: str) -> tuple[bool, list[str] | None]:
        dag = DAG.from_nodes(self.cfg.dag_nodes)
        if not dag_is_acyclic(dag):
            self.events.emit(trace_id, "governance", "dag_cycle", {"ok": False})
            return False, None
        order = dag.topological_sort()
        if order is None:
            self.events.emit(trace_id, "governance", "dag_cycle", {"ok": False})
            return False, None
        return True, order

    def _get_step_function(self, step_id: str):
        step_map = {
            "interface_metadata_parse": self.step_interface_metadata_parse,
            "parameter_validation": self.step_parameter_validation,
            "permission_resolution": self.step_permission_resolution,
            "security_assessment": self.step_security_assessment,
            "approval_chain_validation": self.step_approval_chain_validation,
            "tool_execution": self.step_tool_execution,
            "history_immutable": self.step_history_immutable,
            "continuous_monitoring": self.step_continuous_monitoring,
        }
        return step_map.get(step_id)

    def run(self) -> dict[str, Any]:
        trace_id = self.events.new_trace_id()
        dag_valid, execution_order = self._get_execution_plan(trace_id)
        if not dag_valid or not execution_order:
            return {"ok": False, "error": "dag_cycle", "traceId": trace_id}

        context: dict[str, Any] = {}
        outputs: OrderedDict[str, Any] = OrderedDict()
        outputs["ok"] = True
        outputs["traceId"] = trace_id
        outputs["mode"] = self.cfg.mode
        outputs["steps"] = OrderedDict()

        for step_id in execution_order:
            step_fn = self._get_step_function(step_id)
            if not step_fn:
                self.events.emit(trace_id, step_id, "error", {"error": "step_not_implemented"})
                outputs["ok"] = False
                outputs["failedStep"] = step_id
                outputs["error"] = f"Step function for {step_id} not implemented"
                break
            try:
                self.events.emit(trace_id, step_id, "start", {})
                start_time = time.monotonic()
                result = step_fn(trace_id, step_id, context)
                elapsed = time.monotonic() - start_time
                self.events.emit(trace_id, step_id, "end", {"result": result, "elapsed": elapsed})
                outputs["steps"][step_id] = result
                context[step_id] = result
                if not result.get("ok", False):
                    outputs["ok"] = False
                    outputs["failedStep"] = step_id
                    outputs["error"] = result.get("error", "unknown")
                    break
            except Exception as e:  # pragma: no cover - defensive
                self.events.emit(trace_id, step_id, "error", {"error": str(e)})
                outputs["ok"] = False
                outputs["failedStep"] = step_id
                outputs["error"] = str(e)
                break

        outputs["success"] = outputs["ok"]
        return outputs

    def step_interface_metadata_parse(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        index = self.adapter.index()
        snapshot = self.adapter.snapshot()
        scanner_findings = self.scanner.scan_index(index)
        self.events.emit(trace_id, step_id, "findings", scanner_findings)
        if scanner_findings["blocked"]:
            return {"ok": False, "error": scanner_findings["reason"], "findings": scanner_findings}
        return {
            "ok": True,
            "adapter": self.adapter.name,
            "files": len(index["files"]),
            "snapshot": snapshot,
        }

    def step_parameter_validation(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        policies_path = self.cfg.resolve_input(self.cfg.inputs["policiesConfig"])
        roles_path = self.cfg.resolve_input(self.cfg.inputs["rolesRegistry"])
        policies = yaml.safe_load(read_text(policies_path))
        roles = yaml.safe_load(read_text(roles_path))

        load_jsonschema(self.cfg.resolve_input(self.cfg.inputs["schemas"]["policies"])).validate(
            policies
        )
        load_jsonschema(self.cfg.resolve_input(self.cfg.inputs["schemas"]["roles"])).validate(roles)

        return {"ok": True, "policiesLoaded": True, "rolesLoaded": True}

    def step_permission_resolution(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        allow_writes = self.cfg.allow_writes and (self.cfg.mode in {"repair"})
        return {"ok": True, "allowWrites": allow_writes}

    def step_security_assessment(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        findings = self.adapter.security_scan()
        if findings.get("blocked"):
            return {"ok": False, "error": "security_blocked", "findings": findings}
        return {"ok": True, "findings": findings}

    def step_approval_chain_validation(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"ok": True, "approval": "local-policy-auto"}

    def step_tool_execution(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        normalizer = Normalizer(self.cfg.project_root)
        planner = Planner(self.cfg.project_root, self.adapter)
        patcher = Patcher(
            self.cfg.project_root,
            allow_writes=(self.cfg.mode == "repair" and self.cfg.allow_writes),
        )
        verifier = Verifier(self.cfg.project_root, self.adapter)

        normalized = normalizer.run()
        plan = planner.build_plan()
        plan_path = self.cfg.project_root / self.cfg.outputs["planFile"]
        ensure_dir(plan_path.parent)
        write_text(plan_path, json.dumps(plan, indent=2, sort_keys=True))

        if self.cfg.mode == "plan":
            return {
                "ok": True,
                "normalized": normalized,
                "planOnly": True,
                "planFile": str(plan_path),
            }

        patch_report = patcher.apply(plan)
        patch_path = self.cfg.project_root / self.cfg.outputs["patchReport"]
        ensure_dir(patch_path.parent)
        write_text(patch_path, json.dumps(patch_report, indent=2, sort_keys=True))

        verify_report = verifier.run()
        verify_path = self.cfg.project_root / self.cfg.outputs["verifyReport"]
        ensure_dir(verify_path.parent)
        write_text(verify_path, json.dumps(verify_report, indent=2, sort_keys=True))

        if self.cfg.mode == "verify":
            return {
                "ok": verify_report["ok"],
                "normalized": normalized,
                "verified": True,
                "verify": verify_report,
            }

        return {
            "ok": verify_report["ok"],
            "normalized": normalized,
            "patched": patch_report,
            "verify": verify_report,
        }

    def step_history_immutable(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        manifest = self.hasher.hash_tree(
            self.cfg.project_root, exclude_dirs={self.cfg.state_dir.name, ".git"}
        )
        hist_path = self.cfg.evidence_dir / "hash-manifest.json"
        write_text(hist_path, json.dumps(manifest, indent=2, sort_keys=True))
        return {"ok": True, "hashManifest": str(hist_path), "files": len(manifest["files"])}

    def step_continuous_monitoring(
        self, trace_id: str, step_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self.cfg.mode in {"seal", "repair", "verify"}:
            sealer = Sealer(
                self.cfg.project_root,
                self.cfg.state_dir,
                self.cfg.evidence_dir,
                self.hasher,
            )
            seal = sealer.seal()
            if self.cfg.mode == "seal" and not seal["ok"]:
                return {"ok": False, "error": "seal_failed", "seal": seal}
            return {"ok": True, "sealed": seal}
        return {"ok": True, "monitoring": "noop"}


class ExecutionContext:
    """Shared execution context across pipeline steps."""

    def __init__(self):
        self.data: dict[str, Any] = {}

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default: Any | None = None) -> Any:
        return self.data.get(key, default)


class StepReport:
    """Step execution report."""

    def __init__(
        self,
        step_id: str,
        status: str,
        output: Any | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        error: str | None = None,
    ):
        self.step_id = step_id
        self.status = status
        self.output = output
        self.start_time = start_time or time.time()
        self.end_time = end_time
        self.error = error
        self.duration = 0.0

        if start_time and end_time:
            self.duration = end_time - start_time


class StepRecord:
    """Step execution record for DAG orchestration."""

    def __init__(
        self,
        step_id: str,
        status: str,
        output: Any | None = None,
        error: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ):
        self.step_id = step_id
        self.status = status
        self.output = output
        self.error = error
        self.start_time = start_time
        self.end_time = end_time
        self.duration = (end_time - start_time) if start_time and end_time else 0


class OrchestrationEngine:
    """Lightweight DAG-based orchestration engine."""

    def __init__(self):
        self.steps: dict[str, Any] = {}
        self.dependencies: list[tuple[str, str]] = []
        self.context = ExecutionContext()
        self.records: dict[str, StepRecord] = {}

    def register_step(
        self,
        step_id: str,
        func: Any | None = None,
        requires: Any | None = None,
        depends_on: Any | None = None,
    ):
        """Register a step function; usable as decorator or direct call."""
        deps = depends_on if requires is None else requires

        def _register(fn: Any):
            self.steps[step_id] = fn
            if deps:
                dep_list = [deps] if isinstance(deps, str) else list(deps)
                for dep in dep_list:
                    self.dependencies.append((dep, step_id))
            return fn

        if func is not None:
            return _register(func)
        return _register

    def build_plan(self) -> list[str]:
        """Return the DAG execution order."""
        try:
            return topological_sort(nodes=list(self.steps.keys()), edges=self.dependencies)
        except GraphError as e:
            logging.error(f"Pipeline planning failed: {e}")
            raise

    def run_step(self, step_id: str) -> StepRecord:
        """Execute a single registered step."""
        func = self.steps.get(step_id)
        start_time = time.time()

        if not func:
            record = StepRecord(
                step_id=step_id,
                status="error",
                error=f"Step '{step_id}' not found",
                start_time=start_time,
                end_time=time.time(),
            )
            self.records[step_id] = record
            return record

        try:
            output = func(self.context)
            record = StepRecord(
                step_id=step_id,
                status="success",
                output=output,
                start_time=start_time,
                end_time=time.time(),
            )
        except Exception as e:  # pragma: no cover - defensive
            record = StepRecord(
                step_id=step_id,
                status="error",
                error=str(e),
                start_time=start_time,
                end_time=time.time(),
            )

        self.records[step_id] = record
        return record

    def execute(self) -> dict[str, StepRecord]:
        """Execute all steps following the DAG plan."""
        self.context = ExecutionContext()
        self.records = {}
        plan = self.build_plan()
        for step_id in plan:
            record = self.run_step(step_id)
            if record.status == "error":
                break
        return self.records


class PipelineEngine:
    """DAG-driven pipeline execution engine."""

    def __init__(self):
        self.steps: dict[str, Any] = {}
        self.dependencies: list[tuple[str, str]] = []
        self.reports: dict[str, StepReport] = {}
        self.context = ExecutionContext()

    def register_step(self, step_id: str, func: Any | None = None, depends_on: Any | None = None):
        """Register a step function; usable as a decorator or direct call."""

        def _register(fn: Any):
            self.steps[step_id] = fn
            if depends_on:
                deps = [depends_on] if isinstance(depends_on, str) else list(depends_on)
                for dep in deps:
                    self.dependencies.append((dep, step_id))
            return fn

        if func is not None:
            return _register(func)
        return _register

    def build_execution_plan(self) -> list[str]:
        """Build a topologically sorted execution plan."""
        try:
            return topological_sort(nodes=list(self.steps.keys()), edges=self.dependencies)
        except GraphError as e:
            logging.error(f"DAG validation failed: {e}")
            raise

    def execute_step(self, step_id: str) -> StepReport:
        """Execute a single step and produce a StepReport."""
        if step_id not in self.steps:
            return StepReport(step_id, "error", error=f"Step '{step_id}' not registered")

        func = self.steps[step_id]
        start_time = time.time()

        try:
            result = func(self.context)
            report = StepReport(
                step_id=step_id,
                status="success",
                output=result,
                start_time=start_time,
                end_time=time.time(),
            )
        except Exception as e:  # pragma: no cover - defensive
            report = StepReport(
                step_id=step_id,
                status="error",
                error=str(e),
                start_time=start_time,
                end_time=time.time(),
            )

        self.reports[step_id] = report
        return report

    def run_pipeline(self) -> dict[str, Any]:
        """Execute the pipeline following the DAG order."""
        execution_plan = self.build_execution_plan()
        final_report: dict[str, Any] = {}

        for step_id in execution_plan:
            report = self.execute_step(step_id)
            final_report[step_id] = report.__dict__

            if report.status == "error":
                logging.error(f"Step '{step_id}' failed: {report.error}")
                break

        return final_report
