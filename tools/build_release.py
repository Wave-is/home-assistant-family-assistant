"""Build and verify a deterministic runtime-only release candidate, never publish."""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import posixpath
import re
import stat
import zipfile
from pathlib import Path

if __package__:
    from .check_public_tree import EXCLUDE, check, violations
else:
    from check_public_tree import EXCLUDE, check, violations

DOMAIN_PATH = Path("custom_components/family_assistant")
SUFFIXES = {".py", ".json", ".yaml", ".js", ".css", ".svg", ".png"}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?")
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
REQUIRED = {"__init__.py", "manifest.json", "strings.json", "frontend/family-assistant.js"}
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
JS_IMPORTS = (
    re.compile(r"""(?m)^[ \t]*import\s+(?:[^;]*?\s+from\s+)?["'](\.[^"']+)["']"""),
    re.compile(r"""(?m)^[ \t]*export\s+[^;]*?\s+from\s+["'](\.[^"']+)["']"""),
    re.compile(r"""\bimport\s*\(\s*["'](\.[^"']+)["']\s*\)"""),
)


def _stamp(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        getattr(value, "st_file_attributes", 0),
    )


def _reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0) & REPARSE_POINT
    )


def _within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _guard_source_tree(root: Path) -> None:
    """Reject traversable links, including Windows junctions, before public checks."""
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise ValueError("public_source_check_failed") from error
        for entry in entries:
            if entry.name in EXCLUDE:
                continue
            path = Path(entry.path)
            try:
                value = os.stat(path, follow_symlinks=False)
            except OSError as error:
                raise ValueError("public_source_check_failed") from error
            if _reparse(value):
                relative = path.relative_to(root)
                if relative.parts[: len(DOMAIN_PATH.parts)] == DOMAIN_PATH.parts:
                    raise ValueError("runtime_symlink")
                raise ValueError("public_source_check_failed")
            if stat.S_ISDIR(value.st_mode):
                pending.append(path)


