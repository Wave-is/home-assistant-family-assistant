"""Opt-in hints; no model receives a learner's answer or family context."""

import asyncio
from copy import deepcopy

from .domain import academy
from .domain.validation import DomainError, text

SCHEMA = {
    "type": "object",
    "properties": {"hint": {"type": "string", "minLength": 1, "maxLength": 800}},
    "required": ["hint"],
    "additionalProperties": False,
}


def validate(value):
    if not isinstance(value, dict) or set(value) != {"hint"}:
        raise DomainError("provider_bad_response")
    return text(value["hint"], "hint", 800)


def question(state, actor, now, assignment_id, revision):
    if actor["role"] != "child":
        raise DomainError("forbidden")
    row = next(
        (row for row in academy.project(state, actor, now)["assignments"]
         if row["id"] == assignment_id),
        None,
    )
    if row is None:
        raise DomainError("forbidden")
    if row["revision"] != revision or not row["question"]:
        raise DomainError("conflict")
    return row


async def hint(scope, now, assignment_id, revision):
    """Return local instruction or a bounded answer-only model suggestion."""
    state = scope.engine.snapshot()
    actor = state["members"][scope.actor]
    row = question(state, actor, now(), assignment_id, revision)
    current_question = row["question"]
    local = {"source": "local", "text": current_question["lesson"]}
    runtime = scope.runtime
    assistant = runtime.assistant
    cascade = getattr(assistant, "cascade", None)
    if not row["allow_ai"] or cascade is None or "conversation" not in state["settings"]["modules"]:
        return local
    marker = runtime.assistant_revision
    config = deepcopy(dict(scope._entry.options).get("conversation"))

    async def check():
        await scope.check()
        latest = scope.engine.snapshot()
        if (
            runtime.assistant is not assistant
            or runtime.assistant_revision != marker
            or dict(scope._entry.options).get("conversation") != config
            or "conversation" not in latest["settings"]["modules"]
        ):
            raise DomainError("conflict")
        refreshed = question(latest, latest["members"][scope.actor], now(), assignment_id, revision)
        if not refreshed["allow_ai"] or refreshed["question"] != current_question:
            raise DomainError("conflict")

    from .assistant.provider import bind_actor

    active = getattr(runtime, "academy_hint_active", None)
    if active is None:
        active = runtime.academy_hint_active = set()
    if scope.actor in active or len(active) >= 2:
        raise DomainError("assistant_busy")
    active.add(scope.actor)
    try:
        await check()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a supportive mathematics tutor for school students. Give one "
                    "short hint, not the final answer. Do not request personal information, "
                    "include links, or claim to grade. Use the requested language. "
                    "Return JSON with a single hint string."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Language: {row['language']}. Topic: {current_question['title']}. "
                    f"Exercise: {current_question['prompt']}. "
                    f"Rule: {current_question['lesson']}"
                ),
            },
        ]
        bound = bind_actor(cascade, scope.actor, scope.actor_revision, scope.language)
        try:
            async with asyncio.timeout(30):
                result = await bound.generate(messages, SCHEMA, validate, scope_check=check)
        except TimeoutError:
            await check()
            return local
        except DomainError as error:
            if error.code in {"forbidden", "conflict"}:
                raise
            await check()
            return local
        await check()
        return {"source": "ai", "text": result}
    finally:
        active.discard(scope.actor)
