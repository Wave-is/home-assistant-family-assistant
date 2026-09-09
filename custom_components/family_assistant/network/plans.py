"""Owner-reviewed network changes; no RouterOS call runs inside a Store transaction."""

from datetime import timedelta

from ..domain.validation import DomainError, fields, timestamp
from .leases import preview


def public(plan):
    return {
        "id": plan["id"],
        "status": plan["status"],
        "expires_at": plan["expires_at"],
        "requires_dhcp_recovery_consent": plan["requires_dhcp_recovery_consent"],
        "targets": [
            {
                "id": t["id"],
                "mac": t["mac"],
                "address": t["address"],
                "server": t["server"],
                "old_comment": t["before"].get("comment", ""),
                "comment": t["comment"],
                "convert": t["convert"],
                "changed": t["changed"],
                "warnings": t["warnings"],
            }
            for t in plan["targets"]
        ],
        "progress": plan.get("progress"),
    }


def handle(ctx, action, payload):
    if action == "admission_watch_set":
        from . import watch

        return watch.handle(ctx, payload)
    if action == "network_record_strict_evidence":
        from . import admission

        return admission.handle(ctx, action, payload)
    if action.startswith("admission_"):
        from . import admission

        return admission.handle(ctx, action, payload)
    if action.startswith("kid_"):
        from .kid_plans import handle as handle_kid

        return handle_kid(ctx, action, payload)
    # Parents manage child access; bulk router administration is owner-only.
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    network = ctx.state["network"]
    plans = network.setdefault("plans", {})
    if action == "lease_plan":
        fields(payload, {"leases"}, {"leases"})
        observed = network.get("inventory", {})
        if not observed or ctx.now - timestamp(observed["observed_at"], "observed_at") > timedelta(
            minutes=3
        ):
            raise DomainError("network_stale")
        result = preview(
            network.get("tables", {}),
            payload["leases"],
            ctx.now,
            protected_macs=network.get("protected_macs", []),
        )
        result.update(
            id=ctx.identifier("N"),
            actor=ctx.actor_id,
            status="preview",
            backend=network.get("backend"),
        )
        plans[result["id"]] = result
        return public(result)
    fields(payload, {"id", "confirmed", "dhcp_recovery"}, {"id"})
    plan = plans.get(payload["id"])
    if plan is None:
        raise DomainError("not_found")
    if plan["actor"] != ctx.actor_id:
        raise DomainError("forbidden")
    if plan["status"] != "preview":
        raise DomainError("invalid_transition")
    if action == "lease_cancel":
        plan["status"] = "cancelled"
        return public(plan)
    if action != "lease_apply":
        raise DomainError("unknown_action")
    if ctx.now >= timestamp(plan["expires_at"], "expires_at"):
        raise DomainError("proposal_expired")
    if not network.get("writable"):
        raise DomainError("network_readonly")
    if not network.get("backend") or plan["backend"] != network["backend"]:
        raise DomainError("network_conflict")
    if payload.get("confirmed") is not True:
        raise DomainError("network_confirmation")
    if plan["requires_dhcp_recovery_consent"] and payload.get("dhcp_recovery") is not True:
        raise DomainError("network_recovery_consent")
    if any(
        p["status"] in {"queued", "applying", "rolling_back"}
        for p in [*plans.values(), *network.get("kid_plans", {}).values()]
    ):
        raise DomainError("network_busy")
    plan.update(status="queued", dhcp_recovery=payload.get("dhcp_recovery") is True)
    return public(plan)
