"""
Delivery Agent for CI/CD and GitOps Integration.

This agent handles CI/CD pipeline management, GitOps operations, and supply chain.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..base import Agent, AgentCapability


@dataclass
class CIPatchSet:
    """A set of CI/CD patches."""

    patch_id: str
    provider: str
    repository: str
    patches: list[dict[str, Any]]
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AttestationInput:
    """Input for creating attestations."""

    attestation_id: str
    type: str
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class DeliveryAgent(Agent):
    """Agent for delivery operations (CI/CD, GitOps, supply chain)."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="generate_ci_config",
                description="Generate CI/CD configuration files",
                input_types=["project_snapshot", "repair_plan"],
                output_types=["ci_patch_set"],
            ),
            AgentCapability(
                name="apply_template",
                description="Apply CI/CD template from library",
                input_types=["provider", "template_name", "variables"],
                output_types=["ci_config"],
            ),
            AgentCapability(
                name="update_dependencies",
                description="Update project dependencies",
                input_types=["project_root", "package_manager"],
                output_types=["update_report"],
            ),
            AgentCapability(
                name="create_attestation",
                description="Create supply chain attestations",
                input_types=["attestation_type", "data"],
                output_types=["attestation"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._ci_patch_sets: dict[str, CIPatchSet] = {}
        self._attestations: dict[str, AttestationInput] = {}
        self._templates: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Load default templates
        self._load_default_templates()

    async def initialize(self) -> None:
        """Initialize the delivery agent."""
        # Load custom templates if configured
        templates_dir = self.config.get("templates_dir")
        if templates_dir:
            await self._load_templates_from_dir(templates_dir)

    async def shutdown(self) -> None:
        """Shutdown the delivery agent."""
        # Save state if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            await self._save_state(state_dir)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "generate_ci_config":
                return await self._task_generate_ci_config(payload, context)
            elif task_type == "apply_template":
                return await self._task_apply_template(payload, context)
            elif task_type == "update_dependencies":
                return await self._task_update_dependencies(payload, context)
            elif task_type == "create_attestation":
                return await self._task_create_attestation(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_generate_ci_config(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Generate CI/CD configuration files."""
        project_snapshot = payload.get("project_snapshot")
        repair_plan = payload.get("repair_plan")
        provider = payload.get("provider", "github")

        if not project_snapshot:
            raise ValueError("project_snapshot is required")

        # Detect project type
        project_type = self._detect_project_type(project_snapshot)

        # Generate CI config based on provider and project type
        patches = []
        if provider == "github":
            patches.extend(
                await self._generate_github_actions(project_type, project_snapshot, repair_plan)
            )
        elif provider == "gitlab":
            patches.extend(
                await self._generate_gitlab_ci(project_type, project_snapshot, repair_plan)
            )
        elif provider == "azure":
            patches.extend(
                await self._generate_azure_pipelines(project_type, project_snapshot, repair_plan)
            )

        # Create patch set
        patch_set = CIPatchSet(
            patch_id=f"ci_patch_{int(time.time())}_{self.agent_id}",
            provider=provider,
            repository=project_snapshot.get("project_root", ""),
            patches=patches,
            status="generated",
            metadata={
                "project_type": project_type,
                "created_by": self.agent_id,
            },
        )

        with self._lock:
            self._ci_patch_sets[patch_set.patch_id] = patch_set

        return {
            "success": True,
            "patch_set": patch_set.__dict__,
        }

    async def _task_apply_template(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Apply CI/CD template from library."""
        provider = payload.get("provider", "github")
        template_name = payload.get("template_name")
        variables = payload.get("variables", {})

        if not template_name:
            raise ValueError("template_name is required")

        template_key = f"{provider}:{template_name}"
        template = self._templates.get(template_key)

        if not template:
            raise ValueError(f"Template not found: {template_key}")

        # Apply variables to template
        ci_config = template["content"]

        for key, value in variables.items():
            ci_config = ci_config.replace(f"${{{key}}}", str(value))

        return {
            "success": True,
            "provider": provider,
            "template_name": template_name,
            "ci_config": ci_config,
        }

    async def _task_update_dependencies(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Update project dependencies."""
        project_root = payload.get("project_root")
        package_manager = payload.get("package_manager")

        if not project_root:
            raise ValueError("project_root is required")

        root_path = Path(project_root)

        # Auto-detect package manager if not specified
        if not package_manager:
            package_manager = self._detect_package_manager(root_path)

        if not package_manager:
            raise ValueError("Could not detect package manager")

        # Update dependencies based on package manager
        if package_manager == "pip":
            return await self._update_python_deps(root_path, context)
        elif package_manager == "npm":
            return await self._update_node_deps(root_path, context)
        elif package_manager == "go":
            return await self._update_go_deps(root_path, context)
        else:
            raise ValueError(f"Unsupported package manager: {package_manager}")

    async def _task_create_attestation(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Create supply chain attestation."""
        attestation_type = payload.get("attestation_type")
        data = payload.get("data", {})

        if not attestation_type:
            raise ValueError("attestation_type is required")

        attestation = AttestationInput(
            attestation_id=f"attestation_{int(time.time())}_{self.agent_id}",
            type=attestation_type,
            data=data,
            metadata={
                "created_by": self.agent_id,
                "timestamp": time.time(),
            },
        )

        with self._lock:
            self._attestations[attestation.attestation_id] = attestation

        return {
            "success": True,
            "attestation": attestation.__dict__,
        }

    def _detect_project_type(self, project_snapshot: dict[str, Any]) -> str:
        """Detect project type from snapshot."""
        file_index = project_snapshot.get("file_index", {})

        # Check for language indicators
        if "requirements.txt" in file_index or "pyproject.toml" in file_index:
            return "python"
        elif "package.json" in file_index:
            return "node"
        elif "go.mod" in file_index:
            return "go"
        elif "pom.xml" in file_index:
            return "java"
        elif "Cargo.toml" in file_index:
            return "rust"
        else:
            return "generic"

    def _detect_package_manager(self, project_root: Path) -> str | None:
        """Detect package manager from project."""
        # Python
        if (project_root / "pyproject.toml").exists():
            return "pip"
        if (project_root / "requirements.txt").exists():
            return "pip"
        if (project_root / "Pipfile").exists():
            return "pip"

        # Node.js
        if (project_root / "package.json").exists():
            if (project_root / "yarn.lock").exists():
                return "yarn"
            if (project_root / "pnpm-lock.yaml").exists():
                return "pnpm"
            return "npm"

        # Go
        if (project_root / "go.mod").exists():
            return "go"

        return None

    async def _generate_github_actions(
        self,
        project_type: str,
        project_snapshot: dict[str, Any],
        repair_plan: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Generate GitHub Actions configuration."""
        config = self._get_github_actions_template(project_type)

        patches = [
            {
                "file_path": ".github/workflows/ci.yml",
                "content": config,
                "action": "create",
            },
        ]

        return patches

    async def _generate_gitlab_ci(
        self,
        project_type: str,
        project_snapshot: dict[str, Any],
        repair_plan: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Generate GitLab CI configuration."""
        config = self._get_gitlab_ci_template(project_type)

        patches = [
            {
                "file_path": ".gitlab-ci.yml",
                "content": config,
                "action": "create",
            },
        ]

        return patches

    async def _generate_azure_pipelines(
        self,
        project_type: str,
        project_snapshot: dict[str, Any],
        repair_plan: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Generate Azure Pipelines configuration."""
        config = self._get_azure_pipelines_template(project_type)

        patches = [
            {
                "file_path": "azure-pipelines.yml",
                "content": config,
                "action": "create",
            },
        ]

        return patches

    async def _update_python_deps(
        self,
        project_root: Path,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Update Python dependencies."""
        # In production, would actually run pip/poetry commands
        # For now, simulate the update

        requirements_file = project_root / "requirements.txt"
        if requirements_file.exists():
            # Parse requirements
            deps = []
            with open(requirements_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        deps.append(line)

            return {
                "success": True,
                "package_manager": "pip",
                "dependencies_count": len(deps),
                "updated": True,
                "message": "Dependencies analyzed (simulated update)",
            }

        return {
            "success": False,
            "error": "No requirements.txt found",
        }

    async def _update_node_deps(
        self,
        project_root: Path,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Update Node.js dependencies."""
        package_file = project_root / "package.json"
        if package_file.exists():
            return {
                "success": True,
                "package_manager": "npm",
                "updated": True,
                "message": "Dependencies analyzed (simulated update)",
            }

        return {
            "success": False,
            "error": "No package.json found",
        }

    async def _update_go_deps(
        self,
        project_root: Path,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Update Go dependencies."""
        go_mod = project_root / "go.mod"
        if go_mod.exists():
            return {
                "success": True,
                "package_manager": "go",
                "updated": True,
                "message": "Dependencies analyzed (simulated update)",
            }

        return {
            "success": False,
            "error": "No go.mod found",
        }

    def _get_github_actions_template(self, project_type: str) -> str:
        """Get GitHub Actions template for project type."""
        templates = {
            "python": """
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run tests
        run: |
          python -m pytest tests/
""",
            "node": """
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Install dependencies
        run: npm ci
      - name: Run tests
        run: npm test
""",
            "go": """
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      - name: Run tests
        run: go test ./...
""",
        }

        return templates.get(project_type, templates["python"])

    def _get_gitlab_ci_template(self, project_type: str) -> str:
        """Get GitLab CI template for project type."""
        return """
stages:
  - test

test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pytest tests/
"""

    def _get_azure_pipelines_template(self, project_type: str) -> str:
        """Get Azure Pipelines template for project type."""
        return """
trigger:
- main

pool:
  vmImage: 'ubuntu-latest'

steps:
- script: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pytest tests/
  displayName: 'Run tests'
"""

    def _load_default_templates(self) -> None:
        """Load default CI/CD templates."""
        # GitHub Actions templates
        self._templates["github:python"] = {
            "name": "Python CI",
            "content": self._get_github_actions_template("python"),
        }
        self._templates["github:node"] = {
            "name": "Node.js CI",
            "content": self._get_github_actions_template("node"),
        }
        self._templates["github:go"] = {
            "name": "Go CI",
            "content": self._get_github_actions_template("go"),
        }

        # GitLab CI templates
        self._templates["gitlab:default"] = {
            "name": "Default CI",
            "content": self._get_gitlab_ci_template("python"),
        }

        # Azure Pipelines templates
        self._templates["azure:default"] = {
            "name": "Default Pipeline",
            "content": self._get_azure_pipelines_template("python"),
        }

    async def _load_templates_from_dir(self, templates_dir: str) -> None:
        """Load custom templates from directory."""
        # Implementation would load YAML/JSON templates
        pass

    async def _save_state(self, state_dir: str) -> None:
        """Save agent state."""
        pass

    def get_patch_set(self, patch_id: str) -> CIPatchSet | None:
        """Get a CI patch set by ID."""
        with self._lock:
            return self._ci_patch_sets.get(patch_id)

    def list_patch_sets(self) -> list[CIPatchSet]:
        """List all CI patch sets."""
        with self._lock:
            return list(self._ci_patch_sets.values())

    def get_attestation(self, attestation_id: str) -> AttestationInput | None:
        """Get an attestation by ID."""
        with self._lock:
            return self._attestations.get(attestation_id)

    def list_templates(self, provider: str | None = None) -> list[dict[str, Any]]:
        """List available templates."""
        with self._lock:
            if provider:
                return [
                    {"key": k, **v}
                    for k, v in self._templates.items()
                    if k.startswith(f"{provider}:")
                ]
            return [{"key": k, **v} for k, v in self._templates.items()]
