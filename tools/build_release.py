"""Build and verify a deterministic runtime-only release candidate, never publish."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path

if __package__:
    from .check_public_tree import check, violations
else:
    from check_public_tree import check, violations

DOMAIN_PATH = Path("custom_components/family_assistant")
SUFFIXES = {".py", ".json", ".yaml", ".js", ".css", ".svg", ".png"}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?")
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
REQUIRED = {"__init__.py", "manifest.json", "strings.json", "frontend/family-assistant.js"}


def build(root: Path, expected_version: str) -> tuple[bytes, dict]:
    """Validate source, package runtime files, and read back every exact byte."""
    root = root.resolve(strict=True)
    if not VERSION.fullmatch(expected_version):
        raise ValueError("invalid_release_version")
    if check(root):
        raise ValueError("public_source_check_failed")
    component = root / DOMAIN_PATH
    if not component.is_dir() or component.is_symlink():
        raise ValueError("missing_runtime")
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("domain") != "family_assistant" or manifest.get("version") != expected_version:
        raise ValueError("release_version_mismatch")
    payloads = {}
    total = 0
    for path in sorted(component.rglob("*")):
        if path.is_symlink():
            raise ValueError("runtime_symlink")
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            continue
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix not in SUFFIXES:
            raise ValueError("unexpected_runtime_file")
        if path.stat().st_size > MAX_FILE:
            raise ValueError("runtime_file_too_large")
        content = path.read_bytes()
        total += len(content)
        if len(content) > MAX_FILE or total > MAX_TOTAL or len(payloads) >= 2000:
            raise ValueError("runtime_archive_too_large")
        if violations(relative, content):
            raise ValueError("runtime_privacy_check_failed")
        payloads[relative.as_posix()] = content
    if not {f"{DOMAIN_PATH.as_posix()}/{name}" for name in REQUIRED} <= payloads.keys():
        raise ValueError("incomplete_runtime")
    for language in ("en", "ru", "uk"):
        if f"{DOMAIN_PATH.as_posix()}/translations/{language}.json" not in payloads:
            raise ValueError("incomplete_translations")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in payloads.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    result = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if archive.namelist() != list(payloads) or archive.testzip() is not None:
            raise ValueError("archive_structure_mismatch")
        for name, content in payloads.items():
            if archive.read(name) != content:
                raise ValueError("archive_content_mismatch")
    return result, {
        "version": expected_version,
        "files": len(payloads),
        "runtime_bytes": total,
        "archive_bytes": len(result),
        "sha256": hashlib.sha256(result).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, help="Create a new ZIP; never overwrite an artifact")
    arguments = parser.parse_args()
    content, report = build(arguments.source, arguments.version)
    if arguments.output is not None:
        with arguments.output.open("xb") as target:
            target.write(content)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
