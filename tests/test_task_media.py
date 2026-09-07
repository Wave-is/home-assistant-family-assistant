"""End-to-end task consumer tests for verified private photo attachments."""

import pytest

from custom_components.family_assistant.assistant.plans import projection as llm_projection
from custom_components.family_assistant.domain import media
from custom_components.family_assistant.domain.validation import DomainError

DIGEST = "b" * 64


async def create_task(engine, now, *, report_type="photo", assignee="child", operation=None):
    return await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": f"Synthetic {report_type} task",
            "assignee": assignee,
            "report_type": report_type,
        },
        operation or f"create-{report_type}-{assignee}",
        now,
    )


async def reserve(engine, now, task, *, actor="child", operation=None):
    actor_record = engine.snapshot()["members"][actor]
    return await engine.execute(
        actor,
        "media.reserve",
        {
            "purpose": "task_report",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "uploader_revision": actor_record["revision"],
        },
        operation or f"reserve-{task['id']}-{actor}-{task['revision']}",
        now,
    )


async def finalize(engine, now, reserved, *, actor="child", operation="finalize-media"):
    def transition(ctx):
        return media.finalize(
            ctx,
            actor,
            reserved["id"],
            reserved["revision"],
            "image/png",
            4321,
            DIGEST,
        )

    return await engine.system_update(operation, now, transition)


async def available(engine, now, task, *, actor="child", suffix="one"):
    reserved = await reserve(engine, now, task, actor=actor, operation=f"reserve-{suffix}")
    return await finalize(engine, now, reserved, actor=actor, operation=f"finalize-{suffix}")


async def submit(engine, now, task, attachment, *, actor="child", operation="submit-photo"):
    return await engine.execute(
        actor,
        "tasks.submit",
        {
            "id": task["id"],
            "revision": task["revision"],
            "media": {"id": attachment["id"], "revision": attachment["revision"]},
        },
        operation,
        now,
    )


def task_row(engine, actor, task_id, now):
    return next(item for item in engine.view(actor, now=now)["tasks"] if item["id"] == task_id)


@pytest.mark.asyncio
async def test_photo_submit_atomically_attaches_and_exact_replay_is_stable(engine, store, now):
    task = await create_task(engine, now)
    attachment = await available(engine, now, task)
    before = engine.snapshot()
    store.fail = True

    with pytest.raises(OSError):
        await submit(engine, now, task, attachment)
    assert engine.snapshot() == before
    assert engine.snapshot()["media"][attachment["id"]]["status"] == "available"

    store.fail = False
    receipt = await submit(engine, now, task, attachment)
    assert receipt == {"id": task["id"], "revision": 2, "status": "submitted"}
    stored = engine.snapshot()
    assert stored["tasks"][task["id"]]["report_media"] == [attachment["id"]]
    assert stored["tasks"][task["id"]]["report_generation"] == 1
    assert stored["media"][attachment["id"]]["status"] == "attached"
    assert stored["media"][attachment["id"]]["revision"] == 3
    calls = store.calls

    assert await submit(engine, now, task, attachment) == receipt
    assert engine.snapshot() == stored
    assert store.calls == calls


@pytest.mark.asyncio
async def test_double_submit_and_wrong_media_do_not_mutate(engine, now):
    task = await create_task(engine, now)
    first = await available(engine, now, task, suffix="first")
    second = await available(engine, now, task, suffix="second")
    await submit(engine, now, task, first)
    current = engine.snapshot()["tasks"][task["id"]]
    before = engine.snapshot()

    with pytest.raises(DomainError, match="conflict"):
        await submit(engine, now, task, first, operation="stale-double-submit")
    assert engine.snapshot() == before
    with pytest.raises(DomainError, match="invalid_transition"):
        await submit(engine, now, current, second, operation="fresh-double-submit")
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_current_assignee_and_parent_receive_only_bounded_metadata(engine, now):
    task = await create_task(engine, now)
    attachment = await available(engine, now, task)
    await submit(engine, now, task, attachment)

    for actor in ("child", "parent", "owner"):
        row = task_row(engine, actor, task["id"], now)
        assert row["report_attachments"] == [
            {
                "id": attachment["id"],
                "revision": 3,
                "purpose": "task_report",
                "mime_type": "image/png",
                "size_bytes": 4321,
                "status": "attached",
            }
        ]
        assert not any(
            key in repr(row) for key in (DIGEST, "blob_key", "uploader_revision", "scope")
        )
        assert "report_media" not in row
    for actor in ("sibling", "adult", "guest"):
        assert all(item["id"] != task["id"] for item in engine.view(actor, now=now)["tasks"])
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_ha("synthetic-unlinked-admin")


