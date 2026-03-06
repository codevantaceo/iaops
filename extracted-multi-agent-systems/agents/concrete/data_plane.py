"""
DataPlane Agent for Filesystem and Artifact Management.

This agent handles filesystem operations, snapshots, and file indexing.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..base import Agent, AgentCapability


@dataclass
class ProjectSnapshot:
    """Snapshot of a project state."""

    snapshot_id: str
    project_root: str
    timestamp: float
    file_count: int
    total_size: int
    file_index: dict[str, dict[str, Any]]
    hash_manifest: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)


class DataPlaneAgent(Agent):
    """Agent for data plane operations (filesystem, artifacts, snapshots)."""

    def __init__(
        self,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ):
        capabilities = [
            AgentCapability(
                name="file_scan",
                description="Scan filesystem and create file index",
                input_types=["project_root"],
                output_types=["file_index"],
            ),
            AgentCapability(
                name="create_snapshot",
                description="Create a project snapshot",
                input_types=["project_root", "state_dir"],
                output_types=["project_snapshot"],
            ),
            AgentCapability(
                name="read_file",
                description="Read file contents",
                input_types=["file_path"],
                output_types=["file_content"],
            ),
            AgentCapability(
                name="write_file",
                description="Write file contents",
                input_types=["file_path", "content"],
                output_types=["write_result"],
            ),
            AgentCapability(
                name="compute_hash",
                description="Compute file/directory hash",
                input_types=["path"],
                output_types=["hash"],
            ),
        ]

        super().__init__(agent_id, capabilities, config)

        # Internal state
        self._snapshots: dict[str, ProjectSnapshot] = {}
        self._file_cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._indexing_cache: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Initialize the data plane agent."""
        # Load existing snapshots if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            state_path = Path(state_dir)
            if state_path.exists():
                await self._load_snapshots(state_path)

    async def shutdown(self) -> None:
        """Shutdown the data plane agent."""
        # Save snapshots if configured
        state_dir = self.config.get("state_dir")
        if state_dir:
            state_path = Path(state_dir)
            state_path.mkdir(parents=True, exist_ok=True)
            await self._save_snapshots(state_path)

    async def execute_task(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a task assigned to this agent."""
        task_type = task.get("task_type", "")
        payload = task.get("payload", {})

        try:
            if task_type == "file_scan":
                return await self._task_file_scan(payload, context)
            elif task_type == "create_snapshot":
                return await self._task_create_snapshot(payload, context)
            elif task_type == "read_file":
                return await self._task_read_file(payload, context)
            elif task_type == "write_file":
                return await self._task_write_file(payload, context)
            elif task_type == "compute_hash":
                return await self._task_compute_hash(payload, context)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type,
            }

    async def _task_file_scan(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Scan filesystem and create file index."""
        project_root = payload.get("project_root")
        if not project_root:
            raise ValueError("project_root is required")

        root_path = Path(project_root)
        if not root_path.exists():
            raise ValueError(f"Project root does not exist: {project_root}")

        # Check cache
        cache_key = f"file_scan:{project_root}"
        if cache_key in self._indexing_cache:
            return self._indexing_cache[cache_key]

        # Scan files
        file_index = {}
        total_size = 0

        for file_path in root_path.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(root_path))

                try:
                    stat = file_path.stat()
                    file_index[rel_path] = {
                        "path": rel_path,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "mime_type": self._guess_mime_type(file_path),
                        "hash": await self._compute_file_hash(file_path),
                    }
                    total_size += stat.st_size
                except Exception:
                    # Skip files we can't read
                    continue

        result = {
            "success": True,
            "project_root": project_root,
            "file_count": len(file_index),
            "total_size": total_size,
            "file_index": file_index,
        }

        # Cache result
        self._indexing_cache[cache_key] = result

        return result

    async def _task_create_snapshot(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Create a project snapshot."""
        project_root = payload.get("project_root")
        state_dir = payload.get("state_dir")

        if not project_root:
            raise ValueError("project_root is required")

        # Get file index
        scan_result = await self._task_file_scan(
            {"project_root": project_root},
            context,
        )

        # Compute hash manifest
        hash_manifest = {}
        for path, info in scan_result["file_index"].items():
            hash_manifest[path] = info["hash"]

        # Create snapshot
        snapshot = ProjectSnapshot(
            snapshot_id=f"snapshot_{int(time.time())}_{self.agent_id}",
            project_root=project_root,
            timestamp=time.time(),
            file_count=scan_result["file_count"],
            total_size=scan_result["total_size"],
            file_index=scan_result["file_index"],
            hash_manifest=hash_manifest,
            metadata={
                "created_by": self.agent_id,
                "state_dir": state_dir,
            },
        )

        # Store snapshot
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot

        return {
            "success": True,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot": snapshot.__dict__,
        }

    async def _task_read_file(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Read file contents."""
        file_path = payload.get("file_path")
        if not file_path:
            raise ValueError("file_path is required")

        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"File does not exist: {file_path}")

        # Check cache
        cache_key = f"file:{file_path}"
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        # Read file
        content = path.read_text(encoding="utf-8", errors="ignore")

        result = {
            "success": True,
            "file_path": file_path,
            "content": content,
            "size": len(content),
        }

        # Cache result
        self._file_cache[cache_key] = result

        return result

    async def _task_write_file(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Write file contents."""
        file_path = payload.get("file_path")
        content = payload.get("content")

        if not file_path or content is None:
            raise ValueError("file_path and content are required")

        path = Path(file_path)

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        path.write_text(content, encoding="utf-8")

        # Update cache
        cache_key = f"file:{file_path}"
        self._file_cache[cache_key] = {
            "success": True,
            "file_path": file_path,
            "content": content,
            "size": len(content),
        }

        # Invalidate file scan cache
        # (in production, would be more selective)

        return {
            "success": True,
            "file_path": file_path,
            "written": True,
        }

    async def _task_compute_hash(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Task: Compute file/directory hash."""
        path = payload.get("path")
        if not path:
            raise ValueError("path is required")

        path_obj = Path(path)

        if path_obj.is_file():
            file_hash = await self._compute_file_hash(path_obj)
            return {
                "success": True,
                "path": path,
                "type": "file",
                "hash": file_hash,
            }
        elif path_obj.is_dir():
            dir_hash = await self._compute_dir_hash(path_obj)
            return {
                "success": True,
                "path": path,
                "type": "directory",
                "hash": dir_hash,
            }
        else:
            raise ValueError(f"Path does not exist: {path}")

    async def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        return sha256.hexdigest()

    async def _compute_dir_hash(self, dir_path: Path) -> str:
        """Compute hash of a directory (based on file hashes)."""
        hash_manifest = {}

        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(dir_path))
                file_hash = await self._compute_file_hash(file_path)
                hash_manifest[rel_path] = file_hash

        # Hash the manifest
        manifest_str = json.dumps(hash_manifest, sort_keys=True)
        return hashlib.sha256(manifest_str.encode()).hexdigest()

    def _guess_mime_type(self, file_path: Path) -> str:
        """Guess the MIME type of a file."""
        # Simplified mime type detection
        ext = file_path.suffix.lower()

        mime_types = {
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".ts": "text/typescript",
            ".json": "application/json",
            ".yaml": "text/x-yaml",
            ".yml": "text/x-yaml",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".css": "text/css",
            ".xml": "application/xml",
            ".sh": "text/x-shellscript",
            ".go": "text/x-go",
        }

        return mime_types.get(ext, "application/octet-stream")

    async def _load_snapshots(self, state_dir: Path) -> None:
        """Load existing snapshots from state directory."""
        snapshots_file = state_dir / "snapshots.json"

        if not snapshots_file.exists():
            return

        try:
            with open(snapshots_file) as f:
                data = json.load(f)

            for snapshot_data in data.get("snapshots", []):
                snapshot = ProjectSnapshot(**snapshot_data)
                self._snapshots[snapshot.snapshot_id] = snapshot

        except Exception:
            pass

    async def _save_snapshots(self, state_dir: Path) -> None:
        """Save snapshots to state directory."""
        snapshots_file = state_dir / "snapshots.json"

        data = {
            "snapshots": [s.__dict__ for s in self._snapshots.values()],
        }

        with open(snapshots_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_snapshot(self, snapshot_id: str) -> ProjectSnapshot | None:
        """Get a snapshot by ID."""
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def list_snapshots(self) -> list[ProjectSnapshot]:
        """List all snapshots."""
        with self._lock:
            return list(self._snapshots.values())
