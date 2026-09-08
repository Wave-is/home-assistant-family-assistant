"""Packaging, localization and privacy invariants for the public repository."""

import ast
import json
import os
from pathlib import Path

import pytest

from tools.check_public_tree import check, violations

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"


def leaves(value, prefix=""):
    if isinstance(value, dict):
        return {path for key, child in value.items() for path in leaves(child, f"{prefix}/{key}")}
    return {prefix}


def test_complete_matching_translation_shapes():
    base = json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))
    for language in ("en", "ru", "uk"):
        translation = json.loads(
            (PACKAGE / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        assert leaves(translation) == leaves(base)
        if language == "en":
            assert translation == base


def test_every_domain_error_is_translated():
    errors = json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))["exceptions"]
    codes = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "DomainError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                codes.add(node.args[0].value)
    assert codes <= errors.keys(), codes - errors.keys()


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
def test_copy_wizard_abort_reasons_and_discard_labels_are_in_native_options_sections(language):
    translation = json.loads(
        (PACKAGE / "translations" / f"{language}.json").read_text(encoding="utf-8")
    )["options"]
    tree = ast.parse((PACKAGE / "migration" / "copy_flow.py").read_text(encoding="utf-8"))
    reasons = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "_abort" and len(node.args) > 1:
            if isinstance(node.args[1], ast.Constant):
                reasons.add(node.args[1].value)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "async_abort":
            reasons.update(
                keyword.value.value
                for keyword in node.keywords
                if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant)
            )
    assert "migration_copy_cancelled" in reasons
    assert reasons <= translation["abort"].keys()
    for step in ("legacy_copy_matches", "legacy_copy_review"):
        assert translation["step"][step]["data"]["discard_review"]


def test_hacs_single_domain_and_self_contained_runtime():
    domains = [
        p.name
        for p in (ROOT / "custom_components").iterdir()
        if p.is_dir() and p.name != "__pycache__"
    ]
    assert domains == ["family_assistant"]
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "family_assistant"
    assert manifest["config_flow"] is True
    assert (ROOT / "brand" / "icon.png").is_file()
    assert (PACKAGE / "brand" / "icon.png").read_bytes() == (
        ROOT / "brand" / "icon.png"
    ).read_bytes()


def test_public_tree_has_no_private_files_or_credentials():
    assert check() == []


def test_scanner_prunes_excluded_test_output_before_traversal(tmp_path, monkeypatch):
    excluded = tmp_path / "test-results"
    excluded.mkdir()
    (tmp_path / "example.txt").write_text("public", encoding="utf-8")
    original = os.scandir

    def guarded(path):
        assert Path(path) != excluded, "scanner traversed replaceable test output"
        return original(path)

    monkeypatch.setattr(os, "scandir", guarded)
    assert check(tmp_path) == []


def test_scanner_does_not_ignore_source_traversal_errors(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    original = os.scandir

    def guarded(path):
        if Path(path) == source:
            raise PermissionError("synthetic unreadable source")
        return original(path)

    monkeypatch.setattr(os, "scandir", guarded)
    with pytest.raises(PermissionError):
        check(tmp_path)


def test_scanner_detects_synthetic_secret_and_private_path_without_echo():
    token = "1" * 8 + ":" + "x" * 35
    assert "telegram_token" in violations(Path("example.txt"), token.encode())
    assert "private_file" in violations(Path(".local/test.txt"), b"synthetic")
    assert "private_file" in violations(Path("history.db"), b"synthetic")


def test_scanner_rejects_private_media_even_when_content_is_empty_or_text():
    for path in (
        "family_assistant_data/entry/upload",
        "custom_components/family_assistant/family_assistant_data/entry/file",
        ".upload-synthetic",
        "custom_components/family_assistant/" + "a" * 64,
        "synthetic.webp",
        "synthetic.heic",
    ):
        assert "private_file" in violations(Path(path), b"")
    assert violations(Path("brand/icon.png"), b"synthetic") == []
