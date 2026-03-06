import hashlib
import re


class SecurityScanner:
    SECURE_PATTERNS = re.compile(r"(?i)(?:secret|password|api[_-]?key|token|auth)")

    RISK_PATTERNS = [
        re.compile(r"(<script|javascript:|on\w+\s*=)", re.IGNORECASE),
        re.compile(r"(?:union\s+select|select\s+.*from)", re.IGNORECASE),
        re.compile(r"\./\.\./", re.IGNORECASE),
    ]

    def inspect(self, file_path: str, content: str = "") -> dict[str, object]:
        """Inspect provided content for sensitive data and risky patterns."""
        report = {
            "path": file_path,
            "blocked_by_name": False,
            "sensitive_found": False,
            "risks": [],
        }

        if re.search(r"\.(env|key|pem|secret)$", file_path):
            report["blocked_by_name"] = True

        if self.SECURE_PATTERNS.search(content):
            report["sensitive_found"] = True

        for pattern in self.RISK_PATTERNS:
            if pattern.search(content):
                report["risks"].append(pattern.pattern)

        report["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
        report["is_secure"] = not (
            report["blocked_by_name"] or report["sensitive_found"] or report["risks"]
        )
        report["is_safe"] = report["is_secure"]  # backward compatibility
        report["pattern_match"] = report["blocked_by_name"]
        report["sensitive_data"] = report["sensitive_found"]
        report["vulnerabilities"] = report["risks"]
        report["filename"] = file_path
        return report

    def scan_file(self, path: str, content: str):
        """Backward compatible wrapper for legacy callers."""
        return self.inspect(path, content)
