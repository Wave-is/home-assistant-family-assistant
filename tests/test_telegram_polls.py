"""Private Telegram rendering and callback contracts for family polls."""

import re
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import poll_reviews
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram import polls as telegram_polls


async def poll_engine(engine):
    state = engine.snapshot()
    if "polls" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("polls")

    async def save(_state):
        return None

    return Engine(state, save)


async def create_poll(engine, now, *, operation="create", eligible=("child",)):
    state = engine.snapshot()
    return await engine.execute(
        "parent",
        "polls.create",
        {
            "actor_revision": 1,
            "question": "Question canary: secret family choice?",
            "options": ["Choice canary alpha", "Choice canary beta"],
            "eligible": [
                {"member": member, "revision": state["members"][member]["revision"]}
                for member in eligible
            ],
            "closes_at": (now + timedelta(hours=2)).isoformat(),
            "confirm_private_ballot_limits": True,
        },
        operation,
        now,
    )


def callbacks(rendered):
    return [
        button["callback_data"]
        for row in rendered.get("reply_markup", {}).get("inline_keyboard", [])
        for button in row
    ]


def callback_buttons(rendered):
    return {
        button["callback_data"]: button["text"]
        for row in rendered.get("reply_markup", {}).get("inline_keyboard", [])
        for button in row
    }


def assert_review_descriptor(descriptor):
    assert set(descriptor) == {"kind", "mode", "review_id"}
    assert descriptor["kind"] == "polls" and descriptor["mode"] == "review"
    assert re.fullmatch(r"PR[A-Za-z0-9_-]{16}", descriptor["review_id"])
    assert not ({"poll_id", "option_id", "ballot_revision"} & descriptor.keys())


@pytest.mark.asyncio
async def test_group_list_and_callbacks_are_constant_private_redirects(engine, now):
    e = await poll_engine(engine)
    await create_poll(e, now)
    before = e.snapshot()
    descriptor = await telegram_polls.route(
        e, "child", "/polls", "tg:1:1:action", now, private=False
    )
    forged = await telegram_polls.route(
        e, "child", "ps:v:PL000001:O1", "tg:1:2:action", now, private=False
    )
    assert descriptor == forged == {"kind": "polls", "mode": "private"}
    rendered = telegram_polls.render_reply(before, "child", descriptor, now, "en")
    assert "direct chat" in rendered["text"]
    assert "Question canary" not in rendered["text"]
    assert "Choice canary" not in rendered["text"]
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_private_list_is_send_time_only_scoped_and_callbacks_are_bounded(engine, now):
    e = await poll_engine(engine)
    await create_poll(e, now, eligible=("child",))
    await create_poll(e, now, operation="sibling-poll", eligible=("sibling",))
    descriptor = await telegram_polls.route(
        e, "child", "/polls", "tg:1:1:action", now, private=True
    )
    assert descriptor == {"kind": "polls", "mode": "list"}
    assert "Question canary" not in repr(descriptor)
    rendered = telegram_polls.render_reply(e.snapshot(), "child", descriptor, now, "ru")
    assert rendered["text"].count("Question canary") == 1
    assert "Choice canary alpha" in rendered["text"]
    assert all(len(value.encode()) <= 64 for value in callbacks(rendered))
    assert "ps:v:PL000001:O1" in callbacks(rendered)
    assert not any("PL000002" in value for value in callbacks(rendered))
    assert rendered["link_preview_options"] == {"is_disabled": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ("en", "ru", "uk"))
