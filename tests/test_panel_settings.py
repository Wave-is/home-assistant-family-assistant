"""Control-center saves use canonical storage, revisions and side-effect fences."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain import settings
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def test_partial_save_preserves_other_policy_and_private_records(engine, now, store):
    original = engine.snapshot()
    original["settings"]["future_setting"] = {"keep": True}
    original["telegram"]["group_id"] = -999
    engine = Engine(original, store.save)
    result = await engine.execute(
        "owner",
        "settings.patch",
        {"revision": 1, "changes": {"school_preparation_time": "19:30"}},
        "school",
        now,
    )
    assert result["school_preparation_time"] == "19:30"
    assert result["future_setting"] == {"keep": True}
    assert engine.snapshot()["telegram"] == original["telegram"]
    assert engine.snapshot()["members"] == original["members"]
    assert engine.snapshot()["outbox"] == original["outbox"]
    assert Engine(store.value, store.save).snapshot() == engine.snapshot()


async def test_two_windows_cannot_overwrite_and_uncertain_retry_is_idempotent(engine, now, store):
    payload = {"revision": 1, "changes": {"name": "Edited family"}}
    receipt = await engine.execute("owner", "settings.patch", payload, "first", now)
    assert await engine.execute("owner", "settings.patch", payload, "first", now) == receipt
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "owner",
            "settings.patch",
            {"revision": 1, "changes": {"school_preparation_time": "18:30"}},
            "second",
            now,
        )
    assert settings.current_revision(engine.snapshot()) == 2
    assert store.calls == 1


async def test_native_save_invalidates_panel_revision(engine, now):
    await engine.execute(
        "owner",
        "settings.save",
        {"name": "Native edit", "language": "uk", "modules": ["tasks"]},
        "native",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "owner", "settings.patch", {"revision": 1, "changes": {"name": "Stale"}}, "stale", now
        )


async def test_module_toggle_retry_after_other_window_change_and_reload(engine, now, store):
    payload = {"revision": 1, "module": "school", "enabled": True}
    receipt = await engine.execute("owner", "settings.module_toggle", payload, "school-on", now)
    await engine.execute(
        "owner", "settings.patch", {"revision": 2, "changes": {"name": "Other edit"}}, "other", now
    )
    reloaded = Engine(store.value, store.save)
    before = reloaded.snapshot()
    assert (
        await reloaded.execute("owner", "settings.module_toggle", payload, "school-on", now)
        == receipt
    )
    assert reloaded.snapshot() == before
    with pytest.raises(DomainError, match="conflict"):
        await reloaded.execute("owner", "settings.module_toggle", payload, "stale-new-id", now)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await reloaded.execute(
            "owner", "settings.module_toggle", {**payload, "enabled": False}, "school-on", now
        )
    assert reloaded.snapshot() == before


@pytest.mark.parametrize("value", [{"module": "invented"}, {"enabled": 1}, {"revision": True}])
async def test_module_toggle_invalid_fields_are_atomic(engine, now, value):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "owner",
            "settings.module_toggle",
            {"revision": 1, "module": "school", "enabled": True, **value},
            "invalid-toggle",
            now,
        )
    assert engine.snapshot() == before


async def test_digest_policy_also_invalidates_old_general_settings_form(engine, now):
    from custom_components.family_assistant.domain import digest_settings

    state = engine.snapshot()
    values = digest_settings.values(state)
    values["digest_morning_enabled"] = not values["digest_morning_enabled"]
    await engine.execute(
        "owner",
        "settings.digest_policy",
        {
            "actor_revision": state["members"]["owner"]["revision"],
            "policy_fingerprint": digest_settings.fingerprint(state),
            **values,
        },
        "digest",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "owner",
            "settings.patch",
            {"revision": 1, "changes": {"digest_morning_enabled": False}},
            "old-form",
            now,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"revision": True, "changes": {"name": "Bad"}},
        {"revision": 1, "changes": {"token": "synthetic"}},
        {"revision": 1, "changes": {"school_preparation_days_before": True}},
        {"revision": 1, "changes": {"automatic_penalties": "yes"}},
        {"revision": 1, "changes": {"modules": ["invented"]}},
        {"revision": 1, "changes": {}},
    ],
)
async def test_bad_patch_atomic(engine, now, store, payload):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("owner", "settings.patch", payload, "bad", now)
    assert engine.snapshot() == before
    assert store.calls == 0


@pytest.mark.parametrize("actor", ["parent", "child", "guest"])
async def test_setup_and_settings_require_owner(engine, now, actor):
    for action, payload in [
        ("settings.patch", {"revision": 1, "changes": {"name": "Unapproved"}}),
        ("settings.onboarding", {"revision": 1, "step": 2}),
        ("settings.module_toggle", {"revision": 1, "module": "school", "enabled": True}),
    ]:
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(actor, action, payload, action, now)


async def test_guide_resume_has_no_activation_or_delivery(engine, now, store):
    before = engine.snapshot()
    await engine.execute(
        "owner",
        "settings.onboarding",
        {"revision": 1, "step": 3, "skipped": ["telegram"]},
        "guide",
        now,
    )
    reloaded = Engine(store.value, store.save)
    assert settings.onboarding(reloaded.snapshot()) == {
        "revision": 2,
        "step": 3,
        "completed": False,
        "skipped": ["telegram"],
    }
    for key in ("settings", "members", "outbox", "tasks", "alarm_runs", "telegram"):
        assert reloaded.snapshot()[key] == before[key]
    with pytest.raises(DomainError, match="conflict"):
        await reloaded.execute(
            "owner", "settings.onboarding", {"revision": 1, "step": 2}, "old-tab", now
        )
    await reloaded.execute(
        "owner",
        "settings.onboarding",
        {"revision": 2, "step": 4, "completed": True},
        "finished",
        now,
    )
    assert settings.onboarding(Engine(store.value, store.save).snapshot())["completed"] is True


async def test_module_disable_preserves_data_and_reenable_does_not_enable_penalties(engine, now):
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Read a chapter", "assignee": "child"}, "task", now
    )
    before = engine.snapshot()
    await engine.execute(
        "owner", "settings.patch", {"revision": 1, "changes": {"modules": []}}, "off", now
    )
    assert engine.snapshot()["tasks"][task["id"]] == task
    await engine.execute(
        "owner",
        "settings.patch",
        {"revision": 2, "changes": {"modules": before["settings"]["modules"]}},
        "on",
        now,
    )
    assert engine.snapshot()["settings"]["automatic_penalties"] is False


async def test_optional_profile_is_preserved_by_old_editor_and_explicitly_clearable(engine, now):
    original = deepcopy(engine.snapshot()["members"]["child"])
    changed = await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": original["revision"],
            "name": "Junior",
            "role": "child",
            "birth_date": "2015-02-03",
            "avatar": "robot",
        },
        "profile",
        now,
    )
    result = await engine.execute(
        "owner",
        "members.save",
        {"id": "child", "revision": changed["revision"], "name": "Junior", "role": "child"},
        "old-editor",
        now,
    )
    assert result["birth_date"] == "2015-02-03" and result["avatar"] == "robot"
    assert result["ha_user_id"] == original["ha_user_id"]
    cleared = await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": result["revision"],
            "name": "Junior",
            "role": "child",
            "birth_date": None,
            "avatar": None,
        },
        "clear-profile",
        now,
    )
    assert cleared["birth_date"] is None and cleared["avatar"] is None


@pytest.mark.parametrize(
    "profile",
    [
        {"birth_date": "2099-01-01"},
        {"birth_date": "2015-02-30"},
        {"birth_date": True},
        {"avatar": "https://example.org/photo.png"},
    ],
)
async def test_invalid_profile_does_not_change_member(engine, now, profile):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner",
            "members.save",
            {"id": "child", "revision": 1, "name": "Junior", "role": "child", **profile},
            "invalid-profile",
            now,
        )
    assert engine.snapshot() == before


async def test_resumed_profile_draft_is_rejected_after_remote_edit_and_store_reload(
    engine, now, store
):
    """A browser's retained revision cannot rebase aliases or account links on a newer member."""
    member = engine.snapshot()["members"]["child"]
    draft = {
        "id": "child",
        "revision": member["revision"],
        "name": "Unfinished profile",
        "role": "child",
        "language": "uk",
        "aliases": ["Sunny"],
        "active": True,
        "ha_user_id": member["ha_user_id"],
        "birth_date": None,
        "avatar": "star",
    }
    await engine.execute(
        "owner", "members.save", {**draft, "name": "Other window"}, "remote-profile", now
    )
    reloaded = Engine(store.value, store.save)
    before = reloaded.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await reloaded.execute("owner", "members.save", draft, "resumed-draft", now)
    assert reloaded.snapshot() == before


async def test_resumed_profile_creation_requires_current_owner_after_store_reload(
    engine, now, store
):
    """Even a well-formed locally retained creation cannot restore revoked authority."""
    snapshot = engine.snapshot()
    snapshot["members"]["parent"]["role"] = "owner"
    snapshot["members"]["owner"]["role"] = "parent"
    await store.save(snapshot)
    reloaded = Engine(store.value, store.save)
    before = reloaded.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await reloaded.execute(
            "owner",
            "members.save",
            {"name": "Local new member", "role": "child", "language": "en"},
            "resumed-creation",
            now,
        )
    assert reloaded.snapshot() == before
