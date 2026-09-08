"""Fail closed before publishing. Findings print paths/rule IDs, never matches."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {
    ".git",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "test-results",
    "playwright-report",
    "dist",
    "htmlcov",
}
PRIVATE_NAMES = {
    ".local",
    ".storage",
    "secrets.yaml",
    "credentials.env",
    ".env",
    "snapshot",
    ".codex-remote-attachments",
    "family_assistant_data",
    "family_assistant_recovery",
}
PRIVATE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".backup",
    ".pcap",
    ".pcapng",
    ".log",
    ".jpg",
    ".jpeg",
    ".webp",
    ".heic",
    ".pfx",
}
RULES = {
    "private_lan_ip": re.compile(
        r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "telegram_token": re.compile(r"\b\d{5,15}:[A-Za-z0-9_-]{30,100}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "absolute_workspace": re.compile(r"[A-Za-z]:[\\/](?:Agents|Users)[\\/]", re.I),
}


def violations(relative: Path, content: bytes) -> list[str]:
    found = []
    if (
        any(part in PRIVATE_NAMES for part in relative.parts)
        or relative.suffix.lower() in PRIVATE_SUFFIXES
        or any(part.startswith(".upload-") for part in relative.parts)
        or re.fullmatch(r"[0-9a-f]{64}", relative.name) is not None
    ):
        found.append("private_file")
    if relative.suffix.lower() == ".png":
        if relative.parent.as_posix() not in {"brand", "custom_components/family_assistant/brand"}:
            found.append("unreviewed_image")
        return found
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [*found, "unexpected_binary"]
    for rule, pattern in RULES.items():
        if pattern.search(decoded):
            found.append(rule)
    return found


def check(root: Path = ROOT) -> list[tuple[str, str]]:
    findings = []

    def fail(error):
        raise error

    # Prune excluded build/test directories before traversing them. Playwright
    # replaces its results directory during a run; a post-traversal filter races
    # that replacement and needlessly walks dependencies. Real source I/O errors
    # must still fail the scan, never silently pass an unreadable file/tree.
    for directory, directories, files in os.walk(root, topdown=True, onerror=fail):
        directories[:] = [name for name in directories if name not in EXCLUDE]
        parent = Path(directory)
        for name in directories[:]:
            path = parent / name
            if path.is_symlink():
                findings.append((path.relative_to(root).as_posix(), "unexpected_symlink"))
                directories.remove(name)
        for name in files:
            if name in EXCLUDE:
                continue
            path = parent / name
            relative = path.relative_to(root)
            if path.is_symlink():
                findings.append((relative.as_posix(), "unexpected_symlink"))
                continue
            for rule in violations(relative, path.read_bytes()):
                findings.append((relative.as_posix(), rule))
    return findings


if __name__ == "__main__":
    findings = check()
    for path, rule in findings:
        print(f"FAIL {path}: {rule}")
    if findings:
        raise SystemExit(1)
    print("PASS: public-tree privacy checks (no matched values are printed)")