@pytest.mark.asyncio
async def test_outbox_and_llm_projection_never_receive_media_identifiers_or_secrets(engine, now):
    task = await create_task(engine, now)
    attachment = await available(engine, now, task)
    await submit(engine, now, task, attachment)
    snapshot = engine.snapshot()

    assert all(attachment["id"] not in repr(event) for event in snapshot["outbox"].values())
    assert all(
        DIGEST not in repr(event) and "blob_key" not in repr(event)
        for event in snapshot["outbox"].values()
    )
    for actor in ("child", "parent"):
        projected = llm_projection(engine.view(actor, now=now))
        assert attachment["id"] not in repr(projected)
        assert DIGEST not in repr(projected) and "report_attachments" not in repr(projected)
    submit_audit = next(event for event in snapshot["audit"] if event["id"] == "submit-photo")
    assert submit_audit["result"] == {"id": task["id"], "revision": 2, "status": "submitted"}


@pytest.mark.asyncio
async def test_resubmission_archives_old_media_for_parents_only(engine, now):
    task = await create_task(engine, now)
    first = await available(engine, now, task, suffix="first")
    await submit(engine, now, task, first, operation="submit-first")
    submitted = engine.snapshot()["tasks"][task["id"]]
    await engine.execute(
        "parent",
        "tasks.request_changes",
        {"id": task["id"], "revision": submitted["revision"], "note": "Try again"},
        "request-new-photo",
        now,
    )
    needs_changes = engine.snapshot()["tasks"][task["id"]]
    second = await available(engine, now, needs_changes, suffix="second")
    await submit(engine, now, needs_changes, second, operation="submit-second")

    child_row = task_row(engine, "child", task["id"], now)
    assert "previous_reports" not in child_row
    assert [item["id"] for item in child_row["report_attachments"]] == [second["id"]]
    parent_row = task_row(engine, "parent", task["id"], now)
    assert [item["id"] for item in parent_row["report_attachments"]] == [second["id"]]
    assert [
        item["id"]
        for report in parent_row["previous_reports"]
        for item in report["report_attachments"]
    ] == [first["id"]]
    with pytest.raises(DomainError, match="forbidden"):
        media.read_metadata(
            engine.snapshot(), engine.snapshot()["members"]["child"], first["id"], now
        )
    assert (
        media.read_metadata(
            engine.snapshot(), engine.snapshot()["members"]["parent"], first["id"], now
        )["id"]
        == first["id"]
    )


@pytest.mark.asyncio
async def test_reassignment_hides_historical_media_from_old_and_new_children(engine, now):
    task = await create_task(engine, now)
    attachment = await available(engine, now, task)
    await submit(engine, now, task, attachment)
    current = engine.snapshot()["tasks"][task["id"]]
    await engine.execute(
        "parent",
        "tasks.request_changes",
        {"id": task["id"], "revision": current["revision"], "note": "Reassign"},
        "review-before-reassign",
        now,
    )
    current = engine.snapshot()["tasks"][task["id"]]
    await engine.execute(
        "parent",
        "tasks.revise",
        {"id": task["id"], "revision": current["revision"], "assignee": "sibling"},
        "reassign-photo",
        now,
    )

    assert all(item["id"] != task["id"] for item in engine.view("child", now=now)["tasks"])
    sibling_row = task_row(engine, "sibling", task["id"], now)
    assert "previous_reports" not in sibling_row and "report_attachments" not in sibling_row
    parent_row = task_row(engine, "parent", task["id"], now)
    assert parent_row["previous_reports"][0]["report_attachments"][0]["id"] == attachment["id"]
    for actor in ("child", "sibling"):
        with pytest.raises(DomainError, match="forbidden"):
            media.read_metadata(
                engine.snapshot(), engine.snapshot()["members"][actor], attachment["id"], now
            )


