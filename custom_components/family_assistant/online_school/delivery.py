"""Opt-in private school notifications with durable deduplication and live guards."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from ..domain.online_school import FRESH_FOR, current_source
from ..domain.validation import timestamp

KEY = "online_school_notice"


def _fresh(source, now):
    success = source.get("last_success")
    return (
        source.get("status") == "ready"
        and success
        and timedelta(0) <= now - timestamp(success, "last_success") <= FRESH_FOR
    )


def enqueue(ctx, source_id, changes):
    source = ctx.state.get("school", {}).get("online", {}).get("sources", {}).get(source_id)
    if (
        not source
        or current_source(ctx.state, source_id, source["generation"], source["member_revision"])
        is None
    ):
        return
    rules = source["rules"]
    if not rules["enabled"] or not _fresh(source, ctx.now):
        return
    local = ctx.now.astimezone(ZoneInfo(source["timezone"]))
    tomorrow = (local.date() + timedelta(days=1)).isoformat()
    snapshot = source.get("snapshot") or {}
    intents = []
    if rules["notify_changes"] and changes:
        ids = [row["id"] for row in changes]
        intents.append(("changes:" + ids[-1], {"kind": "changes", "changes": ids}))
    # Do not catch up yesterday's preparation after restart or during the night.
    if rules["homework_time"] <= local.strftime("%H:%M") <= "23:00" and any(
        row["date"] == tomorrow and not row["cancelled"] for row in snapshot.get("lessons", [])
    ):
        intents.append(("prepare:" + tomorrow, {"kind": "prepare", "date": tomorrow}))
    markers = source.setdefault("notification_markers", {})
    for marker in list(markers):
        if ctx.now - timestamp(markers[marker], "marker") > timedelta(days=7):
            del markers[marker]
    for key, descriptor in intents:
        marker = source["generation"] + ":" + key
        if marker in markers:
            continue
        for recipient in rules["recipients"]:
            member = ctx.state["members"].get(recipient, {})
            if not member.get("active") or (
                member.get("role") not in {"owner", "parent"} and recipient != source["member"]
            ):
                continue
            # No backlog for a member who has not connected their own bot chat.
            if not member.get("telegram_id"):
                continue
            ctx.notify(
                recipient,
                KEY,
                {
                    **descriptor,
                    "source": source_id,
                    "generation": source["generation"],
                    "source_revision": source["revision"],
                    "member_revision": source["member_revision"],
                    "recipient_revision": member["revision"],
                    "chat_id": member["telegram_id"],
                    "private_context": True,
                    "expires_at": (ctx.now + timedelta(hours=12)).isoformat(),
                },
            )
        markers[marker] = ctx.now.isoformat()
    while len(markers) > 100:
        del markers[next(iter(markers))]


def current(state, event, now=None):
    data = event.get("data", {})
    source = current_source(
        state, data.get("source"), data.get("generation"), data.get("member_revision")
    )
    if (
        not source
        or source["revision"] != data.get("source_revision")
        or (now is not None and not _fresh(source, now))
    ):
        return False
    member_id = event.get("recipient")
    member = state.get("members", {}).get(member_id, {})
    rules = source["rules"]
    if (
        not rules["enabled"]
        or member_id not in rules["recipients"]
        or not member.get("active")
        or member.get("revision") != data.get("recipient_revision")
        or not member.get("telegram_id")
        or member["telegram_id"] != data.get("chat_id")
        or member.get("role") not in {"owner", "parent"}
        and member_id != source["member"]
        or (now is not None and now >= timestamp(data.get("expires_at"), "expires_at"))
    ):
        return False
    if data.get("kind") == "changes":
        return rules["notify_changes"] and bool(
            set(data.get("changes", [])) & {row["id"] for row in source.get("changes", [])}
        )
    if data.get("kind") == "prepare":
        return (
            now is None
            or now.astimezone(ZoneInfo(source["timezone"])).date().isoformat()
            < data.get("date", "")
        ) and any(
            row["date"] == data.get("date") and not row["cancelled"]
            for row in (source.get("snapshot") or {}).get("lessons", [])
        )
    return False


def targets(state, event, now=None):
    if not current(state, event, now):
        return []
    member = state["members"][event["recipient"]]
    return [{"channel": "telegram", "id": member["telegram_id"], "language": member["language"]}]