async def test_long_poll_list_keeps_complete_scoped_blocks_with_bounded_keyboard(
    engine, now, language
):
    e = await poll_engine(engine)
    polls = []
    for poll_index in range(1, 9):
        question = f"Question {poll_index}: " + "Q" * 220
        options = [
            f"Choice {poll_index}.{option_index} " + "x" * 95 for option_index in range(1, 11)
        ]
        result = await e.execute(
            "parent",
            "polls.create",
            {
                "actor_revision": 1,
                "question": question,
                "options": options,
                "eligible": [{"member": "parent", "revision": 1}],
                "closes_at": (now + timedelta(hours=2)).isoformat(),
                "confirm_private_ballot_limits": True,
            },
            f"long-poll-{poll_index}",
            now,
        )
        polls.append((result["id"], question, options))

    rendered = telegram_polls.render_reply(
        e.snapshot(), "parent", {"kind": "polls", "mode": "list"}, now, language
    )
    keyboard = rendered["reply_markup"]["inline_keyboard"]
    buttons = callback_buttons(rendered)
    displayed = [item for item in polls if item[1] in rendered["text"]]

    assert 0 < len(displayed) < len(polls)
    assert len(rendered["text"]) <= telegram_polls.MAX_MESSAGE_TEXT
    assert sum(len(row) for row in keyboard) <= telegram_polls.MAX_KEYBOARD_BUTTONS
    assert all(1 <= len(row) <= 2 for row in keyboard)
    assert rendered["text"].endswith(telegram_polls.COPY[language]["more"])
    for poll_number, (poll_id, question, options) in enumerate(displayed, 1):
        assert f"P{poll_number} · {question}" in rendered["text"]
        for option_number, label in enumerate(options, 1):
            callback = f"ps:v:{poll_id}:O{option_number}"
            assert f"{option_number}. {label}" in rendered["text"]
            assert buttons[callback] == (f"P{poll_number} · {option_number}. {label[:48]}")
        assert buttons[f"ps:c:{poll_id}"] == (
            f"P{poll_number} · {telegram_polls.COPY[language]['close']}"
        )
    for poll_id, question, _options in polls[len(displayed) :]:
        assert question not in rendered["text"]
        assert not any(f":{poll_id}" in callback for callback in buttons)


