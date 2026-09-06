"""Parent-defined privileges with atomic point reservations, never device effects."""

from copy import deepcopy
from datetime import timedelta

from . import reward_wallet
from .validation import DomainError, enum, fields, text, timestamp


def wallet(state, member):
    return reward_wallet.balance(
        list(state["court"].values()), list(state["reward_requests"].values()), member
    )


def view(state, actor):
    if actor["role"] == "guest":
        return None
    parent = actor["role"] in {"owner", "parent"}
    catalog = [
        r
        for r in state["rewards"].values()
        if parent or (r["enabled"] and (not r["eligible"] or actor["id"] in r["eligible"]))
    ]
    requests = [
        r for r in state["reward_requests"].values() if parent or r["member"] == actor["id"]
    ]
    members = [
        m
        for m in state["members"].values()
        if m["role"] != "guest" and (parent or m["id"] == actor["id"])
    ]
    return {
        "catalog": catalog,
        "requests": requests,
        "balances": [{"member": m["id"], **wallet(state, m["id"])} for m in members],
    }


def integer(value, key, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise DomainError("invalid_field", key)
    return value


def optional(value, key, maximum=500):
    if value == "":
        return ""
    return text(value, key, maximum)


def referenced(ctx, bucket, payload):
    integer(payload["revision"], "revision", 1, 2**53 - 1)
    return ctx.record(bucket, payload["id"], payload["revision"])


def eligible(ctx, member_id, reward=None):
    member = ctx.member(member_id)
    if member["role"] == "guest":
        raise DomainError("invalid_field", "member")
    if reward and reward["eligible"] and member["id"] not in reward["eligible"]:
        raise DomainError("forbidden")
    return member


def history(ctx, record, status, reason):
    record["status"] = status
    record.setdefault("history", []).append(
        {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "status": status, "reason": reason}
    )
    ctx.touch(record)


def supersede(ctx, request):
    for event in ctx.state["outbox"].values():
        if (
            event["key"] in {"reward_requested", "reward_changed"}
            and event["data"].get("id") == request["id"]
            and event["state"] in {"pending", "awaiting_channel"}
        ):
            event["state"] = "superseded"


def handle(ctx, action, payload):
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "reward_save":
        ctx.require_parent()
        allowed = {
            "id",
            "revision",
            "name",
            "description",
            "cost",
            "enabled",
            "eligible",
            "request_ttl_hours",
        }
        fields(payload, allowed, {"name", "cost"} | ({"revision"} if "id" in payload else set()))
        if "id" not in payload and "revision" in payload:
            raise DomainError("invalid_field", "revision")
        previous = referenced(ctx, "rewards", payload) if "id" in payload else None
        value = {
            "description": "",
            "enabled": True,
            "eligible": [],
            "request_ttl_hours": 72,
            **deepcopy(previous or {}),
            **payload,
        }
        value["name"] = text(value["name"], "name", 120)
        value["description"] = optional(value["description"], "description")
        integer(value["cost"], "cost", 1, 10000)
        integer(value["request_ttl_hours"], "request_ttl_hours", 1, 720)
        if type(value["enabled"]) is not bool:
            raise DomainError("invalid_field", "enabled")
        allowed_members = value["eligible"]
        if not isinstance(allowed_members, list) or len(allowed_members) > 50:
            raise DomainError("invalid_field", "eligible")
        value["eligible"] = [eligible(ctx, member)["id"] for member in allowed_members]
        if len(set(value["eligible"])) != len(value["eligible"]):
            raise DomainError("invalid_field", "eligible")
        if not previous:
            value.update(
                id=ctx.identifier("R"), creator=ctx.actor_id, created_at=ctx.now.isoformat()
            )
        else:
            value["id"] = previous["id"]
        ctx.state["rewards"][value["id"]] = ctx.touch(value)
        return value
    if action == "reward_request":
        fields(payload, {"id", "revision", "member", "note"}, {"id", "revision"})
        reward = referenced(ctx, "rewards", payload)
        member = eligible(ctx, payload.get("member", ctx.actor_id), reward)
        if member["id"] != ctx.actor_id and not ctx.privileged:
            raise DomainError("forbidden")
        if not reward["enabled"]:
            raise DomainError("invalid_transition")
        if wallet(ctx.state, member["id"])["available"] < reward["cost"]:
            raise DomainError("insufficient_points")
        note = optional(payload.get("note", ""), "note")
        record = {
            "id": ctx.identifier("V"),
            "reward_id": reward["id"],
            "reward_revision": reward["revision"],
            "name": reward["name"],
            "description": reward["description"],
            "cost": reward["cost"],
            "member": member["id"],
            "creator": ctx.actor_id,
            "note": note,
            "created_at": ctx.now.isoformat(),
            "expires_at": (ctx.now + timedelta(hours=reward["request_ttl_hours"])).isoformat(),
        }
        history(ctx, record, "requested", note)
        ctx.state["reward_requests"][record["id"]] = record
        ctx.notify(
            "parents",
            "reward_requested",
            {"id": record["id"], "member": member["id"], "cost": record["cost"]},
        )
        return record
    if action != "reward_transition":
        raise DomainError("unknown_action")
    fields(
        payload, {"id", "revision", "decision", "reason"}, {"id", "revision", "decision", "reason"}
    )
    record = referenced(ctx, "reward_requests", payload)
    decision = enum(
        payload["decision"], {"approve", "reject", "cancel", "fulfill", "refund"}, "decision"
    )
    if not ctx.privileged and not (
        decision == "cancel"
        and record["member"] == ctx.actor_id
        and record["status"] == "requested"
    ):
        raise DomainError("forbidden")
    reason = text(payload["reason"], "reason")
    transitions = {
        "approve": ({"requested"}, "approved"),
        "reject": ({"requested"}, "rejected"),
        "cancel": ({"requested", "approved"}, "cancelled"),
        "fulfill": ({"approved"}, "fulfilled"),
        "refund": ({"fulfilled"}, "refunded"),
    }
    origins, target = transitions[decision]
    if record["status"] not in origins:
        raise DomainError("invalid_transition")
    if decision == "approve":
        eligible(ctx, record["member"])
        if ctx.now >= timestamp(record["expires_at"], "expires_at"):
            raise DomainError("reward_expired")
        if wallet(ctx.state, record["member"])["net"] < 0:
            raise DomainError("insufficient_points")
    history(ctx, record, target, reason)
    supersede(ctx, record)
    ctx.notify(
        record["member"], "reward_changed", {"id": record["id"], "status": target, "reason": reason}
    )
    return record


def tick(ctx):
    # Even a disabled module must release obsolete reservations, without new messages.
    enabled = "court" in ctx.state["settings"]["modules"]
    for request in ctx.state["reward_requests"].values():
        if request["status"] != "requested" or ctx.now < timestamp(
            request["expires_at"], "expires_at"
        ):
            continue
        history(ctx, request, "expired", "")
        supersede(ctx, request)
        if enabled:
            ctx.notify(request["member"], "reward_expired", {"id": request["id"]})
