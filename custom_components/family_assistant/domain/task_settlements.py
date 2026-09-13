"""Opt-in one-off child-task settlements, committed with their exact score receipt.

No transport I/O, retroactive catch-up loop, or member-name based score lookup.
The original receipt survives correction; only its separate decision changes.
"""

from copy import deepcopy
from datetime import timedelta
from zoneinfo import ZoneInfo

from ..const import PRIVILEGED
from . import penalties, recurrence, task_access
from .context import Context
from .validation import DomainError, fields, revision, text, timestamp

DEFAULTS = {
    "daily_rollover": False,
    "settle_time": "20:00",
    "repeat_penalty": False,
    "same_day_correction": False,
}
OPEN = {"assigned", "accepted", "in_progress", "needs_changes"}
EVENTS = {"task_rollover"}
MAX_SETTLEMENT_RECEIPTS = 366


def supported(state, item):
    member = state["members"].get(item.get("assignee"), {})
    return (
        not task_access.private_task(item)
        and not item.get("source")
        and not item.get("series_id")
        and not item.get("occurrence_id")
        and member.get("active") is True
        and member.get("role") == "child"
        and member.get("revision") == item.get("assignee_revision")
    )


def configure(ctx, item, value):
    ctx.require_parent()
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "missed_policy")
    fields(value, set(DEFAULTS), set(DEFAULTS))
    policy = deepcopy(value)
    for key in ("daily_rollover", "repeat_penalty", "same_day_correction"):
        if type(policy[key]) is not bool:
            raise DomainError("invalid_field", "missed_policy")
    recurrence.clock(policy["settle_time"])
    if not supported(ctx.state, item) or not item.get("due_at"):
        raise DomainError("invalid_field", "missed_policy")
    if policy["daily_rollover"] and len(item.get("missed_receipts", {})) >= MAX_SETTLEMENT_RECEIPTS:
        raise DomainError("invalid_transition", "settlement_capacity")
    if not policy["daily_rollover"] and (policy["repeat_penalty"] or policy["same_day_correction"]):
        raise DomainError("invalid_field", "missed_policy")
    if policy == item.get("missed_policy") and current(ctx.state, item):
        return
    revoke(ctx, item)
    item["missed_policy"] = policy
    item["missed_generation"] = item.get("missed_generation", 0) + 1
    item.setdefault("missed_original_due_at", item["due_at"])
    item["missed_scope"] = {
        "generation": item["missed_generation"],
        "policy": deepcopy(policy),
        "actor": ctx.actor_id,
        "actor_revision": ctx.actor["revision"],
        "member": item["assignee"],
        "member_revision": ctx.member(item["assignee"])["revision"],
        "timezone": ctx.state["settings"].get("timezone", "UTC"),
        "effective_at": ctx.now.isoformat(),
        "state": "active" if policy["daily_rollover"] else "disabled",
    }


def managed(item):
    return item.get("missed_policy", {}).get("daily_rollover") is True


def current(state, item, *, active=True):
    scope = item.get("missed_scope", {})
    actor = state["members"].get(scope.get("actor"), {})
    return (
        "tasks" in state["settings"]["modules"]
        and supported(state, item)
        and managed(item)
        and (not active or scope.get("state") == "active")
        and scope.get("generation") == item.get("missed_generation")
        and scope.get("policy") == item.get("missed_policy")
        and scope.get("member") == item.get("assignee")
        and scope.get("member_revision") == item.get("assignee_revision")
        and scope.get("timezone") == state["settings"].get("timezone", "UTC")
        and actor.get("active") is True
        and actor.get("role") in PRIVILEGED
        and scope.get("actor_revision") == actor.get("revision")
    )


def revoke(ctx, item):
    if isinstance(item.get("missed_scope"), dict):
        # Preserve the truthful terminal capacity reason across scheduler ticks
        # and unrelated revocations. Only explicit reconfiguration replaces it.
        if item["missed_scope"].get("state") != "needs_review":
            item["missed_scope"]["state"] = "revoked"
    for event in ctx.state["outbox"].values():
        if (
            event["key"] in EVENTS
            and event["data"].get("id") == item["id"]
            and event["state"] in {"pending", "awaiting_channel"}
        ):
            event["state"] = "superseded"


def _at(day, deadline, zone):
    result = recurrence.local_clock(day, deadline.strftime("%H:%M"), zone)
    return (
        result + timedelta(seconds=deadline.second, microseconds=deadline.microsecond)
        if result
        else None
    )


def _settle_at(item, deadline, zone):
    cutoff = recurrence.local_clock(deadline.date(), item["missed_policy"]["settle_time"], zone)
    return (
        max(deadline + timedelta(minutes=item["deadline_policy"]["grace_minutes"]), cutoff)
        if cutoff
        else None
    )


