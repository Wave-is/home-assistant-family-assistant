"""Durable ordered routines; conditions observe but never operate HA devices."""

import secrets
from copy import deepcopy
from datetime import UTC, timedelta

from ..const import PRIVILEGED
from . import recurrence, routine_conditions, routine_templates
from .incidents import close_incident, open_incident
from .routine_validation import (
    configuration,
    normalize_template,
    validate_allowlist,
    validate_modes,
)
from .validation import DomainError, enum, fields, text, timestamp

TEMPLATE_FIELDS = {"title", "description", "assignees", "enabled", "rule", "steps", "skip_when"}


def _revision(value):
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return value


def _history(ctx, record, action, reason="", **extra):
    record.setdefault("history", []).append(
        {
            "actor": ctx.actor_id,
            "at": ctx.now.isoformat(),
            "action": action,
            "reason": reason,
            **extra,
        }
    )
    ctx.touch(record)


def _usable(state, member_id):
    member = state["members"].get(member_id, {})
    return member.get("active", False) and member.get("role") != "guest"


def _source_allowed(state, template):
    creator = state["members"].get(template["creator"], {})
    return creator.get("active", False) and creator.get("role") in PRIVILEGED


def step_member(run, step):
    """Old persisted steps inherit the run member; new runs snapshot the recipient."""
    return step.get("member") or run["member"]


def participants(run):
    return {run["member"], *(step_member(run, step) for step in run["steps"])}


def _steps_usable(state, template):
    return all(
        not step.get("assignee") or _usable(state, step["assignee"]) for step in template["steps"]
    )


def _supersede(ctx, run_id, step=None):
    for event in ctx.state["outbox"].values():
        if (
            event["key"] == "routine_step"
            and event["data"]["run_id"] == run_id
            and (step is None or event["data"]["step"] == step)
            and event["state"] not in {"sent", "resolved"}
        ):
            event["state"] = "superseded"


def _data(run, index):
    return {
        "run_id": run["id"],
        "title": run["title"],
        "member": step_member(run, run["steps"][index]),
        "step": index,
        "step_title": run["steps"][index]["title"],
    }


def _close(ctx, run, index, outcome):
    _supersede(ctx, run["id"], index)
    close_incident(
        ctx,
        f"routine:{run['id']}:{index}",
        "routine_closed",
        {**_data(run, index), "outcome": outcome},
    )


def _condition(ctx, value, observations):
    if value is None:
        return False
    allowed = configuration(ctx.state)["entity_allowlist"]
    # Revoked observation access never permits a condition using old cached state.
    safe = {key: value for key, value in observations.items() if key in allowed}
    return routine_conditions.evaluate(
        value, now=ctx.now, modes=configuration(ctx.state)["modes"], observations=safe
    )


def _advance(ctx, run, observations):
    if run["status"] != "active":
        return
    for index, step in enumerate(run["steps"]):
        if step["status"] in {"completed", "skipped"}:
            continue
        if step["status"] == "pending":
            ready = timestamp(run["planned_at"], "planned_at").astimezone(UTC) + timedelta(
                minutes=step["offset_minutes"]
            )
            if ctx.now.astimezone(UTC) < ready:
                return
            if _condition(ctx, step["skip_when"], observations) is True:
                step.update(status="skipped", completed_at=ctx.now.isoformat())
                _history(ctx, run, "step_skipped", "condition", step=index)
                continue
            step.update(status="active", activated_at=ctx.now.isoformat())
            if step["confirmation"] == "manual":
                step["nonce"] = secrets.token_urlsafe(18)
            _history(ctx, run, "step_activated", step=index)
            if step["confirmation"] != "none":
                ctx.notify(
                    step_member(run, step),
                    "routine_step",
                    {
                        **_data(run, index),
                        "confirmation": step["confirmation"],
                        "nonce": step.get("nonce"),
                        "revision": run["revision"],
                    },
                )
        if step["confirmation"] == "none" or (
            step["confirmation"] == "entity_state"
            and _condition(ctx, step["completion_condition"], observations) is True
        ):
            step.update(status="completed", completed_at=ctx.now.isoformat())
            step.pop("nonce", None)
            _history(
                ctx,
                run,
                "step_completed",
                "condition" if step["confirmation"] != "none" else "automatic",
                step=index,
            )
            _close(ctx, run, index, "completed")
            continue
        minutes = step["escalate_minutes"]
        if minutes is not None and not step.get("escalated_at"):
            due = timestamp(step["activated_at"], "activated_at").astimezone(UTC) + timedelta(
                minutes=minutes
            )
            if ctx.now.astimezone(UTC) >= due:
                step["escalated_at"] = ctx.now.isoformat()
                open_incident(
                    ctx,
                    f"routine:{run['id']}:{index}",
                    "routine_overdue",
                    _data(run, index),
                    recipient="parents",
                )
                # Escalation does not invalidate the already delivered confirmation revision.
                run.setdefault("history", []).append(
                    {
                        "actor": "system",
                        "at": ctx.now.isoformat(),
                        "action": "step_escalated",
                        "reason": "",
                        "step": index,
                    }
                )
        return
    run.update(status="completed", completed_at=ctx.now.isoformat())
    _history(ctx, run, "completed")
    ctx.notify(run["member"], "routine_completed", {"run_id": run["id"], "title": run["title"]})


