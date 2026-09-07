"""Synthetic runtime packaging tests; no private source or release publication."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from tools.build_release import DOMAIN_PATH, build


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
