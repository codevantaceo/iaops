from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def _run_command(command: Iterable[str], *, dry_run: bool = False, check: bool = True) -> CommandResult:
    cmd_list = list(command)
    if dry_run:
        return CommandResult(cmd_list, 0, "", "")

    completed = subprocess.run(cmd_list, capture_output=True, text=True)
    if check and completed.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd_list)}): {completed.stderr.strip()}")
    return CommandResult(cmd_list, completed.returncode, completed.stdout, completed.stderr)


def build_image(image: str, *, context: str = ".", dockerfile: str = "Dockerfile", dry_run: bool = False) -> CommandResult:
    """Build a container image using the local Docker daemon."""
    return _run_command(
        ["docker", "build", "-t", image, "-f", dockerfile, context],
        dry_run=dry_run,
    )


def generate_sbom(
    image: str,
    *,
    output_path: str = "sbom.json",
    output_format: str = "cyclonedx-json",
    dry_run: bool = False,
) -> CommandResult:
    """Generate an SBOM using syft and write it to disk."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    return _run_command(
        ["syft", image, "-o", output_format, "-q", "--file", output_path],
        dry_run=dry_run,
    )


def sign_image(
    image: str,
    *,
    key_ref: str | None = None,
    identity_token: str | None = None,
    annotations: dict[str, str] | None = None,
    keyless: bool = True,
    dry_run: bool = False,
) -> CommandResult:
    """Sign an image with cosign using either a key or keyless mode."""
    cmd: list[str] = ["cosign", "sign", "--yes"]

    if key_ref:
        cmd.extend(["--key", key_ref])
        keyless = False

    if identity_token:
        cmd.extend(["--identity-token", identity_token])

    if annotations:
        for key, value in annotations.items():
            cmd.extend(["--annotation", f"{key}={value}"])

    if keyless:
        cmd.append("--keyless")

    cmd.append(image)
    return _run_command(cmd, dry_run=dry_run)


def pipeline(
    image: str,
    *,
    context: str,
    dockerfile: str,
    sbom_path: str,
    key_ref: str | None,
    identity_token: str | None,
    annotations: dict[str, str] | None,
    dry_run: bool,
) -> None:
    build_image(image, context=context, dockerfile=dockerfile, dry_run=dry_run)
    generate_sbom(image, output_path=sbom_path, dry_run=dry_run)
    sign_image(image, key_ref=key_ref, identity_token=identity_token, annotations=annotations, dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build, SBOM, and sign an image using cosign.")
    parser.add_argument("--image", required=True, help="Image tag to build and sign (e.g., ghcr.io/org/app:tag).")
    parser.add_argument("--context", default=".", help="Build context directory.")
    parser.add_argument("--dockerfile", default="Dockerfile", help="Path to Dockerfile.")
    parser.add_argument("--sbom-path", default="sbom.json", help="Where to write the generated SBOM.")
    parser.add_argument("--key-ref", help="Cosign key reference (file path or KMS URI).")
    parser.add_argument("--identity-token", help="OIDC identity token for keyless signing.")
    parser.add_argument("--annotation", action="append", default=[], help="Annotations for the signature key=value.")
    parser.add_argument("--no-keyless", action="store_true", help="Disable keyless signing even when key is absent.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    annotations: dict[str, str] = {}
    for item in args.annotation:
        if "=" not in item:
            raise ValueError(f"Invalid annotation '{item}', expected key=value.")
        key, value = item.split("=", 1)
        annotations[key] = value

    pipeline(
        image=args.image,
        context=args.context,
        dockerfile=args.dockerfile,
        sbom_path=args.sbom_path,
        key_ref=args.key_ref,
        identity_token=args.identity_token,
        annotations=annotations or None,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
