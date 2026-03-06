from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable


def _run(command: Iterable[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[str] | None:
    cmd_list = list(command)
    if dry_run:
        return subprocess.CompletedProcess(cmd_list, 0, "", "")
    return subprocess.run(cmd_list, capture_output=True, text=True)


def verify_signature(image: str, *, key_ref: str | None, certificate_identity: str | None, dry_run: bool = False) -> bool:
    cmd: list[str] = ["cosign", "verify", image]
    if key_ref:
        cmd.extend(["--key", key_ref])
    if certificate_identity:
        cmd.extend(["--certificate-identity", certificate_identity])

    result = _run(cmd, dry_run=dry_run)
    if result is None:
        return True
    return result.returncode == 0


def verify_attestation(image: str, policy_path: str, *, dry_run: bool = False) -> bool:
    cmd = ["cosign", "verify-attestation", "--policy", policy_path, image]
    result = _run(cmd, dry_run=dry_run)
    if result is None:
        return True
    return result.returncode == 0


def verify_sbom(sbom_path: str) -> bool:
    path = Path(sbom_path)
    if not path.exists():
        raise FileNotFoundError(f"SBOM not found at {sbom_path}")

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    components = data.get("components") or data.get("bom", {}).get("components") or []
    return bool(components)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verification gate for signed images and SBOMs.")
    parser.add_argument("--image", required=True, help="Image reference to verify.")
    parser.add_argument("--sbom", required=True, help="Path to SBOM file.")
    parser.add_argument("--key-ref", help="Public key reference used for cosign verify.")
    parser.add_argument("--certificate-identity", help="Expected certificate identity for keyless verification.")
    parser.add_argument("--policy", default="policy/rego/supplychain.rego", help="Rego policy used for attestations.")
    parser.add_argument("--skip-attestation", action="store_true", help="Skip cosign verify-attestation.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signature_ok = verify_signature(
        args.image,
        key_ref=args.key_ref,
        certificate_identity=args.certificate_identity,
        dry_run=args.dry_run,
    )
    sbom_ok = verify_sbom(args.sbom)
    attestation_ok = True
    if not args.skip_attestation:
        attestation_ok = verify_attestation(args.image, args.policy, dry_run=args.dry_run)

    if not (signature_ok and sbom_ok and attestation_ok):
        raise SystemExit("Verification gate failed.")


if __name__ == "__main__":
    main()