def _start(ctx, template, member, planned_at, observations):
    for existing in ctx.state["routine_runs"].values():
        if (
            existing["template_id"] == template["id"]
            and existing["member"] == member
            and existing["status"] == "active"
        ):
            return existing
    run = {
        "id": ctx.identifier("J"),
        "template_id": template["id"],
        "template_revision": template["revision"],
        "title": template["title"],
        "description": template["description"],
        "member": member,
        "planned_at": planned_at.astimezone(UTC).isoformat(),
        "started_at": ctx.now.isoformat(),
        "status": "active",
        "steps": [
            {**deepcopy(step), "member": step.get("assignee") or member, "status": "pending"}
            for step in template["steps"]
        ],
        "history": [],
    }
    ctx.state["routine_runs"][run["id"]] = run
    _history(ctx, run, "started")
    if _condition(ctx, template["skip_when"], observations) is True:
        run.update(status="skipped", completed_at=ctx.now.isoformat())
        for step in run["steps"]:
            step.update(status="skipped", completed_at=ctx.now.isoformat())
        _history(ctx, run, "skipped", "condition")
    else:
        _advance(ctx, run, observations)
    return run


def public_run(run, *, parent=False, actor_id=None):
    result = deepcopy(run)
    if not parent:
        for step in result["steps"]:
            step.pop("completion_condition", None)
            step.pop("skip_when", None)
            if step_member(run, step) != actor_id:
                step.pop("nonce", None)
    return result


def check_replay(state, actor_id, action, result):
    """Authorize historical receipts against the run's current security scope."""
    if action not in {"start", "confirm", "override", "cancel"}:
        return
    run = state["routine_runs"].get(result["id"])
    if run is None:
        raise DomainError("forbidden")
    template = state["routines"].get(run["template_id"])
    if (
        template is None
        or not _source_allowed(state, template)
        or any(not _usable(state, member) for member in participants(run))
        or (
            state["members"][actor_id]["role"] not in PRIVILEGED
            and actor_id not in participants(run)
        )
        or run.get("cancellation_cause") == "authorization_removed"
    ):
        raise DomainError("forbidden")


def _handle(ctx, action, payload):
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action in {"configure", "modes"}:
        ctx.require_parent()
        key = "entity_allowlist" if action == "configure" else "modes"
        if action == "configure" and ctx.actor["role"] != "owner":
            raise DomainError("forbidden")
        fields(payload, {key, "revision"}, {key, "revision"})
        config = configuration(ctx.state)
        revision = payload["revision"]
        if type(revision) is not int or not 0 <= revision <= 2**53 - 1:
            raise DomainError("invalid_field", "revision")
        if revision != config["revision"]:
            raise DomainError("conflict")
        config[key] = (
            validate_allowlist(payload[key])
            if action == "configure"
            else validate_modes(payload[key])
        )
        config["revision"] += 1
        ctx.state["settings"]["routines"] = config
        return config
    if action == "save":
        ctx.require_parent()
        fields(payload, TEMPLATE_FIELDS | {"id", "revision"}, {"title", "assignees", "steps"})
        if "id" in payload:
            old = ctx.record("routines", payload["id"], _revision(payload.get("revision")))
        else:
            if "revision" in payload:
                raise DomainError("invalid_field", "revision")
            old = {}
        value = {
            "description": "",
            "enabled": True,
            "rule": None,
            "skip_when": None,
            **{k: v for k, v in old.items() if k in TEMPLATE_FIELDS},
            **{k: v for k, v in payload.items() if k in TEMPLATE_FIELDS},
        }
        normalized = normalize_template(ctx, value)
        record = {
            **old,
            **normalized,
            "id": old.get("id") or ctx.identifier("U"),
            "creator": old.get("creator", ctx.actor_id),
            "effective_at": ctx.now.isoformat(),
            "occurrences": old.get("occurrences", {}),
        }
        ctx.state["routines"][record["id"]] = record
        _history(ctx, record, "saved")
        return {k: v for k, v in record.items() if k != "occurrences"}
    if action == "start":
        fields(payload, {"id", "revision", "member"}, {"id", "revision", "member"})
        template = ctx.record("routines", payload["id"], _revision(payload["revision"]))
        member = ctx.member(payload["member"])["id"]
        if not ctx.privileged and member != ctx.actor_id:
            raise DomainError("forbidden")
        if (
            member not in template["assignees"]
            or not _usable(ctx.state, member)
            or not template["enabled"]
            or not _source_allowed(ctx.state, template)
            or not _steps_usable(ctx.state, template)
        ):
            raise DomainError("invalid_transition")
        return public_run(
            _start(ctx, template, member, ctx.now, {}), parent=ctx.privileged, actor_id=ctx.actor_id
        )
    if action not in {"confirm", "override", "cancel"}:
        raise DomainError("unknown_action")
    required = {"id", "revision"} | ({"nonce", "step"} if action == "confirm" else {"reason"})
    if action == "override":
        required |= {"outcome", "step"}
    fields(payload, required, required)
    run = ctx.record("routine_runs", payload["id"], _revision(payload["revision"]))
    if not ctx.privileged and ctx.actor_id not in participants(run):
        raise DomainError("forbidden")
    if run["status"] != "active":
        raise DomainError("invalid_transition")
    if action in {"override", "cancel"}:
        ctx.require_parent()
        reason = text(payload["reason"], "reason", 500)
        if action == "cancel":
            _cancel(ctx, run, reason)
            return public_run(run, parent=True)
    index = payload["step"]
    if type(index) is not int or not 0 <= index < len(run["steps"]):
        raise DomainError("invalid_field", "step")
    step = run["steps"][index]
    if step["status"] != "active":
        raise DomainError("invalid_transition")
    if action == "confirm":
        if step_member(run, step) != ctx.actor_id or step["confirmation"] != "manual":
            raise DomainError("forbidden")
        nonce = text(payload["nonce"], "nonce", 100)
        if not secrets.compare_digest(nonce.encode(), step.get("nonce", "").encode()):
            raise DomainError("invalid_field", "nonce")
        outcome, reason = "completed", "confirmation"
    else:
        outcome = enum(payload["outcome"], {"completed", "skipped"}, "outcome")
    step.update(status=outcome, completed_at=ctx.now.isoformat())
    step.pop("nonce", None)
    _history(ctx, run, "step_" + outcome, reason, step=index)
    _close(ctx, run, index, outcome)
    _advance(ctx, run, {})
    return public_run(run, parent=ctx.privileged, actor_id=ctx.actor_id)


