"""Dietary profiles through the real Engine privacy and replay boundaries."""

import asyncio
import json

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.context import result_refs
from custom_components.family_assistant.telegram.router import route

CANARY = "DIETARY-CANARY-PRIVATE-7c09"
INVALID_REVISIONS = [None, True, False, 1.0, "1", 0, -1, 2**53]


@pytest.fixture
def dietary_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("pantry")
    return Engine(state, store.save)


def content(*, note=CANARY, likes=None, dislikes=None, avoid=None):
    return {
        "likes": ["Synthetic apples"] if likes is None else likes,
        "dislikes": ["Synthetic pears"] if dislikes is None else dislikes,
        "avoid": ["Synthetic sesame"] if avoid is None else avoid,
        "allergy_note": note,
    }


async def save_profile(
    engine, now, actor="adult", member_id=None, operation="dietary-save", **changes
):
    note = changes.pop("note", CANARY)
    payload = {"member_id": member_id or actor, **content(note=note)}
    payload.update(changes)
    return await engine.execute(actor, "pantry.dietary_save", payload, operation, now)


def profiles(engine):
    return engine.snapshot()["dietary_profiles"]


def dietary_view(engine, actor, now):
    return engine.view(actor, now=now)["pantry"]["dietary_profiles"]


def access_payload(engine, revision, allowed, member_id="adult"):
    return {
        "member_id": member_id,
        "revision": revision,
        "member_revision": engine.snapshot()["members"][member_id]["revision"],
        "share_with_parents": allowed,
    }


def assert_no_write(engine, store, before, writes):
    assert engine.snapshot() == before
    assert store.calls == writes


async def change_role(engine, now, member_id, role, operation, *, active=True):
    member = engine.snapshot()["members"][member_id]
    return await engine.execute(
        "owner",
        "members.save",
        {
            "id": member_id,
            "revision": member["revision"],
            "name": member["name"],
            "role": role,
            "language": member["language"],
            "active": active,
        },
        operation,
        now,
    )


@pytest.mark.asyncio
async def test_adult_roles_self_manage_with_opaque_receipts_and_current_projection(
    dietary_engine, now
):
    operations = []
    for actor in ("owner", "parent", "adult"):
        create_operation = f"self-{actor}"
        receipt = await save_profile(
            dietary_engine,
            now,
            actor,
            operation=create_operation,
            note=f"{CANARY}-{actor}",
        )
        operations.append(create_operation)
        assert receipt == {"member_id": actor, "revision": 1, "status": "active"}
        edit_operation = f"edit-self-{actor}"
        receipt = await save_profile(
            dietary_engine,
            now,
            actor,
            revision=receipt["revision"],
            operation=edit_operation,
            note=f"{CANARY}-{actor}-edited",
        )
        operations.append(edit_operation)
        assert receipt == {"member_id": actor, "revision": 2, "status": "active"}
        row = dietary_view(dietary_engine, actor, now)["self"]
        assert row["member_id"] == actor
        assert row["management"] == "self"
        assert row["allergy_note"] == f"{CANARY}-{actor}-edited"
        assert row["can_edit"] is True and row["can_share"] is True
        assert row["share_with_parents"] is False

    state = dietary_engine.snapshot()
    audit = {item["id"]: item for item in state["audit"]}
    for operation in operations:
        assert audit[operation]["result"].keys() == {"member_id", "revision", "status"}
        assert state["processed"][operation]["result"].keys() == {
            "member_id",
            "revision",
            "status",
        }
    assert state["outbox"] == {}


@pytest.mark.asyncio
async def test_adult_note_is_hidden_until_fresh_subject_consent(dietary_engine, now):
    created = await save_profile(dietary_engine, now)
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"] == []

    shared = await dietary_engine.execute(
        "adult",
        "pantry.dietary_access_set",
        access_payload(dietary_engine, created["revision"], True),
        "share-adult",
        now,
    )
    assert shared == {"member_id": "adult", "revision": 2, "status": "active"}
    for parent in ("owner", "parent"):
        [row] = dietary_view(dietary_engine, parent, now)["shared_adults"]
        assert row["allergy_note"] == CANARY
        assert row["share_with_parents"] is True
        assert row["can_edit"] is False and row["can_share"] is False

    hidden = await dietary_engine.execute(
        "adult",
        "pantry.dietary_access_set",
        access_payload(dietary_engine, shared["revision"], False),
        "unshare-adult",
        now,
    )
    assert hidden["revision"] == 3
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"] == []