@pytest.mark.asyncio
async def test_same_member_id_epoch_change_revokes_child_and_parent_refresh_archives(engine, now):
    task = await create_task(engine, now)
    attachment = await available(engine, now, task)
    submit_payload = {
        "id": task["id"],
        "revision": task["revision"],
        "media": {"id": attachment["id"], "revision": attachment["revision"]},
    }
    await engine.execute("child", "tasks.submit", submit_payload, "epoch-submit", now)
    member = engine.snapshot()["members"]["child"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": member["revision"],
            "name": "Rebound child",
            "role": "child",
            "language": member["language"],
            "aliases": member["aliases"],
            "ha_user_id": member.get("ha_user_id"),
            "active": True,
        },
        "rebind-child",
        now,
    )

    assert task_row(engine, "child", task["id"], now).get("report_attachments") == []
    assert (
        task_row(engine, "parent", task["id"], now)["report_attachments"][0]["id"]
        == attachment["id"]
    )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("child", "tasks.submit", submit_payload, "epoch-submit", now)

    current = engine.snapshot()["tasks"][task["id"]]
    await engine.execute(
        "parent",
        "tasks.request_changes",
        {"id": task["id"], "revision": current["revision"], "note": "Refresh identity"},
        "epoch-review",
        now,
    )
    current = engine.snapshot()["tasks"][task["id"]]
    await engine.execute(
        "parent",
        "tasks.revise",
        {"id": task["id"], "revision": current["revision"], "assignee": "child"},
        "epoch-refresh",
        now,
    )
    child_row = task_row(engine, "child", task["id"], now)
    assert "previous_reports" not in child_row and "report_attachments" not in child_row
    assert (
        task_row(engine, "parent", task["id"], now)["previous_reports"][0]["report_attachments"][0][
            "id"
        ]
        == attachment["id"]
    )


@pytest.mark.asyncio
async def test_photo_text_and_none_submit_payload_contracts_remain_distinct(engine, now):
    photo = await create_task(engine, now)
    attachment = await available(engine, now, photo)
    before = engine.snapshot()
    for payload, code in (
        ({"id": photo["id"], "revision": photo["revision"]}, "photo_required"),
        (
            {
                "id": photo["id"],
                "revision": photo["revision"],
                "media": {"id": attachment["id"], "revision": attachment["revision"]},
                "report": "must not coexist",
            },
            "photo_required",
        ),
    ):
        with pytest.raises(DomainError, match=code):
            await engine.execute(
                "child", "tasks.submit", payload, f"bad-{code}-{len(payload)}", now
            )
        assert engine.snapshot() == before

    text_task = await create_task(engine, now, report_type="text", operation="create-text")
    none_task = await create_task(engine, now, report_type="none", operation="create-none")
    for task_item, operation in ((text_task, "text-with-media"), (none_task, "none-with-media")):
        before = engine.snapshot()
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute(
                "child",
                "tasks.submit",
                {
                    "id": task_item["id"],
                    "revision": task_item["revision"],
                    "media": {"id": attachment["id"], "revision": attachment["revision"]},
                },
                operation,
                now,
            )
        assert engine.snapshot() == before

    text_result = await engine.execute(
        "child",
        "tasks.submit",
        {"id": text_task["id"], "revision": text_task["revision"], "report": "Done"},
        "submit-text",
        now,
    )
    assert text_result["report"] == "Done" and text_result["status"] == "submitted"

    none_result = await engine.execute(
        "child",
        "tasks.submit",
        {"id": none_task["id"], "revision": none_task["revision"]},
        "submit-none",
        now,
    )
    assert none_result["report"] is None and none_result["status"] == "submitted"
