"""Synthetic runtime packaging tests; no private source or release publication."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from tools import build_release
from tools.build_release import DOMAIN_PATH, build


def test_ci_release_candidate_matches_current_manifest():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / DOMAIN_PATH / "manifest.json").read_text(encoding="utf-8"))
    workflow = (root / ".github/workflows/checks.yml").read_text(encoding="utf-8")
    versions = re.findall(r"run: python tools/build_release\.py --version ([^\s]+)", workflow)
    assert versions == [manifest["version"]]


def test_native_ollama_is_optional_but_declared_for_import_and_startup_order():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / DOMAIN_PATH / "manifest.json").read_text(encoding="utf-8"))
    assert "ollama" in manifest["after_dependencies"]
    assert "ollama" not in manifest["dependencies"]


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "public"
    runtime = root / DOMAIN_PATH
    (runtime / "frontend").mkdir(parents=True)
    (runtime / "translations").mkdir()
    files = {
        "__init__.py": '"""Synthetic runtime."""',
        "manifest.json": json.dumps({"domain": "family_assistant", "version": "1.2.3-beta.1"}),
        "strings.json": "{}",
        "frontend/family-assistant.js": 'import "./child.js";',
        "frontend/child.js": "export const child = true;",
        **{f"translations/{lang}.json": "{}" for lang in ("en", "ru", "uk")},
    }
    for name, content in files.items():
        (runtime / name).write_text(content, encoding="utf-8")
    (root / "README.md").write_text("Development source", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "fixture.py").write_text("assert True", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignored.txt").write_text("not runtime", encoding="utf-8")
    return root


def test_archive_is_deterministic_exact_runtime_only_and_complete_graph(source):
    first, report = build(source, "1.2.3-beta.1")
    second, second_report = build(source, "1.2.3-beta.1")
    assert first == second and report == second_report
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith(DOMAIN_PATH.as_posix() + "/") for name in names)
        assert f"{DOMAIN_PATH.as_posix()}/frontend/child.js" in names
        assert len(names) == report["files"] == 8
        for name in names:
            assert archive.read(name) == (source / name).read_bytes()
            assert archive.getinfo(name).date_time == (1980, 1, 1, 0, 0, 0)


def test_compilation_cache_is_never_packaged(source):
    cache = source / DOMAIN_PATH / "__pycache__"
    cache.mkdir()
    (cache / "compiled.pyc").write_bytes(b"\xffcache")
    content, _ = build(source, "1.2.3-beta.1")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert not any("__pycache__" in name for name in archive.namelist())


@pytest.mark.parametrize("version", ["1.2.4", "../1.2.3", "1.2", ""])
def test_bad_or_mismatched_version_fails(source, version):
    with pytest.raises(ValueError):
        build(source, version)


@pytest.mark.parametrize("name", ["secrets.yaml", ".env", "unknown.txt", "backup.zip"])
def test_private_or_unknown_runtime_file_blocks_package(source, name):
    (source / DOMAIN_PATH / name).write_text("synthetic", encoding="utf-8")
    with pytest.raises(ValueError):
        build(source, "1.2.3-beta.1")


def test_private_source_outside_runtime_also_blocks_publication(source):
    (source / ".local").mkdir()
    (source / ".local" / "private.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="public_source_check_failed"):
        build(source, "1.2.3-beta.1")


def test_missing_language_blocks_package(source):
    (source / DOMAIN_PATH / "translations" / "uk.json").unlink()
    with pytest.raises(ValueError, match="incomplete_translations"):
        build(source, "1.2.3-beta.1")


def test_missing_relative_python_import_blocks_package(source):
    (source / DOMAIN_PATH / "__init__.py").write_text(
        "from .missing_runtime_module import value\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="incomplete_runtime"):
        build(source, "1.2.3-beta.1")


def test_missing_relative_javascript_import_blocks_package(source):
    (source / DOMAIN_PATH / "frontend" / "family-assistant.js").write_text(
        'import "./missing-runtime-module.js";\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="incomplete_runtime"):
        build(source, "1.2.3-beta.1")


@pytest.mark.parametrize("keyword", ["import", "export"])
def test_multiline_javascript_import_is_checked(source, keyword):
    main = source / DOMAIN_PATH / "frontend" / "family-assistant.js"
    declaration = keyword + ' {\n  child,\n} from "./child.js";\n'
    main.write_text(declaration, encoding="utf-8")
    build(source, "1.2.3-beta.1")
    main.write_text(declaration.replace("./child.js", "./missing.js"), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete_runtime"):
        build(source, "1.2.3-beta.1")


def test_manifest_is_validated_from_the_captured_archive_bytes(source, monkeypatch):
    original = build_release._read_stable

    def capture(path, expected, component):
        content = original(path, expected, component)
        if path.name == "manifest.json":
            return json.dumps({"domain": "family_assistant", "version": "9.9.9"}).encode()
        return content

    monkeypatch.setattr(build_release, "_read_stable", capture)
    with pytest.raises(ValueError, match="release_version_mismatch"):
        build(source, "1.2.3-beta.1")


def test_file_change_between_inventory_and_capture_fails_closed(source, monkeypatch):
    original = build_release._read_stable
    manifest = source / DOMAIN_PATH / "manifest.json"
    changed = False

    def capture(path, expected, component):
        nonlocal changed
        if path == manifest and not changed:
            changed = True
            path.write_text('{"domain":"family_assistant","version":"0"}', encoding="utf-8")
        return original(path, expected, component)

    monkeypatch.setattr(build_release, "_read_stable", capture)
    with pytest.raises(ValueError, match="runtime_changed"):
        build(source, "1.2.3-beta.1")


def test_file_added_after_initial_inventory_fails_closed(source, monkeypatch):
    original = build_release._runtime_inventory
    calls = 0

    def inventory(root, component):
        nonlocal calls
        result = original(root, component)
        calls += 1
        if calls == 1:
            (component / "late.py").write_text("value = True\n", encoding="utf-8")
        return result

    monkeypatch.setattr(build_release, "_runtime_inventory", inventory)
    with pytest.raises(ValueError, match="runtime_changed"):
        build(source, "1.2.3-beta.1")


def test_runtime_directory_symlink_is_rejected_without_traversal(source, tmp_path):
    outside = tmp_path / "outside-symlink"
    outside.mkdir()
    (outside / "private.py").write_text("secret = True\n", encoding="utf-8")
    link = source / DOMAIN_PATH / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(ValueError, match="runtime_symlink"):
        build(source, "1.2.3-beta.1")


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction regression")
def test_windows_runtime_junction_is_rejected_without_traversal(source, tmp_path):
    outside = tmp_path / "outside-junction"
    outside.mkdir()
    (outside / "private.py").write_text("secret = True\n", encoding="utf-8")
    junction = source / DOMAIN_PATH / "junction"
    command = shutil.which("cmd.exe")
    if command is None:
        pytest.skip("cmd.exe is unavailable")
    created = subprocess.run(  # noqa: S603 -- fixed executable and synthetic paths
        [command, "/d", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        check=False,
    )
    if created.returncode:
        pytest.skip("directory junctions are unavailable")
    try:
        with pytest.raises(ValueError, match="runtime_symlink"):
            build(source, "1.2.3-beta.1")
    finally:
        os.rmdir(junction)