@pytest.mark.asyncio
async def test_membership_change_after_review_rejects_first_consent_execution(
    dietary_engine, store, now
):
    created = await save_profile(dietary_engine, now)
    reviewed = access_payload(dietary_engine, created["revision"], True)
    member = dietary_engine.snapshot()["members"]["adult"]
    await dietary_engine.execute(
        "owner",
        "members.save",
        {
            "id": "adult",
            "revision": member["revision"],
            "name": "Renamed after review",
            "role": "adult",
            "language": member["language"],
        },
        "rename-after-access-review",
        now,
    )
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_access_set",
            reviewed,
            "stale-reviewed-consent",
            now,
        )
    assert_no_write(dietary_engine, store, before, writes)
    profile = profiles(dietary_engine)["adult"]
    assert profile["revision"] == created["revision"]
    assert profile["share_with_parents"] is False
    assert "consent_member_revision" not in profile


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_revision", ["missing", *INVALID_REVISIONS])
async def test_access_requires_strict_reviewed_member_revision_without_write(
    dietary_engine, store, now, bad_revision
):
    created = await save_profile(dietary_engine, now)
    payload = {
        "member_id": "adult",
        "revision": created["revision"],
        "share_with_parents": True,
    }
    if bad_revision != "missing":
        payload["member_revision"] = bad_revision
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_access_set",
            payload,
            f"bad-member-revision-{bad_revision!r}",
            now,
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
async def test_member_edit_and_role_cycle_never_resurrect_old_adult_consent(dietary_engine, now):
    created = await save_profile(dietary_engine, now)
    initial_access = access_payload(dietary_engine, created["revision"], True)
    shared = await dietary_engine.execute(
        "adult",
        "pantry.dietary_access_set",
        initial_access,
        "initial-consent",
        now,
    )
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"]
    raw = profiles(dietary_engine)["adult"]
    assert "consent_member_revision" in raw
    assert "consent_member_revision" not in json.dumps(dietary_view(dietary_engine, "adult", now))
    assert "consent_member_revision" not in json.dumps(shared)

    member = dietary_engine.snapshot()["members"]["adult"]
    await dietary_engine.execute(
        "owner",
        "members.save",
        {
            "id": "adult",
            "revision": member["revision"],
            "name": "Renamed adult",
            "role": "adult",
            "language": member["language"],
        },
        "rename-adult",
        now,
    )
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"] == []
    before = dietary_engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_access_set",
            initial_access,
            "initial-consent",
            now,
        )
    assert dietary_engine.snapshot() == before
    saved = await save_profile(
        dietary_engine,
        now,
        revision=shared["revision"],
        note="AFTER-RENAME",
        operation="save-after-rename",
    )
    assert saved["revision"] == 3
    assert profiles(dietary_engine)["adult"]["share_with_parents"] is False
    assert "consent_member_revision" not in profiles(dietary_engine)["adult"]

    renewed_access = access_payload(dietary_engine, saved["revision"], True)
    consented_again = await dietary_engine.execute(
        "adult",
        "pantry.dietary_access_set",
        renewed_access,
        "consent-again",
        now,
    )
    assert consented_again["revision"] == 4
    await change_role(dietary_engine, now, "adult", "child", "adult-to-child")
    await change_role(dietary_engine, now, "adult", "adult", "child-to-adult")
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"] == []
    assert dietary_view(dietary_engine, "adult", now)["self"]["share_with_parents"] is False
    before = dietary_engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_access_set",
            renewed_access,
            "consent-again",
            now,
        )
    assert dietary_engine.snapshot() == before


@pytest.mark.asyncio
async def test_parent_manages_only_current_child_parent_origin_and_promotion_revokes_replay(
    dietary_engine, store, now
):
    payload = {"member_id": "child", **content(note="CHILD-PARENT-CANARY")}
    created = await dietary_engine.execute(
        "parent", "pantry.dietary_save", payload, "parent-child-save", now
    )
    managed = next(
        row
        for row in dietary_view(dietary_engine, "parent", now)["managed_children"]
        if row["member_id"] == "child"
    )
    assert managed["member_id"] == "child"
    assert managed["management"] == "parent_child"
    assert managed["can_edit"] is True and managed["can_share"] is False
    child_self = dietary_view(dietary_engine, "child", now)["self"]
    assert child_self["allergy_note"] == "CHILD-PARENT-CANARY"
    assert child_self["can_edit"] is False and child_self["can_share"] is False

    await change_role(dietary_engine, now, "child", "adult", "promote-child")
    managed = dietary_view(dietary_engine, "parent", now)["managed_children"]
    assert all(row["member_id"] != "adult" for row in managed)
    promoted = dietary_view(dietary_engine, "child", now)["self"]
    assert promoted["allergy_note"] == "CHILD-PARENT-CANARY"
    assert promoted["can_edit"] is True and promoted["can_share"] is True
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="forbidden"):
        await dietary_engine.execute(
            "parent", "pantry.dietary_save", payload, "parent-child-save", now
        )
    assert_no_write(dietary_engine, store, before, writes)

    claimed = await dietary_engine.execute(
        "child",
        "pantry.dietary_save",
        {
            "member_id": "child",
            "revision": created["revision"],
            **content(note="PROMOTED-SELF-CANARY"),
        },
        "promoted-claims-profile",
        now,
    )
    stored = profiles(dietary_engine)["child"]
    assert claimed["revision"] == 2 and stored["management"] == "self"
    assert stored["share_with_parents"] is False


