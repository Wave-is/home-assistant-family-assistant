"""Recurring duties create ordinary, independently reviewable task instances."""

from copy import deepcopy
from datetime import timedelta

from ..const import PRIVILEGED
from . import recurrence, task_events
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

LINEAGE_FIELDS = {"actor_revision", "creator_revision", "assignee_revisions"}


def _current_actor(ctx: Context, value) -> None:
    expected = strict_revision(value)
    if strict_revision(ctx.actor.get("revision")) != expected:
        raise DomainError("conflict")


def _current_creator(ctx: Context, creator_id: str, value) -> int:
    expected = strict_revision(value)
    creator = ctx.state.get("members", {}).get(creator_id)
    if (
        not isinstance(creator, dict)
        or not creator.get("active", False)
        or creator.get("role") not in PRIVILEGED
    ):
        raise DomainError("conflict")
    if strict_revision(creator.get("revision")) != expected:
        raise DomainError("conflict")
    return expected


def _current_assignees(ctx: Context, members, revisions) -> tuple[list[str], dict[str, int]]:
    if (
        not isinstance(members, list)
        or not 1 <= len(members) <= 20
        or any(not isinstance(member, str) for member in members)
        or len(set(members)) != len(members)
        or not isinstance(revisions, dict)
        or set(revisions) != set(members)
    ):
        raise DomainError("invalid_field", "assignees")
    result = {}
    for member_id in members:
        expected = strict_revision(revisions[member_id])
        member = ctx.member(member_id)
        if member["role"] == "guest":
            raise DomainError("invalid_field", "assignees")
        if strict_revision(member.get("revision")) != expected:
            raise DomainError("conflict")
        result[member_id] = expected
    return list(members), result


def generic_series_current(state: dict, series: dict) -> bool:
    """Require the exact reviewed creator and assignee identity epochs."""
    try:
        if not isinstance(series, dict):
            return False
        creator_id = series.get("creator")
        creator = state.get("members", {}).get(creator_id)
        assignees = series.get("assignees")
        revisions = series.get("assignee_revisions")
        if (
            not isinstance(creator, dict)
            or not creator.get("active", False)
            or creator.get("role") not in PRIVILEGED
            or strict_revision(creator.get("revision"))
            != strict_revision(series.get("creator_revision"))
            or not isinstance(assignees, list)
            or not 1 <= len(assignees) <= 20
            or any(not isinstance(member_id, str) for member_id in assignees)
            or len(set(assignees)) != len(assignees)
            or not isinstance(revisions, dict)
            or set(revisions) != set(assignees)
        ):
            return False
        for member_id in assignees:
            member = state.get("members", {}).get(member_id)
            if (
                not isinstance(member, dict)
                or not member.get("active", False)
                or member.get("role") == "guest"
                or strict_revision(member.get("revision"))
                != strict_revision(revisions.get(member_id))
            ):
                return False
    except (DomainError, TypeError):
        return False
    return True


def series_current(state: dict, series: dict) -> bool:
    """Return the authoritative source/identity state for either series kind."""
    from .maintenance import is_managed_series
    from .maintenance import series_current as maintenance_current

    return (
        maintenance_current(state, series)
        if is_managed_series(series)
        else generic_series_current(state, series)
    )


