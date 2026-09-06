"""Bounded, read-only interpretation of the last verified router observation.

This predicts configured permission, never connectivity. Historical profile data
is retained separately; stale, changing or unreconciled observations are unknown.
"""

from datetime import timedelta
from math import ceil

from ..domain.validation import DomainError, timestamp
from . import kids
from .kid_status import schedule_status


def _unknown(reason):
    return {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
        "temporary_until": None,
        "temporary_mode": None,
        "valid_until": None,
        "reason": reason,
    }


def status(state, binding, observed, now):
    """Project one authorized binding without disclosing journal or device IDs."""
    if "mikrotik" not in state["settings"]["modules"]:
        return _unknown("module_disabled")
    if observed is None:
        return _unknown("unverified")
    network = state["network"]
    try:
        now = timestamp(now, "now")
        seen = timestamp(network.get("inventory", {}).get("observed_at"), "observed_at")
        if not timedelta(0) <= now - seen <= timedelta(minutes=3):
            return _unknown("stale")
    except DomainError:
        return _unknown("stale")
    timezone = state["settings"]["timezone"]
    try:
        # Compare the sampled router clock to the sample time, not the read time.
        kids.router_clock(network.get("tables", {}), seen, timezone)
    except DomainError:
        return _unknown("clock")
    plans = [
        p
        for p in network.get("kid_plans", {}).values()
        if p.get("member") == binding["member"]
        and p.get("binding") == binding
        and p.get("backend") == network.get("backend")
        and p.get("status") not in {"preview", "cancelled", "failed"}
    ]
    result = {
        **schedule_status(observed, now, timezone),
        "temporary_until": None,
        "temporary_mode": None,
        "reason": "fresh",
        "valid_until": (seen + timedelta(minutes=3)).isoformat(),
    }
    if result["mode"] == "unknown":
        return _unknown("unverified")
    if plans:
        plan = plans[-1]
        phase = plan.get("status")
        if phase in {"queued", "applying", "rolling_back", "review_required"}:
            return _unknown("changing")
        try:
            changed = plan.get("updated_at")
            if changed and timestamp(changed, "updated_at") > seen:
                return _unknown("changing")
            if phase == "applied" and plan.get("until"):
                until = timestamp(plan["until"], "until")
                if now >= until:
                    # A timer deadline alone is not evidence the native guard ran.
                    if seen < until or observed != plan["before"]:
                        return _unknown("expiry_pending")
                elif observed == plan["before"] and observed != plan["after"]:
                    # A reboot can end an exception early; show actual observed config.
                    pass
                elif (
                    observed != plan["after"]
                    or plan.get("progress", {}).get("phase") != "verified"
                    or plan.get("progress", {}).get("timer_verified") is not True
                ):
                    return _unknown("changing")
                else:
                    result.update(temporary_until=until.isoformat(), temporary_mode=plan["mode"])
                    restored = schedule_status(plan["before"], until, timezone)
                    if restored["allows"] is None:
                        result.update(next_change_at=None, next_allows=None)
                    elif restored["allows"] != result["allows"]:
                        result.update(
                            next_change_at=until.isoformat(), next_allows=restored["allows"]
                        )
                    else:
                        result.update(
                            next_change_at=restored["next_change_at"],
                            next_allows=restored["next_allows"],
                        )
                    result["valid_until"] = min(
                        timestamp(result["valid_until"], "valid_until"), until
                    ).isoformat()
        except (DomainError, KeyError, TypeError):
            return _unknown("unverified")
    if result["next_change_at"]:
        next_time = timestamp(result["next_change_at"], "next_change_at")
        result["valid_until"] = min(
            timestamp(result["valid_until"], "valid_until"), next_time
        ).isoformat()
        result["remaining_minutes"] = (
            ceil((next_time - now).total_seconds() / 60) if result["allows"] else None
        )
    else:
        result["remaining_minutes"] = None
    return result