def _award(ctx, item, receipt):
    config = ctx.state["settings"]
    if "court" not in config["modules"] or not config.get("automatic_penalties"):
        return "skipped_disabled", None
    points = item["deadline_policy"]["penalty"]
    if points >= 0:
        return "skipped_zero", None
    repeat = item["missed_policy"]["repeat_penalty"]
    # A policy toggle, edited deadline, or reassignment cannot create another
    # score for this task on the same day (including a previously reversed row).
    for event in ctx.state["court"].values():
        if (
            event.get("source") != "task"
            or event.get("reason_data", {}).get("task_id") != item["id"]
        ):
            continue
        day = (
            timestamp(event["created_at"], "created_at")
            .astimezone(ZoneInfo(receipt["timezone"]))
            .date()
            .isoformat()
        )
        if not repeat or day == receipt["settled_local_date"]:
            return "skipped_duplicate", None
    source_id = f"{item['id']}:missed:{receipt['due_local_date']}" if repeat else item["id"]
    record_id = f"task:{source_id}"
    if record_id in ctx.state["court"]:
        return "skipped_duplicate", None
    applied = penalties.award(
        ctx,
        source="task",
        source_id=source_id,
        member=receipt["member"],
        points=points,
        reason_key="task_missed",
        reason_data={
            "task_id": item["id"],
            "due_at": receipt["from_due_at"],
            "settlement_id": receipt["id"],
            "due_local_date": receipt["due_local_date"],
            "member_revision": receipt["member_revision"],
        },
        timezone=receipt["timezone"],
    )
    return ("applied", record_id) if applied else ("skipped_cap", None)


def tick(ctx, item):
    """Called instead of the legacy escalation, only for explicitly managed work."""
    if not current(ctx.state, item) or item["status"] not in OPEN:
        return
    scope = item["missed_scope"]
    zone = scope["timezone"]
    local = ctx.now.astimezone(ZoneInfo(zone))
    deadline = timestamp(item["due_at"], "due_at").astimezone(ZoneInfo(zone))
    scheduled = _settle_at(item, deadline, zone)
    if scheduled is not None and ctx.now < scheduled:
        return
    if scheduled is None and ctx.now < deadline + timedelta(
        minutes=item["deadline_policy"]["grace_minutes"]
    ):
        return  # A nonexistent spring cutoff cannot move a later deadline early.
    if len(item.get("missed_receipts", {})) >= MAX_SETTLEMENT_RECEIPTS:
        revoke(ctx, item)
        scope.update(state="needs_review", reason="settlement_capacity")
        ctx.touch(item)
        return
    start = max(deadline.date() + timedelta(days=1), local.date())
    target = None
    for offset in range(3):
        candidate = _at(start + timedelta(days=offset), deadline, zone)
        candidate_settlement = _settle_at(item, candidate, zone) if candidate else None
        if candidate_settlement and candidate_settlement > ctx.now:
            target = candidate
            break
    if target is None:
        return
    from . import task_events

    task_events.close(ctx, item)
    receipt = {
        "id": f"{item['id']}:missed:{scope['generation']}:{deadline.date().isoformat()}",
        "task_id": item["id"],
        "generation": scope["generation"],
        "policy": deepcopy(scope["policy"]),
        "actor": scope["actor"],
        "actor_revision": scope["actor_revision"],
        "member": scope["member"],
        "member_revision": scope["member_revision"],
        "timezone": zone,
        "due_local_date": deadline.date().isoformat(),
        "settled_local_date": local.date().isoformat(),
        "settled_at": ctx.now.isoformat(),
        "from_due_at": item["due_at"],
        "due_at": target.isoformat(),
        "same_day_correction": item["missed_policy"]["same_day_correction"],
        "reviewers": task_events.reviewers(ctx.state),
    }
    if scheduled is None or scheduled.date() < local.date():
        outcome, ledger_id = "skipped_outage", None
    elif deadline <= timestamp(scope["effective_at"], "effective_at"):
        outcome, ledger_id = "skipped_retroactive", None
    else:
        outcome, ledger_id = _award(ctx, item, receipt)
    receipt.update(outcome=outcome, ledger_id=ledger_id)
    if ledger_id:
        receipt["ledger_revision"] = ctx.state["court"][ledger_id]["revision"]
        receipt["points"] = ctx.state["court"][ledger_id]["points"]
    else:
        receipt["points"] = 0
    item["due_at"] = receipt["due_at"]
    item["missed_receipt"] = receipt
    item.pop("missed_correction", None)
    notifier = Context(ctx.state, ctx.actor, ctx.now, f"task-settlement:{receipt['id']}")
    receipt["event_id"] = notifier.notify(
        "parents",
        "task_rollover",
        {
            "id": item["id"],
            "settlement_id": receipt["id"],
            "member": receipt["member"],
            "member_revision": receipt["member_revision"],
            "due_at": receipt["due_at"],
            "points": receipt["points"],
            "outcome": outcome,
        },
    )
    item.setdefault("missed_receipts", {})[receipt["id"]] = deepcopy(receipt)
    ctx.touch(item)


