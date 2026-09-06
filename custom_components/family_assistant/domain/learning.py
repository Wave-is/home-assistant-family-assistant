"""Explicit per-person language corrections, not generated code or permissions."""

import re
import unicodedata
from copy import deepcopy

from ..telegram.intents import parse
from .context import Context
from .validation import DomainError, fields, text

READ_COMMANDS = {"/stats", "/tasks", "/shopping", "/alarms"}


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()).strip(" .?!")


def resolve(state, actor, value):
    if "conversation" not in state["settings"]["modules"]:
        return value
    source = normalized(value)
    for record in state["memory"].get("phrases", {}).values():
        if record["actor"] == actor and record["active"] and record["normalized"] == source:
            return record["canonical"]
    return value


def handle(ctx, action, payload):
    from .engine import Engine

    phrases = ctx.state["memory"].setdefault("phrases", {})
    if action == "forget":
        fields(payload, {"id"}, {"id"})
        record = phrases.get(payload["id"])
        if record is None:
            raise DomainError("not_found")
        if record["actor"] != ctx.actor_id:
            raise DomainError("forbidden")
        record["active"] = False
        ctx.touch(record)
        return {"id": record["id"], "status": "forgotten"}
    fields(payload, {"source", "canonical"}, {"source", "canonical"})
    source = text(payload["source"], "source", 400)
    canonical = text(payload["canonical"], "canonical", 400)
    if source.startswith("/") or normalized(source) == normalized(canonical):
        raise DomainError("invalid_field", "source")
    # Do not pin a reusable phrase to one old record or an absolute date.
    if re.search(r"\b[TSACP]\d{4,}\b|\b\d{4}-\d{2}-\d{2}\b", canonical, re.I):
        raise DomainError("learning_template_required")

    async def discard(_state):
        pass

    view = Engine(ctx.state, discard).view(ctx.actor_id)
    try:
        source_intent = parse(ctx.state, view, source, ctx.now)
    except DomainError:
        source_intent = None
    if source_intent is not None:
        raise DomainError("learning_template_required")  # Never shadow a built-in strict command.
    if canonical not in READ_COMMANDS:
        try:
            intent = parse(ctx.state, view, canonical, ctx.now)
        except DomainError as err:
            if err.code != "context_required":
                raise
            intent = None  # A reply-based template resolves the actual target only at use time.
            if not re.match(
                r"^(?:установи срок|встанови термін|set (?:the )?deadline)\b", canonical, re.I
            ):
                raise DomainError("learning_template_required") from None
        else:
            if intent is None:
                raise DomainError("learning_template_required")
            if not intent.action.startswith("read."):
                trial = Context(deepcopy(ctx.state), ctx.actor, ctx.now, "learning-preview")
                Engine._dispatch(trial, intent.action, intent.payload)
    existing = next(
        (
            p
            for p in phrases.values()
            if p["actor"] == ctx.actor_id and p["normalized"] == normalized(source)
        ),
        None,
    )
    if existing is None and sum(p["actor"] == ctx.actor_id for p in phrases.values()) >= 200:
        raise DomainError("learning_limit")
    record = {
        **(existing or {}),
        "id": existing["id"] if existing else ctx.identifier("L"),
        "actor": ctx.actor_id,
        "source": source,
        "normalized": normalized(source),
        "canonical": canonical,
        "active": True,
    }
    phrases[record["id"]] = ctx.touch(record)
    # Public decision log records the ID, not another person's private phrase.
    return {"id": record["id"], "status": "learned"}