@pytest.mark.asyncio
async def test_demoted_self_origin_profile_stays_private_and_read_only(dietary_engine, now):
    await save_profile(dietary_engine, now)
    await change_role(dietary_engine, now, "adult", "child", "demote-adult")
    child_view = dietary_view(dietary_engine, "adult", now)
    assert child_view["self"]["allergy_note"] == CANARY
    assert child_view["self"]["can_edit"] is False
    managed = dietary_view(dietary_engine, "parent", now)["managed_children"]
    assert all(row["member_id"] != "adult" for row in managed)
    assert dietary_view(dietary_engine, "parent", now)["shared_adults"] == []


@pytest.mark.asyncio
async def test_clear_is_content_free_and_reopen_requires_tombstone_revision(
    dietary_engine, store, now
):
    created = await save_profile(dietary_engine, now)
    shared = await dietary_engine.execute(
        "adult",
        "pantry.dietary_access_set",
        access_payload(dietary_engine, created["revision"], True),
        "share-before-clear",
        now,
    )
    cleared = await dietary_engine.execute(
        "adult",
        "pantry.dietary_clear",
        {"member_id": "adult", "revision": shared["revision"]},
        "clear-profile",
        now,
    )
    assert cleared == {"member_id": "adult", "revision": 3, "status": "cleared"}
    tombstone = profiles(dietary_engine)["adult"]
    assert set(tombstone) == {"member_id", "management", "revision", "status", "updated_at"}
    assert CANARY not in json.dumps(tombstone)
    self_stub = dietary_view(dietary_engine, "adult", now)["self"]
    assert self_stub["status"] == "cleared" and self_stub["revision"] == 3
    assert CANARY not in json.dumps(self_stub)

    before, writes = dietary_engine.snapshot(), store.calls
    for payload in (
        {"member_id": "adult", **content(note="NO-ABA")},
        {"member_id": "adult", "revision": created["revision"], **content(note="STALE")},
    ):
        with pytest.raises(DomainError):
            await dietary_engine.execute(
                "adult", "pantry.dietary_save", payload, f"bad-reopen-{len(payload)}", now
            )
    assert_no_write(dietary_engine, store, before, writes)
    with pytest.raises(DomainError, match="invalid_transition"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_access_set",
            access_payload(dietary_engine, 3, True),
            "share-cleared",
            now,
        )

    reopened = await save_profile(
        dietary_engine,
        now,
        revision=cleared["revision"],
        note="FRESH-CONTENT",
        operation="reopen-profile",
    )
    assert reopened == {"member_id": "adult", "revision": 4, "status": "active"}
    assert profiles(dietary_engine)["adult"]["allergy_note"] == "FRESH-CONTENT"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["dietary_save", "dietary_access_set", "dietary_clear"])
@pytest.mark.parametrize("bad_revision", ["missing", *INVALID_REVISIONS])
async def test_existing_actions_require_strict_revision_without_write(
    dietary_engine, store, now, action, bad_revision
):
    created = await save_profile(dietary_engine, now)
    payload = {"member_id": "adult"}
    if action == "dietary_save":
        payload.update(content(note="EDITED"))
    elif action == "dietary_access_set":
        payload.update(
            member_revision=dietary_engine.snapshot()["members"]["adult"]["revision"],
            share_with_parents=True,
        )
    if bad_revision != "missing":
        payload["revision"] = bad_revision
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await dietary_engine.execute(
            "adult", f"pantry.{action}", payload, f"bad-{action}-{bad_revision!r}", now
        )
    assert_no_write(dietary_engine, store, before, writes)
    assert created["revision"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, True, 1, 1.0, "1", 0, -1, 2**53])