def _candidate(state, item):
    receipt = item.get("missed_receipt", {})
    if (
        item.get("status") != "completed"
        or not current(state, item, active=False)
        or receipt.get("generation") != item.get("missed_generation")
        or receipt.get("member") != item.get("assignee")
        or receipt.get("member_revision") != item.get("assignee_revision")
        or not receipt.get("same_day_correction")
        or not receipt.get("ledger_id")
        or timestamp(item["closed_at"], "closed_at")
        .astimezone(ZoneInfo(receipt["timezone"]))
        .date()
        .isoformat()
        != receipt["settled_local_date"]
    ):
        return None
    return receipt


def correct(ctx, item, *, payload=None):
    """One exact automatic event; ordinary appeal review rules still apply."""
    ctx.require_parent()
    receipt = _candidate(ctx.state, item)
    if receipt is None:
        if payload is not None:
            raise DomainError("invalid_transition")
        return
    if payload is not None:
        if revision(payload["actor_revision"]) != ctx.actor["revision"]:
            raise DomainError("conflict")
        if payload["settlement_id"] != receipt["id"]:
            raise DomainError("conflict")
        expected = revision(payload["court_revision"])
        reason = text(payload["reason"], "reason", 500)
    else:
        expected = receipt["ledger_revision"]
        reason = "Parent confirmed task completion on the settlement day"
    record = ctx.state["court"].get(receipt["ledger_id"], {})
    data = record.get("reason_data", {})
    if (
        record.get("source") != "task"
        or record.get("actor") != "system"
        or record.get("member") != receipt["member"]
        or record.get("points") != receipt["points"]
        or data.get("task_id") != item["id"]
        or data.get("settlement_id") != receipt["id"]
        or data.get("due_at") != receipt["from_due_at"]
        or data.get("due_local_date") != receipt["due_local_date"]
        or data.get("member_revision") != receipt["member_revision"]
    ):
        raise DomainError("conflict")
    decision = {
        "settlement_id": receipt["id"],
        "ledger_id": record["id"],
        "actor": ctx.actor_id,
        "actor_revision": ctx.actor["revision"],
        "closed_at": item["closed_at"],
        "at": ctx.now.isoformat(),
    }
    if record.get("status") == "reversed":
        decision["state"] = "already_reversed"
    elif "court" not in ctx.state["settings"]["modules"] or expected != record.get("revision"):
        if payload is not None:
            raise DomainError("conflict")
        decision["state"] = "needs_review"
    else:
        from . import court

        try:
            court.handle(
                ctx, "reverse", {"id": record["id"], "revision": expected, "reason": reason}
            )
        except DomainError as error:
            if payload is not None or error.code != "forbidden":
                raise
            decision["state"] = "needs_review"
        else:
            record["reversal"]["source_reference"] = {
                "source": "task",
                "task_id": item["id"],
                "settlement_id": receipt["id"],
            }
            decision["state"] = "reversed"
    item["missed_correction"] = decision


def correction_payload(state, item, actor):
    receipt = _candidate(state, item)
    if not receipt:
        raise DomainError("invalid_transition")
    return {
        "id": item["id"],
        "revision": item["revision"],
        "actor_revision": actor["revision"],
        "settlement_id": receipt["id"],
        "court_revision": state["court"][receipt["ledger_id"]]["revision"],
    }


def event_current(state, event):
    item = state["tasks"].get(event.get("data", {}).get("id"), {})
    receipt = item.get("missed_receipt", {})
    from .task_events import reviewers

    return (
        event.get("key") == "task_rollover"
        and event.get("recipient") == "parents"
        and current(state, item)
        and item.get("status") in OPEN
        and receipt.get("generation") == item.get("missed_generation")
        and receipt.get("event_id") == event.get("id")
        and receipt.get("reviewers") == reviewers(state)
        and event["data"].get("settlement_id") == receipt.get("id")
        and event["data"].get("member") == receipt.get("member")
        and event["data"].get("member_revision") == receipt.get("member_revision")
        and event["data"].get("due_at") == receipt.get("due_at") == item.get("due_at")
        and event["data"].get("points") == receipt.get("points")
        and event["data"].get("outcome") == receipt.get("outcome")
    )


def project(result, *, parent):
    scope = result.pop("missed_scope", None)
    result.pop("missed_generation", None)
    result.pop("missed_receipts", None)
    receipt = result.pop("missed_receipt", None)
    correction = result.pop("missed_correction", None)
    if scope:
        result["missed_policy_status"] = scope["state"]
        if parent and scope.get("reason"):
            result["missed_policy_reason"] = scope["reason"]
    if parent and receipt:
        result["last_settlement"] = {
            key: receipt[key]
            for key in (
                "id",
                "due_local_date",
                "settled_at",
                "from_due_at",
                "due_at",
                "points",
                "outcome",
                "ledger_id",
            )
        }
        result["correction_status"] = correction["state"] if correction else None
