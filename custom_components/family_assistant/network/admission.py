"""Owner-reviewed local device approvals; no router effect or enforcement.

An HA name match is evidence, not admission. These plans modify only the private
Family Assistant ledger. Strict blocking (quarantine / allowlist enforcement)
requires explicit topology evidence recorded via the ``network_record_strict_evidence``
action before activation is permitted.  See network/strict_preconditions.py.
"""

import re
from copy import deepcopy
from datetime import timedelta

from ..domain.validation import DomainError, fields, revision, text, timestamp
from .admission_inventory import classify, observation_token
from .inventory import mac
from .strict_preconditions import public_status as strict_status
from .strict_preconditions import record_evidence as _record_evidence

PREFIX = "admission_"
MAX_PLANS = 1000
MAX_ENTRIES = 1000


def _actor(ctx, payload):
    if "mikrotik" not in ctx.state["settings"]["modules"]:
        raise DomainError("module_disabled")
    current = ctx.state["members"].get(ctx.actor_id)
    if not current or current.get("active") is not True or current.get("role") != "owner":
        raise DomainError("forbidden")
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if revision(payload.get("actor_revision")) != revision(current.get("revision")):
        raise DomainError("conflict")
    return current


def _policy(network):
    value = network.get("admission")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DomainError("network_response")
    fields(
        value,
        {"backend", "revision", "entries", "updated_at"},
        {"backend", "revision", "entries", "updated_at"},
    )
    revision(value["revision"])
    timestamp(value["updated_at"], "updated_at")
    if not isinstance(value["backend"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["backend"]):
        raise DomainError("network_response")
    entries = value["entries"]
    if not isinstance(entries, dict) or len(entries) > MAX_ENTRIES:
        raise DomainError("network_response")
    for key, entry in entries.items():
        if not isinstance(key, str) or mac(key) != key or not isinstance(entry, dict):
            raise DomainError("network_response")
        fields(entry, {"label"}, {"label"})
        if text(entry["label"], "label", 160) != entry["label"]:
            raise DomainError("network_response")
    return value


def _plans(network):
    plans = network.get("admission_plans", {})
    if not isinstance(plans, dict):
        raise DomainError("network_response")
    return plans


def public(plan):
    return deepcopy(
        {
            key: plan[key]
            for key in (
                "id",
                "status",
                "created_at",
                "expires_at",
                "policy_revision",
                "changes",
                "backend_changed",
            )
        }
    )


def _current_plan(ctx, payload):
    network = ctx.state["network"]
    plan = _plans(network).get(text(payload.get("id"), "id", 80))
    if not isinstance(plan, dict):
        raise DomainError("not_found")
    if (
        plan.get("actor") != ctx.actor_id
        or revision(plan.get("actor_revision")) != ctx.actor["revision"]
    ):
        raise DomainError("forbidden")
    if plan.get("backend") != network.get("backend"):
        raise DomainError("network_conflict")
    return plan


def handle(ctx, action, payload):
    if action == "network_record_strict_evidence":
        # Owner-only action; auth and payload validation are inside the module.
        return _record_evidence(ctx, payload)
    actor = _actor(ctx, payload)
    network = ctx.state["network"]
    if action == "admission_preview":

        fields(
            payload,
            {
                "actor_revision",
                "observation_token",
                "policy_revision",
                "changes",
                "replace_backend",
            },
            {"actor_revision", "observation_token", "policy_revision", "changes"},
        )
        if payload["policy_revision"] is not None:
            revision(payload["policy_revision"])
        current_token = observation_token(network, ctx.now)
        if payload["observation_token"] != current_token:
            raise DomainError("network_conflict")
        old = _policy(network)
        if payload["policy_revision"] != (old["revision"] if old else None):
            raise DomainError("conflict")
        backend_changed = old is not None and old["backend"] != network["backend"]
        replace_backend = payload.get("replace_backend", False)
        if type(replace_backend) is not bool:
            raise DomainError("invalid_field", "replace_backend")
        if backend_changed and not replace_backend:
            raise DomainError("network_confirmation")
        if replace_backend and not backend_changed:
            raise DomainError("invalid_field", "replace_backend")
        # Approvals from another router remain in the old record until explicitly
        # replaced. They never silently authorize clients on this backend.
        existing = old["entries"] if old and old["backend"] == network["backend"] else {}
        classified = classify(network, ctx.now)
        devices = {item["mac"]: item for item in classified["devices"]}
        requested = payload["changes"]
        if not isinstance(requested, list) or not 1 <= len(requested) <= 100:
            raise DomainError("invalid_field", "changes")
        changes, seen = [], set()
        for item in requested:
            if not isinstance(item, dict):
                raise DomainError("invalid_field", "changes")
            fields(item, {"mac", "approved", "label"}, {"mac", "approved"})
            identity = item["mac"]
            if not isinstance(identity, str) or mac(identity) != identity or identity in seen:
                raise DomainError("invalid_field", "mac")
            seen.add(identity)
            if type(item["approved"]) is not bool:
                raise DomainError("invalid_field", "approved")
            observed = devices.get(identity)
            if identity in {mac(value) for value in network.get("protected_macs", [])} or (
                observed and observed["status"] == "protected"
            ):
                raise DomainError("network_protected")
            before = deepcopy(existing.get(identity))
            if item["approved"]:
                if observed is None:
                    raise DomainError("network_conflict")
                after = {"label": text(item.get("label"), "label", 160)}
            else:
                if "label" in item:
                    raise DomainError("invalid_field", "label")
                if before is None:
                    raise DomainError("not_found")
                after = None
            if before == after:
                raise DomainError("invalid_transition")
            changes.append({"mac": identity, "before": before, "after": after})
        if len(_plans(network)) >= MAX_PLANS:
            raise DomainError("capacity_reached")
        plan = {
            "id": ctx.identifier("NA"),
            "status": "preview",
            "actor": ctx.actor_id,
            "actor_revision": actor["revision"],
            "backend": network["backend"],
            "observation_token": current_token,
            "policy_revision": payload["policy_revision"],
            "backend_changed": backend_changed,
            "created_at": ctx.now.isoformat(),
            "expires_at": (ctx.now + timedelta(minutes=2)).isoformat(),
            "changes": changes,
        }
        network.setdefault("admission_plans", {})[plan["id"]] = plan
        return public(plan)

    if action not in {"admission_apply", "admission_cancel"}:
        raise DomainError("unknown_action")
    allowed = {"id", "actor_revision"} | ({"confirmed"} if action == "admission_apply" else set())
    fields(payload, allowed, allowed)
    plan = _current_plan(ctx, payload)
    if plan["status"] != "preview":
        raise DomainError("invalid_transition")
    if action == "admission_cancel":
        plan["status"] = "cancelled"
        return {"id": plan["id"], "status": "cancelled"}
    if payload["confirmed"] is not True:
        raise DomainError("network_confirmation")
    if ctx.now >= timestamp(plan["expires_at"], "expires_at"):
        raise DomainError("proposal_expired")
    if observation_token(network, ctx.now) != plan["observation_token"]:
        raise DomainError("network_conflict")
    old = _policy(network)
    previous = old["revision"] if old else None
    if previous != plan["policy_revision"]:
        raise DomainError("conflict")
    if previous == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    entries = deepcopy(old["entries"]) if old and old["backend"] == plan["backend"] else {}
    for change in plan["changes"]:
        if entries.get(change["mac"]) != change["before"]:
            raise DomainError("network_conflict")
        if change["after"] is None:
            entries.pop(change["mac"])
        else:
            entries[change["mac"]] = deepcopy(change["after"])
    if len(entries) > MAX_ENTRIES:
        raise DomainError("capacity_reached")
    if plan["backend_changed"]:
        archives = network.setdefault("admission_archives", [])
        if not isinstance(archives, list) or len(archives) >= 50:
            raise DomainError("capacity_reached")
        archives.append(
            {"policy": deepcopy(old), "archived_at": ctx.now.isoformat(), "plan": plan["id"]}
        )
    network["admission"] = {
        "backend": plan["backend"],
        "revision": (previous or 0) + 1,
        "entries": entries,
        "updated_at": ctx.now.isoformat(),
    }
    _policy(network)
    plan["status"] = "applied"
    plan["result_revision"] = network["admission"]["revision"]
    return {"id": plan["id"], "status": "applied", "revision": plan["result_revision"]}


def authorize_replay(ctx, action, payload, result):
    _actor(ctx, payload)
    if not isinstance(result, dict):
        raise DomainError("forbidden")
    plan = _current_plan(ctx, {"id": result.get("id")})
    if action == "admission_preview":
        if result != public(plan) or plan["status"] != "preview":
            raise DomainError("conflict")
        policy = _policy(ctx.state["network"])
        if (policy["revision"] if policy else None) != plan["policy_revision"]:
            raise DomainError("conflict")
        if (
            ctx.now >= timestamp(plan["expires_at"], "expires_at")
            or observation_token(ctx.state["network"], ctx.now) != plan["observation_token"]
        ):
            raise DomainError("proposal_expired")
    elif action == "admission_apply":
        policy = _policy(ctx.state["network"])
        if (
            plan["status"] != "applied"
            or policy is None
            or revision(result.get("revision")) != policy["revision"]
            or plan.get("result_revision") != policy["revision"]
        ):
            raise DomainError("conflict")
        if result != {"id": plan["id"], "status": "applied", "revision": policy["revision"]}:
            raise DomainError("conflict")
    elif action == "admission_cancel":
        if plan["status"] != "cancelled" or result != {"id": plan["id"], "status": "cancelled"}:
            raise DomainError("conflict")
    else:
        raise DomainError("unknown_action")


def view(state, actor, now):
    if "mikrotik" not in state["settings"]["modules"] or actor.get("role") not in {
        "owner",
        "parent",
    }:
        return None
    current = state["members"].get(actor["id"])
    if (
        not current
        or current.get("active") is not True
        or current.get("revision") != actor.get("revision")
        or current.get("role") != actor.get("role")
    ):
        return None
    network = state["network"]
    result = classify(network, now)
    try:
        policy = _policy(network)
        plans = []
        for plan in _plans(network).values():
            if not isinstance(plan, dict):
                raise DomainError("network_response")
            if (
                plan.get("actor") != actor["id"]
                or revision(plan.get("actor_revision")) != revision(actor["revision"])
                or plan.get("backend") != network.get("backend")
            ):
                continue
            item = public(plan)
            item["applicable"] = (
                plan["status"] == "preview"
                and result["status"] == "fresh"
                and result["token"] == plan["observation_token"]
                and (policy["revision"] if policy else None) == plan["policy_revision"]
                and now < timestamp(plan["expires_at"], "expires_at")
            )
            plans.append(item)
    except (DomainError, KeyError, TypeError, ValueError):
        return {"status": "unavailable", "devices": [], "plans": [], "can_edit": False}
    result.update(
        policy_revision=policy["revision"] if policy else None,
        backend_changed=bool(policy and policy["backend"] != network.get("backend")),
        can_edit=actor["role"] == "owner" and result["status"] == "fresh",
        mode="audit_only",
        enforcement=False,
        plans=plans[-20:],
        **strict_status(state, now),
    )
    return result
