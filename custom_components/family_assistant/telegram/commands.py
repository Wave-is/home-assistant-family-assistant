"""Persist interpretation before execution so redeliveries keep the exact same plan."""

import hashlib
import json

from ..domain.validation import DomainError


def signature(actor, content, refs):
    return hashlib.sha256(
        json.dumps([actor, content, list(refs)], ensure_ascii=False).encode()
    ).hexdigest()


def previous(engine, actor, content, refs, operation_id):
    engine.view(actor)  # Recheck the identity even when replaying a stored plan.
    prior = engine.snapshot()["telegram"].get("plans", {}).get(operation_id)
    if prior and prior["signature"] != signature(actor, content, refs):
        raise DomainError("idempotency_conflict")
    return prior


async def execute(engine, actor, content, refs, operation_id, now, action, payload):
    def save(ctx):
        plans = ctx.state["telegram"].setdefault("plans", {})
        fingerprint = signature(actor, content, refs)
        if operation_id in plans and plans[operation_id]["signature"] != fingerprint:
            raise DomainError("idempotency_conflict")
        return plans.setdefault(
            operation_id,
            {
                "signature": fingerprint,
                "action": action,
                "payload": payload,
                "actor": actor,
                "created_at": now.isoformat(),
            },
        )

    plan = await engine.system_update("command_interpretation", now, save)
    return await engine.execute(actor, plan["action"], plan["payload"], operation_id, now)
