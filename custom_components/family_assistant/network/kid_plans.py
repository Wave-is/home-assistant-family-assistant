"""Parents' reviewed Kid Control commands; inventory administration stays owner-only."""

from datetime import timedelta

from ..const import PRIVILEGED
from ..domain.validation import DomainError, fields, text, timestamp
from . import kids


def can_manage(state, actor):
    member = state["members"].get(actor, {})
    return bool(
        member.get("active")
        and (
            member.get("role") in PRIVILEGED
            or (
                member.get("role") == "adult"
                and state["network"].get("kid_grants", {}).get(actor) is True
            )
        )
    )


def public(plan):
    return {
        key: plan.get(key)
        for key in (
            "id",
            "actor",
            "member",
            "mode",
            "status",
            "expires_at",
            "until",
            "diff",
            "warnings",
            "progress",
        )
    }


def view(state, actor):
    network = state["network"]
    managed = can_manage(state, actor)
    profiles = []
    for binding in network.get("kid_profiles", {}).values():
        if not managed and binding["member"] != actor:
            continue
        rows = [
            r
            for r in network.get("tables", {}).get("kids", [])
            if r.get(".id") == binding["profile_id"]
        ]
        observed = None
        try:
            if rows and binding.get("backend") == network.get("backend"):
                observed = kids.validate_binding(
                    network["tables"], binding, network.get("protected_macs", [])
                )
        except DomainError:
            pass
        profiles.append(
            {
                "member": binding["member"],
                "name": binding["name"],
                "observed": observed,
                "device_names": [d["name"] for d in binding["devices"]],
                "devices": binding["devices"] if managed else [],
            }
        )
    return {
        "can_manage": managed,
        "writable": network.get("kid_writable", False),
        "observed_at": network.get("inventory", {}).get("observed_at"),
        "profiles": profiles,
        "candidates": [
            {
                "id": row.get(".id"),
                "name": row.get("name"),
                "devices": [
                    {"id": d.get(".id"), "name": d.get("name"), "mac": d.get("mac-address")}
                    for d in network.get("tables", {}).get("kid_devices", [])
                    if d.get("user") == row.get("name")
                ],
            }
            for row in network.get("tables", {}).get("kids", [])
        ]
        if state["members"][actor]["role"] == "owner"
        else [],
        "delegations": network.get("kid_grants", {})
        if state["members"][actor]["role"] == "owner"
        else {},
        "plans": [
            public(p)
            for p in network.get("kid_plans", {}).values()
            if managed or p["member"] == actor
        ][-20:],
    }


def fresh(network, now):
    observed = network.get("inventory", {})
    if not observed or not timedelta(0) <= now - timestamp(
        observed["observed_at"], "observed_at"
    ) <= timedelta(minutes=3):
        raise DomainError("network_stale")


def handle(ctx, action, payload):
    network = ctx.state["network"]
    if action in {"kid_adopt", "kid_permission"}:
        if ctx.actor["role"] != "owner":
            raise DomainError("forbidden")
        if action == "kid_permission":
            fields(payload, {"member", "enabled"}, {"member", "enabled"})
            member = ctx.member(payload["member"])
            if member["role"] != "adult" or type(payload["enabled"]) is not bool:
                raise DomainError("invalid_field", "member")
            network.setdefault("kid_grants", {})[member["id"]] = payload["enabled"]
            return {"id": member["id"], "enabled": payload["enabled"]}
        fields(
            payload,
            {"member", "profile_id", "devices", "confirmed"},
            {"member", "profile_id", "devices", "confirmed"},
        )
        fresh(network, ctx.now)
        member = ctx.member(payload["member"])
        if member["role"] != "child":
            raise DomainError("invalid_field", "member")
        if payload["confirmed"] is not True:
            raise DomainError("network_confirmation")
        bindings = network.setdefault("kid_profiles", {})
        if any(
            p["member"] == member["id"]
            and p["status"] in {"queued", "applying", "rolling_back", "applied"}
            and (p.get("until") or p["status"] != "applied")
            for p in network.get("kid_plans", {}).values()
        ):
            raise DomainError("network_busy")
        binding = kids.bind(
            network.get("tables", {}),
            payload["profile_id"],
            payload["devices"],
            network.get("protected_macs", []),
        )
        if any(
            b["profile_id"] == binding["profile_id"] and b["member"] != member["id"]
            for b in bindings.values()
        ):
            raise DomainError("network_conflict")
        binding.update(member=member["id"], backend=network.get("backend"))
        bindings[member["id"]] = binding
        return {"id": member["id"], "name": binding["name"], "status": "adopted"}
    if not can_manage(ctx.state, ctx.actor_id):
        raise DomainError("forbidden")
    plans = network.setdefault("kid_plans", {})
    if action == "kid_plan":
        fresh(network, ctx.now)
        member = ctx.member(payload.get("member"))
        binding = network.get("kid_profiles", {}).get(member["id"])
        if not binding:
            raise DomainError("network_kid_unmanaged")
        if binding.get("backend") != network.get("backend"):
            raise DomainError("network_conflict")
        if any(
            p["member"] == member["id"]
            and p.get("until")
            and p["status"] in {"queued", "applying", "applied"}
            for p in plans.values()
        ):
            raise DomainError("network_busy")
        result = kids.prepare(
            network.get("tables", {}),
            binding,
            payload,
            ctx.now,
            ctx.state["settings"]["timezone"],
            network.get("protected_macs", []),
        )
        result.update(
            id=ctx.identifier("K"),
            actor=ctx.actor_id,
            backend=network.get("backend"),
            status="preview",
            reason=text(payload.get("reason", "Parent command"), "reason", 300),
        )
        plans[result["id"]] = result
        return public(result)
    fields(payload, {"id", "confirmed"}, {"id"})
    plan = plans.get(payload["id"])
    if not plan:
        raise DomainError("not_found")
    if plan["actor"] != ctx.actor_id:
        raise DomainError("forbidden")
    if plan["status"] != "preview":
        raise DomainError("invalid_transition")
    if action == "kid_cancel":
        plan["status"] = "cancelled"
        return public(plan)
    if action != "kid_apply":
        raise DomainError("unknown_action")
    if ctx.now >= timestamp(plan["expires_at"], "expires_at"):
        raise DomainError("proposal_expired")
    if not network.get("kid_writable"):
        raise DomainError("network_readonly")
    if plan["backend"] != network.get("backend"):
        raise DomainError("network_conflict")
    if payload.get("confirmed") is not True:
        raise DomainError("network_confirmation")
    if any(
        p["status"] in {"queued", "applying", "rolling_back"}
        for p in [*plans.values(), *network.get("plans", {}).values()]
    ):
        raise DomainError("network_busy")
    if plan["until"] and ctx.now >= timestamp(plan["until"], "until") - timedelta(seconds=30):
        raise DomainError("proposal_expired")
    plan["status"] = "queued"
    return public(plan)