async def test_new_profile_rejects_every_explicit_revision(dietary_engine, store, now, revision):
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await dietary_engine.execute(
            "adult",
            "pantry.dietary_save",
            {"member_id": "adult", "revision": revision, **content()},
            f"new-with-revision-{revision!r}",
            now,
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
async def test_max_stored_revision_cannot_overflow_or_write(dietary_engine, store, now):
    await save_profile(dietary_engine, now)
    state = dietary_engine.snapshot()
    state["dietary_profiles"]["adult"]["revision"] = 2**53 - 1
    restored = Engine(state, store.save)
    before, writes = restored.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await restored.execute(
            "adult",
            "pantry.dietary_save",
            {
                "member_id": "adult",
                "revision": 2**53 - 1,
                **content(note="OVERFLOW"),
            },
            "revision-overflow",
            now,
        )
    assert_no_write(restored, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["dietary_save", "dietary_access_set", "dietary_clear"])
async def test_stale_positive_revision_conflicts_without_write(dietary_engine, store, now, action):
    created = await save_profile(dietary_engine, now)
    current = await dietary_engine.execute(
        "adult",
        "pantry.dietary_save",
        {"member_id": "adult", "revision": created["revision"], **content(note="CURRENT")},
        "advance-profile",
        now,
    )
    payload = {"member_id": "adult", "revision": created["revision"]}
    if action == "dietary_save":
        payload.update(content(note="STALE"))
    elif action == "dietary_access_set":
        payload.update(
            member_revision=dietary_engine.snapshot()["members"]["adult"]["revision"],
            share_with_parents=True,
        )
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await dietary_engine.execute("adult", f"pantry.{action}", payload, f"stale-{action}", now)
    assert_no_write(dietary_engine, store, before, writes)
    assert current["revision"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"likes": [" "]},
        {"likes": ["x" * 81]},
        {"likes": ["Same", " same "]},
        {"likes": ["Same"], "avoid": [" same "]},
        {"likes": ["x"] * 31},
        {"likes": "not-a-list"},
        {"allergy_note": "x" * 1001},
        {"management": "self"},
        {"share_with_parents": True},
        {"extra": True},
    ],
)
async def test_content_shape_and_duplicate_labels_reject_atomically(
    dietary_engine, store, now, changes
):
    payload = {"member_id": "adult", **content(note="")}
    payload.update(changes)
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await dietary_engine.execute(
            "adult", "pantry.dietary_save", payload, f"invalid-{writes}", now
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
async def test_whole_record_fields_are_required_and_trimmed(dietary_engine, store, now):
    for missing in ("likes", "dislikes", "avoid", "allergy_note"):
        payload = {"member_id": "adult", **content()}
        payload.pop(missing)
        before, writes = dietary_engine.snapshot(), store.calls
        with pytest.raises(DomainError, match="invalid_field"):
            await dietary_engine.execute(
                "adult", "pantry.dietary_save", payload, f"missing-{missing}", now
            )
        assert_no_write(dietary_engine, store, before, writes)
    receipt = await save_profile(
        dietary_engine,
        now,
        likes=["  Trim me  "],
        dislikes=[],
        avoid=[],
        note="  note  ",
    )
    row = profiles(dietary_engine)["adult"]
    assert receipt["revision"] == 1
    assert row["likes"] == ["Trim me"] and row["allergy_note"] == "note"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actor", "member_id"),
    [
        ("parent", "adult"),
        ("adult", "child"),
        ("child", "child"),
        ("guest", "guest"),
    ],
)
async def test_unauthorized_creation_is_write_free(dietary_engine, store, now, actor, member_id):
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="forbidden"):
        await save_profile(
            dietary_engine,
            now,
            actor,
            member_id,
            operation=f"forbidden-{actor}-{member_id}",
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "probe_revision"),
    [
        ("dietary_save", "missing"),
        ("dietary_save", 1),
        ("dietary_save", 2),
        ("dietary_clear", 1),
        ("dietary_clear", 2),
    ],
)
async def test_unauthorized_existing_profile_does_not_expose_revision_state(
    dietary_engine, store, now, action, probe_revision
):
    created = await save_profile(dietary_engine, now)
    payload = {"member_id": "adult"}
    if action == "dietary_save":
        payload.update(content(note="PROBE"))
    if probe_revision != "missing":
        payload["revision"] = probe_revision
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="forbidden"):
        await dietary_engine.execute(
            "parent", f"pantry.{action}", payload, f"probe-{action}-{probe_revision}", now
        )
    assert_no_write(dietary_engine, store, before, writes)
    assert created["revision"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["module", "role", "inactive"])
