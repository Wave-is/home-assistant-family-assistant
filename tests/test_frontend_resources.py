from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.family_assistant.frontend_resources import (
    FRONTEND_URL_ROOT,
    LEGACY_RESOURCE_URL,
    OWNERSHIP_QUERY,
    frontend_fingerprint,
    owned_fingerprint,
    plan_resource_mutation,
    prepare_frontend_resource,
)


def test_content_address_covers_paths_and_all_javascript(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text('import "./view.js";', encoding="utf-8")
    (frontend / "view.js").write_text("export const view = 1;", encoding="utf-8")
    first = frontend_fingerprint(frontend)

    (frontend / "ignored.txt").write_text("not loaded", encoding="utf-8")
    assert frontend_fingerprint(frontend) == first
    (frontend / "view.js").write_text("export const view = 2;", encoding="utf-8")
    assert frontend_fingerprint(frontend) != first

    content_hash = frontend_fingerprint(frontend)
    (frontend / "view.js").rename(frontend / "renamed.js")
    assert frontend_fingerprint(frontend) != content_hash


def test_registration_versions_the_complete_import_namespace(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)

    assert len(resource.fingerprint) == 64
    assert resource.resource_url == (
        f"{FRONTEND_URL_ROOT}/{resource.fingerprint}/family-assistant.js?{OWNERSHIP_QUERY}"
    )
    assert resource.static_paths[0].url_path == f"{FRONTEND_URL_ROOT}/{resource.fingerprint}"
    assert resource.static_paths[0].cache_headers is True
    assert resource.static_paths[1].url_path == FRONTEND_URL_ROOT
    assert resource.static_paths[1].cache_headers is False


def test_only_exact_local_marker_is_owned(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)
    fingerprint = resource.fingerprint

    assert owned_fingerprint(resource.resource_url) == fingerprint
    assert owned_fingerprint(resource.resource_url + "&extra=1") is None
    assert owned_fingerprint(resource.resource_url.replace("=1", "=true")) is None
    assert owned_fingerprint("https://example.invalid" + resource.resource_url) is None
    assert owned_fingerprint(LEGACY_RESOURCE_URL + "?" + OWNERSHIP_QUERY) is None
    assert owned_fingerprint(None) is None


def test_mutation_is_idempotent_and_updates_only_owned_record(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)
    unrelated = {"id": "other", "type": "module", "url": "/local/other.js"}

    assert plan_resource_mutation([unrelated], resource.resource_url).kind == "create"
    current = {"id": "ours", "type": "module", "url": resource.resource_url}
    mutation = plan_resource_mutation([unrelated, current], resource.resource_url)
    assert mutation.kind == "current" and mutation.item_id == "ours"

    old_url = resource.resource_url.replace(resource.fingerprint, "0" * 64)
    old = {"id": "ours", "type": "module", "url": old_url}
    mutation = plan_resource_mutation([unrelated, old], resource.resource_url)
    assert mutation.kind == "update" and mutation.item_id == "ours"

    wrong_type = replace(resource, resource_url=resource.resource_url).resource_url
    mutation = plan_resource_mutation(
        [{"id": "ours", "type": "css", "url": wrong_type}], resource.resource_url
    )
    assert mutation.kind == "update" and mutation.item_id == "ours"


def test_manual_and_duplicate_owned_resources_fail_closed(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)
    owned = {"id": "ours", "type": "module", "url": resource.resource_url}

    manual = {"id": "manual", "type": "module", "url": LEGACY_RESOURCE_URL}
    assert plan_resource_mutation([manual], resource.resource_url).kind == "manual_conflict"
    manual_versioned = {
        "id": "manual-versioned",
        "type": "module",
        "url": resource.resource_url.partition("?")[0] + "?v=manual",
    }
    assert (
        plan_resource_mutation([owned, manual_versioned], resource.resource_url).kind
        == "manual_conflict"
    )
    assert plan_resource_mutation([owned, dict(owned)], resource.resource_url).kind == (
        "owned_conflict"
    )
    malformed = {"type": "module", "url": resource.resource_url}
    assert plan_resource_mutation([malformed], resource.resource_url).kind == "owned_conflict"
    assert plan_resource_mutation([{}, {"url": None}], resource.resource_url).kind == "create"


def test_invalid_urls_are_not_mistaken_for_owned_records(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)

    invalid = [
        {"id": "number", "type": "module", "url": 7},
        {"id": "scheme", "type": "module", "url": "javascript:alert(1)"},
        {
            "id": "encoded",
            "type": "module",
            "url": "/family_assistant/frontend/%2e%2e/family-assistant.js",
        },
        {
            "id": "uppercase",
            "type": "module",
            "url": resource.resource_url.replace(
                resource.fingerprint, resource.fingerprint.upper()
            ),
        },
    ]
    assert plan_resource_mutation(invalid, resource.resource_url).kind == "create"


def test_same_asset_path_with_foreign_url_shape_is_manual_conflict(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "family-assistant.js").write_text("export {};", encoding="utf-8")
    resource = prepare_frontend_resource(frontend)
    path = resource.resource_url.partition("?")[0]

    for url in (
        f"{path}?v=manual",
        f"{resource.resource_url}#changed",
        f"https://ha.invalid{path}?v=manual",
    ):
        assert (
            plan_resource_mutation(
                [{"id": "manual", "type": "module", "url": url}], resource.resource_url
            ).kind
            == "manual_conflict"
        )


def test_missing_or_symlinked_javascript_is_rejected(tmp_path: Path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    with pytest.raises(RuntimeError, match="frontend_missing"):
        frontend_fingerprint(frontend)

    target = tmp_path / "outside.js"
    target.write_text("export {};", encoding="utf-8")
    link = frontend / "family-assistant.js"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this test host")
    with pytest.raises(RuntimeError, match="frontend_invalid_path"):
        frontend_fingerprint(frontend)
