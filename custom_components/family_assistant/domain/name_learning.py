"""Grounded name repairs: local language memory, never member identity changes.

The model supplies an ordinary typed plan. Only a unique one-edit recipient
correction whose strict parse reproduces that entire plan can execute without
review. No fuzzy result is used for authentication or hardware commands.
"""

import re
import unicodedata

from ..telegram.intents import assignment_recipient, find_member, parse
from .validation import DomainError, fields, text
from .validation import revision as strict_revision


def spelling(value):
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").strip()
    if not re.fullmatch(r"[a-zа-яіїєґ]{4,40}", value):
        return None
    if re.search(r"[a-z]", value) and re.search(r"[а-яіїєґ]", value):
        return None
    # Same bounded Cyrillic case-ending rule as the deterministic name resolver.
    return re.sub(r"[аеиоуєюяы]$", "", value)


def one_edit(left, right):
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        different = [i for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        return len(different) == 1 or (
            len(different) == 2
            and different[1] == different[0] + 1
            and left[different[0]] == right[different[1]]
            and left[different[1]] == right[different[0]]
        )
    short, long = sorted((left, right), key=len)
    return any(short == long[:i] + long[i + 1 :] for i in range(len(long)))


def candidate(state, source):
    key = spelling(source)
    if key is None or len(key) < 4:
        return None
    try:
        find_member(state, source)
    except DomainError as err:
        if err.code != "unknown_member":
            return None
    else:
        return None  # Explicit configured names/aliases always win.
    matches = set()
    for member in state["members"].values():
        if not member.get("active"):
            continue
        for name in (member["name"], *member.get("aliases", [])):
            other = spelling(name)
            if other and len(other) >= 4 and one_edit(key, other):
                matches.add(member["id"])
    return next(iter(matches)) if len(matches) == 1 else None


def effective(state, actor, record):
    member = state["members"].get(record.get("member"), {})
    return bool(
        record.get("active")
        and record.get("actor") == actor.get("id")
        and actor.get("active")
        and actor.get("role") in {"owner", "parent"}
        and record.get("role") == actor.get("role")
        and record.get("actor_revision") == actor.get("revision")
        and member.get("active")
        and record.get("member_revision") == member.get("revision")
        and candidate(state, record.get("source", "")) == member.get("id")
    )


def resolve(state, actor_id, content):
    span = assignment_recipient(content)
    if span is None:
        return content
    source = content[span[0] : span[1]]
    key = spelling(source)
    if key is None:
        return content
    actor = state["members"].get(actor_id, {})
    matches = {
        row["member"]
        for row in state["memory"].get("phrases", {}).values()
        if row.get("kind") == "member_alias"
        and row.get("normalized") == key
        and effective(state, actor, row)
        and candidate(state, source) == row["member"]
    }
    if len(matches) != 1:
        return content
    name = state["members"][next(iter(matches))]["name"]
    return content[: span[0]] + name + content[span[1] :]


def prove(state, view, content, now, commands):
    """Return a narrowly checked correction, or None to retain normal review."""
    if view["role"] not in {"owner", "parent"} or not isinstance(content, str):
        return None
    if len(content) > 4000 or not isinstance(commands, list) or len(commands) != 1:
        return None
    command = commands[0]
    if not isinstance(command, dict) or set(command) != {"action", "payload"}:
        return None
    if command.get("action") != "tasks.create" or not isinstance(command.get("payload"), dict):
        return None
    span = assignment_recipient(content)
    if span is None:
        return None
    source = content[span[0] : span[1]]
    member_id = candidate(state, source)
    if member_id is None or member_id != command["payload"].get("assignee"):
        return None
    member = state["members"][member_id]
    visible = next((m for m in view["members"] if m["id"] == member_id), None)
    if (
        member["role"] == "guest"
        or visible is None
        or visible.get("revision") != member["revision"]
    ):
        return None
    records = state["memory"].get("phrases", {})
    old = next(
        (
            r
            for r in records.values()
            if r.get("kind") == "member_alias"
            and r.get("actor") == view["actor"]
            and r.get("normalized") == spelling(source)
        ),
        None,
    )
    actor = state["members"][view["actor"]]
    if old is not None and not effective(state, actor, old):
        return None  # A revoked/stale rule is never resurrected by a model.
    if old is None and sum(r.get("actor") == view["actor"] for r in records.values()) >= 200:
        return None
    corrected = content[: span[0]] + member["name"] + content[span[1] :]
    try:
        original = parse(state, view, content, now)
    except DomainError as err:
        if err.code != "unknown_member":
            return None
    else:
        if original is not None:
            return None
    try:
        intent = parse(state, view, corrected, now)
    except DomainError:
        return None
    payload = {**command["payload"]}
    if "assignee_revision" in payload:
        if strict_revision(payload.pop("assignee_revision")) != member["revision"]:
            return None
    payload.setdefault("due_at", None)
    if intent is None or intent.action != "tasks.create" or intent.payload != payload:
        return None
    return {
        "source": source,
        "normalized": spelling(source),
        "canonical": member["name"],
        "member": member_id,
        "member_revision": member["revision"],
        "actor_revision": actor["revision"],
        "role": actor["role"],
    }


def handle(ctx, payload):
    """Task, rule and receipt commit together; failed writes teach nothing."""
    from .engine import Engine

    ctx.require_parent()
    fields(
        payload,
        {"source", "commands", "actor_revision", "member_revision"},
        {"source", "commands", "actor_revision", "member_revision"},
    )
    source = text(payload["source"], "source", 4000)
    if strict_revision(payload["actor_revision"]) != ctx.actor["revision"]:
        raise DomainError("conflict")

    async def discard(_state):
        pass

    view = Engine(ctx.state, discard).view(ctx.actor_id)
    correction = prove(ctx.state, view, source, ctx.now, payload["commands"])
    if (
        correction is None
        or strict_revision(payload["member_revision"]) != correction["member_revision"]
    ):
        raise DomainError("conflict")
    command = payload["commands"][0]
    task = Engine._dispatch(ctx, command["action"], command["payload"])
    records = ctx.state["memory"].setdefault("phrases", {})
    old = next(
        (
            r
            for r in records.values()
            if r.get("kind") == "member_alias"
            and r.get("actor") == ctx.actor_id
            and r.get("normalized") == correction["normalized"]
        ),
        None,
    )
    if old is None:
        old = ctx.touch(
            {
                **correction,
                "id": ctx.identifier("L"),
                "actor": ctx.actor_id,
                "kind": "member_alias",
                "active": True,
                "provenance": "model_name_repair",
                "operation_id": ctx.operation_id,
            }
        )
        records[old["id"]] = old
    return {
        "id": old["id"],
        "status": "repaired",
        "items": [task],
        "actor_revision": correction["actor_revision"],
        "member_revision": correction["member_revision"],
        "member": correction["member"],
    }


def authorize_replay(ctx, payload, result):
    from . import task_access

    ctx.require_parent()
    member = ctx.member(result["member"])
    if (
        payload.get("actor_revision") != ctx.actor["revision"]
        or result.get("actor_revision") != ctx.actor["revision"]
        or result.get("member_revision") != member["revision"]
    ):
        raise DomainError("conflict")
    if "tasks" not in ctx.state["settings"]["modules"]:
        raise DomainError("module_disabled")
    for item in result["items"]:
        task_access.authorize_replay(ctx.state, ctx.actor, item)


def reply(result, view, language):
    from ..assistant.language import COPY
    from ..telegram.presentation import summary

    record = next(r for r in view["learned_phrases"] if r["id"] == result["id"])
    return COPY[language]["name_repaired"].format(
        source=record["source"],
        canonical=record["canonical"],
        id=result["id"],
        result="\n".join(summary(item, view, language) for item in result["items"]),
    )