def public_record(state: dict, series: dict, *, parent: bool) -> dict:
    """Project lineage only to parents; expose one derived current bit to all viewers."""
    result = deepcopy(series)
    result["current"] = series_current(state, series)
    if not parent:
        for key in {
            "creator",
            "creator_revision",
            "assignee_revisions",
            "cursor",
            "occurrences",
        }:
            result.pop(key, None)
    return result


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Return a frozen receipt only to its still-current privileged reviewer."""
    ctx.require_parent()
    if action not in {"series_save", "series_enable"}:
        raise DomainError("unknown_action")
    if not isinstance(payload, dict) or not isinstance(result, dict):
        raise DomainError("invalid_field", "payload")
    _current_actor(ctx, payload.get("actor_revision"))
    text(result.get("id"), "id", 80)
    strict_revision(result.get("revision"))
    if action == "series_enable" and type(result.get("enabled")) is not bool:
        raise DomainError("invalid_field", "enabled")


def handle(ctx, action, payload, *, _maintenance=False):
    ctx.require_parent()
    from .maintenance import is_managed_series

    target_id = payload.get("id")
    existing_target = (
        ctx.state["task_series"].get(target_id) if isinstance(target_id, str) else None
    )
    if is_managed_series(existing_target) and not _maintenance:
        raise DomainError("forbidden")
    if action == "series_enable":
        allowed = {"id", "enabled", "revision"} | (set() if _maintenance else {"actor_revision"})
        fields(payload, allowed, allowed)
        if not _maintenance:
            _current_actor(ctx, payload["actor_revision"])
        if type(payload["revision"]) is not int or payload["revision"] < 1:
            raise DomainError("invalid_field", "revision")
        if type(payload["enabled"]) is not bool:
            raise DomainError("invalid_field", "enabled")
        item = ctx.record("task_series", payload["id"], payload["revision"])
        if not _maintenance and payload["enabled"] and not generic_series_current(ctx.state, item):
            raise DomainError("conflict")
        item["enabled"] = payload["enabled"]
        item["effective_at"] = ctx.now.isoformat()
        return ctx.touch(item)
    if action != "series_save":
        raise DomainError("unknown_action")
    allowed = {
        "id",
        "revision",
        "title",
        "assignees",
        "rotation",
        "rule",
        "due_time",
        "report_type",
        "checklist",
        "enabled",
        "reminder_minutes",
        "grace_minutes",
        "penalty",
    }
    required = {"title", "assignees", "rule", "due_time"}
    if not _maintenance:
        allowed |= LINEAGE_FIELDS
        required |= LINEAGE_FIELDS
    fields(
        payload,
        allowed,
        required,
    )
    if not _maintenance:
        _current_actor(ctx, payload["actor_revision"])
    series_id = payload.get("id")
    revision = payload.get("revision")
    if "id" in payload:
        if type(revision) is not int or revision < 1:
            raise DomainError("invalid_field", "revision")
        existing = ctx.record("task_series", series_id, revision)
    else:
        if "revision" in payload:
            raise DomainError("invalid_field", "revision")
        existing = {}
    members = payload["assignees"]
    if _maintenance:
        if (
            not isinstance(members, list)
            or not 1 <= len(members) <= 20
            or any(not isinstance(member, str) for member in members)
            or len(set(members)) != len(members)
        ):
            raise DomainError("invalid_field", "assignees")
        member_revisions = {}
        for member_id in members:
            member = ctx.member(member_id)
            if member["role"] == "guest":
                raise DomainError("invalid_field", "assignees")
            member_revisions[member_id] = strict_revision(member.get("revision"))
        members = list(members)
    else:
        members, member_revisions = _current_assignees(ctx, members, payload["assignee_revisions"])
        creator_id = existing.get("creator", ctx.actor_id)
        creator_revision = _current_creator(ctx, creator_id, payload["creator_revision"])
    rotation = payload.get("rotation", existing.get("rotation", False))
    enabled = payload.get("enabled", existing.get("enabled", True))
    if type(rotation) is not bool or type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")
    report_type = payload.get("report_type", existing.get("report_type", "text"))
    if report_type not in {"text", "photo", "none"}:
        raise DomainError("invalid_field", "report_type")
    checklist = payload.get("checklist", existing.get("checklist", []))
    if not isinstance(checklist, list) or len(checklist) > 50:
        raise DomainError("invalid_field", "checklist")
    item = {
        **existing,
        "id": existing.get("id") or ctx.identifier("D"),
        "creator": existing.get("creator", ctx.actor_id),
        "title": text(payload["title"], "title"),
        "assignees": list(members),
        "rotation": rotation,
        "enabled": enabled,
        "rule": recurrence.validate(payload["rule"]),
        "due_time": recurrence.clock(payload["due_time"]),
        "report_type": report_type,
        "checklist": [text(t, "checklist", 200) for t in checklist],
        "deadline_policy": task_events.policy(ctx, payload, existing.get("deadline_policy")),
        "effective_at": ctx.now.isoformat(),
        "cursor": existing.get("cursor", 0),
        "occurrences": existing.get("occurrences", {}),
    }
    if not _maintenance:
        item["creator_revision"] = creator_revision
        item["assignee_revisions"] = member_revisions
    else:
        item.pop("creator_revision", None)
        item.pop("assignee_revisions", None)
    ctx.state["task_series"][item["id"]] = ctx.touch(item)
    return item


def tick(ctx):
    from .maintenance import is_managed_series
    from .tasks import handle as task_command

    if "tasks" not in ctx.state["settings"]["modules"]:
        return
    for series in ctx.state["task_series"].values():
        managed = is_managed_series(series)
        if not series_current(ctx.state, series):
            continue
        creator = ctx.state["members"].get(series["creator"], {})
        if (
            not series["enabled"]
            or not creator.get("active")
            or creator.get("role") not in PRIVILEGED
        ):
            continue
        for moment in recurrence.due(
            series["rule"], ctx.now, not_before=timestamp(series["effective_at"], "effective_at")
        ):
            occurrence_id = moment.date().isoformat()
            if occurrence_id in series["occurrences"]:
                continue
            available = [
                m
                for m in series["assignees"]
                if ctx.state["members"].get(m, {}).get("active")
                and ctx.state["members"][m]["role"] != "guest"
            ]
            if not available:
                continue
            selected = (
                [available[series["cursor"] % len(available)]] if series["rotation"] else available
            )
            day = moment.date() + (
                timedelta(days=1) if series["due_time"] < series["rule"]["time"] else timedelta()
            )
            deadline = recurrence.local_clock(day, series["due_time"], series["rule"]["timezone"])
            if deadline is None or deadline <= ctx.now:
                # A late restart never creates a task already overdue and immediately punishes it.
                series["occurrences"][occurrence_id] = {"state": "skipped_deadline", "tasks": []}
                continue
            ids = []
            for member in selected:
                child_ctx = Context(
                    ctx.state, creator, ctx.now, f"series:{series['id']}:{occurrence_id}:{member}"
                )
                task = task_command(
                    child_ctx,
                    "create",
                    {
                        "title": series["title"],
                        "assignee": member,
                        "due_at": deadline.isoformat(),
                        "report_type": series["report_type"],
                        "checklist": series["checklist"],
                        **series.get("deadline_policy", {}),
                    },
                )
                task.update(series_id=series["id"], occurrence_id=occurrence_id)
                if managed:
                    task.update(
                        delivery_scope="private",
                        source={
                            "kind": "maintenance_service",
                            "asset_id": series["source"]["asset_id"],
                            "asset_revision": series["source"]["asset_revision"],
                            "series_id": series["id"],
                            "series_revision": series["revision"],
                        },
                    )
                ids.append(task["id"])
            series["occurrences"][occurrence_id] = {"state": "created", "tasks": ids}
            series["cursor"] += 1
            ctx.touch(series)