def _runtime_inventory(root: Path, component: Path) -> dict[str, tuple[Path, tuple[int, ...]]]:
    """Take a canonical, containment-checked inventory without following links."""
    inventory: dict[str, tuple[Path, tuple[int, ...]]] = {}
    folded: dict[str, str] = {}
    pending = [component]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            raise ValueError("runtime_changed") from error
        for entry in entries:
            path = Path(entry.path)
            if entry.name == "__pycache__":
                continue
            try:
                value = os.stat(path, follow_symlinks=False)
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise ValueError("runtime_changed") from error
            if _reparse(value) or not _within(resolved, component):
                raise ValueError("runtime_symlink")
            if stat.S_ISDIR(value.st_mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(value.st_mode) or path.suffix not in SUFFIXES:
                raise ValueError("unexpected_runtime_file")
            if value.st_size > MAX_FILE:
                raise ValueError("runtime_file_too_large")
            name = path.relative_to(root).as_posix()
            collision = folded.setdefault(name.casefold(), name)
            if collision != name:
                raise ValueError("unexpected_runtime_file")
            if len(inventory) >= 2000:
                raise ValueError("runtime_archive_too_large")
            inventory[name] = (path, _stamp(value))
    return dict(sorted(inventory.items()))


def _read_stable(path: Path, expected: tuple[int, ...], component: Path) -> bytes:
    """Capture one regular file and prove its identity did not change while read."""
    try:
        before = os.stat(path, follow_symlinks=False)
        resolved_before = path.resolve(strict=True)
        if _reparse(before) or not stat.S_ISREG(before.st_mode):
            raise ValueError("runtime_changed")
        if _stamp(before) != expected or not _within(resolved_before, component):
            raise ValueError("runtime_changed")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if _stamp(opened) != expected or _reparse(opened):
                raise ValueError("runtime_changed")
            content = stream.read(MAX_FILE + 1)
            finished = os.fstat(stream.fileno())
        after = os.stat(path, follow_symlinks=False)
        resolved_after = path.resolve(strict=True)
    except ValueError:
        raise
    except OSError as error:
        raise ValueError("runtime_changed") from error
    if len(content) > MAX_FILE:
        raise ValueError("runtime_file_too_large")
    if (
        _stamp(opened) != _stamp(finished)
        or _stamp(after) != expected
        or _reparse(after)
        or resolved_after != resolved_before
        or not _within(resolved_after, component)
    ):
        raise ValueError("runtime_changed")
    return content


def _python_target(
    relative: str, module: str | None, level: int, alias: str | None = None
) -> str | None:
    package = list(Path(relative).parent.parts)
    upward = level - 1
    if upward > len(package):
        return None
    if upward:
        package = package[:-upward]
    if module:
        package.extend(module.split("."))
    elif alias and alias != "*":
        package.append(alias)
    return "/".join(package)


def _module_present(target: str | None, runtime_names: set[str]) -> bool:
    if target is None:
        return False
    return f"{target}.py" in runtime_names or f"{target}/__init__.py" in runtime_names


def _validate_python_imports(relative: str, content: bytes, runtime_names: set[str]) -> None:
    try:
        tree = ast.parse(content, filename=relative)
    except (SyntaxError, ValueError) as error:
        raise ValueError("incomplete_runtime") from error
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            if node.module:
                targets = [_python_target(relative, node.module, node.level)]
            else:
                targets = [
                    _python_target(relative, None, node.level, alias.name) for alias in node.names
                ]
        elif node.module and node.module.startswith("custom_components.family_assistant"):
            suffix = node.module.removeprefix("custom_components.family_assistant").lstrip(".")
            targets = [suffix.replace(".", "/")]
        else:
            continue
        if any(not _module_present(target, runtime_names) for target in targets):
            raise ValueError("incomplete_runtime")


def _validate_javascript_imports(relative: str, content: bytes, runtime_names: set[str]) -> None:
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("incomplete_runtime") from error
    directory = posixpath.dirname(relative)
    for pattern in JS_IMPORTS:
        for match in pattern.finditer(source):
            specifier = match.group(1)
            if "\\" in specifier or "?" in specifier or "#" in specifier:
                raise ValueError("incomplete_runtime")
            target = posixpath.normpath(posixpath.join(directory, specifier))
            if target == ".." or target.startswith("../") or target not in runtime_names:
                raise ValueError("incomplete_runtime")


def _validate_imports(payloads: dict[str, bytes]) -> None:
    prefix = f"{DOMAIN_PATH.as_posix()}/"
    runtime_names = {name.removeprefix(prefix) for name in payloads}
    for name, content in payloads.items():
        relative = name.removeprefix(prefix)
        if name.endswith(".py"):
            _validate_python_imports(relative, content, runtime_names)
        elif name.endswith(".js"):
            _validate_javascript_imports(relative, content, runtime_names)


def build(root: Path, expected_version: str) -> tuple[bytes, dict]:
    """Validate source, package runtime files, and read back every exact byte."""
    root = root.resolve(strict=True)
    if not VERSION.fullmatch(expected_version):
        raise ValueError("invalid_release_version")
    _guard_source_tree(root)
    if check(root):
        raise ValueError("public_source_check_failed")
    component = root / DOMAIN_PATH
    if not component.is_dir():
        raise ValueError("missing_runtime")
    component = component.resolve(strict=True)
    if not _within(component, root):
        raise ValueError("runtime_symlink")
    inventory = _runtime_inventory(root, component)
    payloads: dict[str, bytes] = {}
    total = 0
    for name, (path, expected) in inventory.items():
        content = _read_stable(path, expected, component)
        total += len(content)
        if total > MAX_TOTAL:
            raise ValueError("runtime_archive_too_large")
        if violations(Path(name), content):
            raise ValueError("runtime_privacy_check_failed")
        payloads[name] = content
    if _runtime_inventory(root, component) != inventory:
        raise ValueError("runtime_changed")
    if not {f"{DOMAIN_PATH.as_posix()}/{name}" for name in REQUIRED} <= payloads.keys():
        raise ValueError("incomplete_runtime")
    for language in ("en", "ru", "uk"):
        if f"{DOMAIN_PATH.as_posix()}/translations/{language}.json" not in payloads:
            raise ValueError("incomplete_translations")
    manifest_name = f"{DOMAIN_PATH.as_posix()}/manifest.json"
    try:
        manifest = json.loads(payloads[manifest_name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("release_version_mismatch") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("domain") != "family_assistant"
        or manifest.get("version") != expected_version
    ):
        raise ValueError("release_version_mismatch")
    _validate_imports(payloads)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            content = payloads[name]
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    result = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        if archive.namelist() != sorted(payloads) or archive.testzip() is not None:
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
