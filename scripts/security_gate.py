from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTS = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".txt",
    ".html",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "synthetic_data/data"}

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
]
FORBIDDEN_MODEL_PATTERNS = [
    re.compile(r"(?i)\bqwen\b"),
    re.compile(r"(?i)\bfunctiongemma\b"),
]
URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")
ALLOWED_URL_HOST_SUBSTRINGS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "json-schema.org",
    "example.local",
}


def should_scan(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTS:
        return False
    for part in path.parts:
        if part in SKIP_DIRS:
            return False
    return True


def scan() -> tuple[list[str], list[str], list[str]]:
    secret_issues: list[str] = []
    model_policy_issues: list[str] = []
    egress_issues: list[str] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue

        content = path.read_text(encoding="utf-8", errors="ignore")

        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                secret_issues.append(str(path.relative_to(ROOT)))
                break

        for pattern in FORBIDDEN_MODEL_PATTERNS:
            if pattern.search(content):
                model_policy_issues.append(str(path.relative_to(ROOT)))
                break

        for url in URL_PATTERN.findall(content):
            if all(host not in url for host in ALLOWED_URL_HOST_SUBSTRINGS):
                # Documentation links are allowed.
                if str(path.relative_to(ROOT)).startswith("docs/"):
                    continue
                egress_issues.append(f"{path.relative_to(ROOT)} -> {url}")
                break

    return secret_issues, model_policy_issues, egress_issues


def main() -> int:
    secret_issues, model_policy_issues, egress_issues = scan()
    failed = False

    if secret_issues:
        failed = True
        print("security_gate=FAIL secrets_detected")
        for issue in sorted(set(secret_issues)):
            print(f"secret_issue={issue}")

    if model_policy_issues:
        failed = True
        print("security_gate=FAIL forbidden_model_reference_detected")
        for issue in sorted(set(model_policy_issues)):
            print(f"model_policy_issue={issue}")

    if egress_issues:
        failed = True
        print("security_gate=FAIL non_local_url_detected")
        for issue in sorted(set(egress_issues)):
            print(f"egress_issue={issue}")

    if failed:
        return 1

    print("security_gate=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