@pytest.mark.asyncio
async def test_vote_review_and_new_update_retry_reuse_exact_engine_operation(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    review_descriptor = await telegram_polls.route(
        e, "child", f"ps:v:{poll_id}:O1", "tg:1:10:action", now, private=True
    )
    assert_review_descriptor(review_descriptor)
    review = telegram_polls.render_reply(e.snapshot(), "child", review_descriptor, now, "uk")
    assert "Choice canary alpha" in review["text"]
    confirm = next(value for value in callbacks(review) if value.startswith("pr:y:"))
    assert len(confirm.encode()) <= 64

    saved = await telegram_polls.route(e, "child", confirm, "tg:1:11:action", now, private=True)
    assert saved == {"kind": "polls", "mode": "saved", "action": "vote"}
    state = e.snapshot()
    assert state["poll_ballots"][poll_id]["child"]["revision"] == 1
    assert (
        state["poll_reviews"][review_descriptor["review_id"]]["confirm_operation_id"]
        == "tg:1:11:action"
    )

    retried = await telegram_polls.route(e, "child", confirm, "tg:1:12:action", now, private=True)
    assert retried == saved
    state = e.snapshot()
    assert state["poll_ballots"][poll_id]["child"]["revision"] == 1
    assert "tg:1:12:action" not in state["processed"]
    assert "tg:1:11:action" in state["processed"]
    assert (
        await telegram_polls.route(
            e, "child", f"ps:v:{poll_id}:O1", "tg:1:10:action", now, private=True
        )
        == review_descriptor
    )
    revoked = e.snapshot()
    revoked["members"]["child"]["active"] = False
    with pytest.raises(DomainError, match="forbidden"):
        telegram_polls.render_reply(revoked, "child", saved, now, "en")
    disabled = e.snapshot()
    disabled["settings"]["modules"].remove("polls")
    with pytest.raises(DomainError, match="module_disabled"):
        telegram_polls.render_reply(disabled, "child", saved, now, "en")


@pytest.mark.asyncio
async def test_descriptor_outbox_and_journals_never_store_poll_plaintext(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    descriptor = await telegram_polls.route(
        e, "child", f"ps:v:{poll_id}:O2", "tg:1:10:action", now, private=True
    )

    def queue(ctx):
        ctx.notify(
            "child",
            "telegram_reply",
            {"poll_reply": descriptor, "actor": "child", "bot_id": 1, "chat_id": 10},
        )

    await e.system_update("synthetic_poll_reply", now, queue)
    state = e.snapshot()
    protected = {
        "outbox": state["outbox"],
        "audit": state["audit"],
        "processed": state["processed"],
        "telegram": state["telegram"],
    }
    encoded = repr(protected)
    assert "Question canary" not in encoded
    assert "Choice canary alpha" not in encoded
    assert "Choice canary beta" not in encoded
    assert state["telegram"].get("plans", {}) == {}
    assert_review_descriptor(descriptor)


@pytest.mark.asyncio
async def test_review_descriptor_token_may_coincidentally_contain_option_id(
    engine, now, monkeypatch
):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    monkeypatch.setattr(poll_reviews.secrets, "token_urlsafe", lambda _size: "O2abcdefghijklmn")
    descriptor = await telegram_polls.route(
        e, "child", f"ps:v:{poll_id}:O2", "tg:1:token-action", now, private=True
    )
    assert descriptor["review_id"] == "PRO2abcdefghijklmn"
    assert_review_descriptor(descriptor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "close_label", "archive_label"),
    (
        ("en", "Close poll", "Archive poll"),
        ("ru", "Закрыть голосование", "Архивировать"),
        ("uk", "Закрити голосування", "Архівувати"),
    ),
)
async def test_parent_close_then_archive_each_use_review_and_opaque_receipt(
    engine, now, language, close_label, archive_label
):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    open_list = telegram_polls.render_reply(
        e.snapshot(), "parent", {"kind": "polls", "mode": "list"}, now, language
    )
    assert callback_buttons(open_list)[f"ps:c:{poll_id}"] == f"P1 · {close_label}"
    close_review = await telegram_polls.route(
        e, "parent", f"ps:c:{poll_id}", "tg:1:20:action", now, private=True
    )
    close_rendered = telegram_polls.render_reply(e.snapshot(), "parent", close_review, now, "en")
    close_confirm = next(value for value in callbacks(close_rendered) if value.startswith("pr:y:"))
    assert await telegram_polls.route(
        e, "parent", close_confirm, "tg:1:21:action", now, private=True
    ) == {"kind": "polls", "mode": "saved", "action": "close"}

    closed_list = telegram_polls.render_reply(
        e.snapshot(), "parent", {"kind": "polls", "mode": "list"}, now, language
    )
    assert callback_buttons(closed_list)[f"ps:a:{poll_id}"] == f"P1 · {archive_label}"

    archive_review = await telegram_polls.route(
        e, "parent", f"ps:a:{poll_id}", "tg:1:22:action", now, private=True
    )
    archive_rendered = telegram_polls.render_reply(
        e.snapshot(), "parent", archive_review, now, "en"
    )
    archive_confirm = next(
        value for value in callbacks(archive_rendered) if value.startswith("pr:y:")
    )
    assert await telegram_polls.route(
        e, "parent", archive_confirm, "tg:1:23:action", now, private=True
    ) == {"kind": "polls", "mode": "saved", "action": "archive"}
    assert e.snapshot()["polls"][poll_id]["status"] == "archived"
    assert poll_id not in e.snapshot()["poll_ballots"]


@pytest.mark.asyncio
async def test_cancel_and_malformed_or_purge_callbacks_are_nonmutating(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    review = await telegram_polls.route(
        e, "child", f"ps:v:{poll_id}:O1", "tg:1:10:action", now, private=True
    )
    rendered = telegram_polls.render_reply(e.snapshot(), "child", review, now, "en")
    cancel = next(value for value in callbacks(rendered) if value.startswith("pr:n:"))
    assert await telegram_polls.route(e, "child", cancel, "tg:1:11:action", now, private=True) == {
        "kind": "polls",
        "mode": "cancelled",
    }

    for invalid in (
        "ps:p:PL000001",
        "ps:v:PL000001",
        "ps:c:PL000001:O1",
        "pr:y:not-a-review",
        "ps:" + "x" * 70,
    ):
        before = e.snapshot()
        with pytest.raises(DomainError) as caught:
            await telegram_polls.route(e, "child", invalid, "tg:1:99:action", now, private=True)
        assert caught.value.code == "invalid_field"
        assert e.snapshot() == before


@pytest.mark.asyncio
async def test_stale_review_fails_on_member_module_and_source_changes(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    review = await telegram_polls.route(
        e, "child", f"ps:v:{poll_id}:O1", "tg:1:10:action", now, private=True
    )
    confirm = next(
        value
        for value in callbacks(
            telegram_polls.render_reply(e.snapshot(), "child", review, now, "en")
        )
        if value.startswith("pr:y:")
    )

    async def save(_state):
        return None

    stale_state = e.snapshot()
    stale_state["members"]["child"]["revision"] = 2
    stale = Engine(stale_state, save)
    with pytest.raises(DomainError, match="forbidden"):
        await telegram_polls.route(stale, "child", confirm, "tg:1:11:action", now, private=True)

    disabled_state = e.snapshot()
    disabled_state["settings"]["modules"].remove("polls")
    disabled = Engine(disabled_state, save)
    with pytest.raises(DomainError, match="module_disabled"):
        await telegram_polls.route(disabled, "child", confirm, "tg:1:11:action", now, private=True)

    changed_state = e.snapshot()
    changed_state["polls"][poll_id]["definition_revision"] = 2
    changed = Engine(changed_state, save)
    with pytest.raises(DomainError, match="conflict"):
        await telegram_polls.route(changed, "child", confirm, "tg:1:11:action", now, private=True)