def handle(ctx, action, payload):
    try:
        return _handle(ctx, action, payload)
    except (OverflowError, OSError):
        raise DomainError("command_too_large") from None


def _cancel(ctx, run, reason, *, cause="manual"):
    run.update(status="cancelled", completed_at=ctx.now.isoformat(), cancellation_cause=cause)
    for index, step in enumerate(run["steps"]):
        step.pop("nonce", None)
        _close(ctx, run, index, "cancelled")
    _supersede(ctx, run["id"])
    _history(ctx, run, "cancelled", reason)


def cancel_disabled(ctx):
    for run in ctx.state["routine_runs"].values():
        if run["status"] == "active" and (
            "routines" not in ctx.state["settings"]["modules"]
            or any(not _usable(ctx.state, member) for member in participants(run))
            or not _source_allowed(ctx.state, ctx.state["routines"][run["template_id"]])
        ):
            _cancel(ctx, run, "authorization_removed", cause="authorization_removed")


def tick(ctx, observations=None):
    observations = observations if isinstance(observations, dict) else {}
    cancel_disabled(ctx)
    if "routines" not in ctx.state["settings"]["modules"]:
        return
    try:
        for template in ctx.state["routines"].values():
            if (
                not template["enabled"]
                or template["rule"] is None
                or not _source_allowed(ctx.state, template)
                or not _steps_usable(ctx.state, template)
            ):
                continue
            for moment in recurrence.due(
                template["rule"],
                ctx.now,
                not_before=timestamp(template["effective_at"], "effective_at"),
            ):
                occurrence = moment.date().isoformat()
                if occurrence in template["occurrences"]:
                    continue
                ids = []
                for member in template["assignees"]:
                    if _usable(ctx.state, member):
                        run = _start(ctx, template, member, moment, observations)
                        ids.append(run["id"])
                template["occurrences"][occurrence] = ids
            cutoff = (ctx.now.astimezone(UTC) - timedelta(days=90)).date().isoformat()
            template["occurrences"] = {
                k: v for k, v in template["occurrences"].items() if k >= cutoff
            }
        for run in ctx.state["routine_runs"].values():
            _advance(ctx, run, observations)
    except (OverflowError, OSError):
        raise DomainError("command_too_large") from None


def view(state, actor):
    parent = actor["role"] in PRIVILEGED
    templates = []
    for template in state["routines"].values():
        if parent:
            templates.append({k: deepcopy(v) for k, v in template.items() if k != "occurrences"})
        elif actor["id"] in template["assignees"]:
            templates.append(
                {
                    k: deepcopy(template[k])
                    for k in ("id", "title", "description", "enabled", "revision")
                }
            )
    config = configuration(state)
    if not parent:
        config.pop("entity_allowlist", None)
    return {
        "templates": templates,
        "presets": routine_templates.templates(actor["language"]) if parent else [],
        "config": config,
        "runs": [
            public_run(run, parent=parent, actor_id=actor["id"])
            for run in state["routine_runs"].values()
            if parent or actor["id"] in participants(run)
        ],
    }