async def test_replay_rechecks_current_module_role_and_active_authority(
    dietary_engine, store, now, revocation
):
    payload = {"member_id": "child", **content(note="REPLAY-CANARY")}
    await dietary_engine.execute(
        "parent", "pantry.dietary_save", payload, f"saved-{revocation}", now
    )
    if revocation == "module":
        settings = dietary_engine.snapshot()["settings"]
        await dietary_engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": [module for module in settings["modules"] if module != "pantry"],
            },
            "disable-pantry",
            now,
        )
        expected = "module_disabled"
    else:
        await change_role(
            dietary_engine,
            now,
            "parent",
            "adult" if revocation == "role" else "parent",
            f"revoke-parent-{revocation}",
            active=revocation != "inactive",
        )
        expected = "forbidden"
    before, writes = dietary_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match=expected):
        await dietary_engine.execute(
            "parent", "pantry.dietary_save", payload, f"saved-{revocation}", now
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
async def test_concurrency_frozen_replay_store_failure_and_batch_rollback(
    dietary_engine, store, now
):
    payload = {"member_id": "adult", **content()}
    results = await asyncio.gather(
        *[
            dietary_engine.execute("adult", "pantry.dietary_save", payload, "same-profile", now)
            for _ in range(10)
        ]
    )
    assert all(result == results[0] for result in results)
    assert len(profiles(dietary_engine)) == 1 and store.calls == 1
    results[0]["status"] = "tampered"
    assert (
        await dietary_engine.execute("adult", "pantry.dietary_save", payload, "same-profile", now)
    )["status"] == "active"

    access = {
        "member_id": "adult",
        "revision": 1,
        "member_revision": dietary_engine.snapshot()["members"]["adult"]["revision"],
        "share_with_parents": True,
    }
    competing = await asyncio.gather(
        dietary_engine.execute("adult", "pantry.dietary_access_set", access, "access-one", now),
        dietary_engine.execute("adult", "pantry.dietary_access_set", access, "access-two", now),
        return_exceptions=True,
    )
    assert sum(isinstance(value, DomainError) for value in competing) == 1
    assert profiles(dietary_engine)["adult"]["revision"] == 2

    before, writes = dietary_engine.snapshot(), store.calls
    store.fail = True
    with pytest.raises(OSError):
        await save_profile(dietary_engine, now, "parent", "child", operation="failed-child-save")
    assert dietary_engine.snapshot() == before
    assert store.calls == writes + 1
    store.fail = False

    writes = store.calls

    with pytest.raises(DomainError, match="forbidden"):
        await dietary_engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {
                        "action": "pantry.dietary_save",
                        "payload": {"member_id": "child", **content(note="ROLLBACK-CANARY")},
                    },
                    {
                        "action": "pantry.dietary_save",
                        "payload": {"member_id": "adult", **content(note="FORBIDDEN")},
                    },
                ]
            },
            "dietary-batch",
            now,
        )
    assert_no_write(dietary_engine, store, before, writes)


@pytest.mark.asyncio
async def test_sensitive_content_never_enters_receipts_assistant_telegram_or_diagnostics(
    dietary_engine, now
):
    receipt = await save_profile(dietary_engine, now)
    state = dietary_engine.snapshot()
    assert CANARY in json.dumps(state["dietary_profiles"])
    for bucket in ("audit", "processed", "outbox"):
        assert CANARY not in json.dumps(state[bucket])
    assert state["outbox"] == {}
    assert result_refs(receipt) == []

    for actor in ("adult", "parent", "child", "guest"):
        view = dietary_engine.view(actor, now=now)
        assert CANARY not in json.dumps(plans.projection(view))
        assert CANARY not in json.dumps(
            plans.messages(view, "Synthetic request", (), now), ensure_ascii=False
        )
    telegram_text = await route(dietary_engine, "adult", "/shopping", "dietary-telegram-read", now)
    assert CANARY not in telegram_text


@pytest.mark.asyncio
async def test_guest_and_inactive_views_do_not_project_dietary_bucket(dietary_engine, now):
    await save_profile(dietary_engine, now)
    assert "pantry" not in dietary_engine.view("guest", now=now)
    await change_role(dietary_engine, now, "adult", "adult", "deactivate-adult", active=False)
    with pytest.raises(DomainError, match="forbidden"):
        dietary_engine.view("adult", now=now)
