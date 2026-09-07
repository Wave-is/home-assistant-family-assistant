"""Local single-choice family polls with private member-to-choice mappings."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from ..const import PRIVILEGED
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

MAX_OPTIONS = 10
MAX_ELIGIBLE = 50
MAX_OPEN = 100
MAX_POLLS = 500
MAX_ARCHIVED_VIEW = 100
MIN_DURATION = timedelta(minutes=5)
MAX_DURATION = timedelta(days=30)
STATUSES = frozenset({"open", "closed", "archived"})
BALLOT_MODE = "private_mapping"
_UNSPECIFIED = object()


def _version(value, field="revision") -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _module(state: dict) -> None:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "polls" not in modules:
        raise DomainError("module_disabled")


def _current_actor(ctx: Context) -> dict:
    member = ctx.state.get("members", {}).get(ctx.actor_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") == "guest"
        or ctx.actor.get("id") != member.get("id")
        or ctx.actor.get("role") != member.get("role")
        or ctx.actor.get("revision") != member.get("revision")
    ):
        raise DomainError("forbidden")
    _version(member.get("revision"), "actor_revision")
    return member


def _actor_revision(actor: dict, value, field="actor_revision") -> int:
    expected = _version(value, field)
    if actor.get("revision") != expected:
        raise DomainError("conflict", field)
    return expected


def _require_parent(ctx: Context, actor_revision) -> dict:
    actor = _current_actor(ctx)
    if actor.get("role") not in PRIVILEGED:
        raise DomainError("forbidden")
    _actor_revision(actor, actor_revision)
    return actor


def _polls(state: dict) -> dict:
    value = state.get("polls", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "polls")
    return value


def _mutable_polls(ctx: Context) -> dict:
    value = ctx.state.get("polls")
    if value is None:
        value = {}
        ctx.state["polls"] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "polls")
    return value


def _ballots(state: dict) -> dict:
    value = state.get("poll_ballots", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "poll_ballots")
    return value


def _mutable_ballots(ctx: Context) -> dict:
    value = ctx.state.get("poll_ballots")
    if value is None:
        value = {}
        ctx.state["poll_ballots"] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "poll_ballots")
    return value


def _record(state: dict, poll_id, revision=_UNSPECIFIED) -> dict:
    poll_id = text(poll_id, "id", 80)
    record = _polls(state).get(poll_id)
    if not isinstance(record, dict):
        raise DomainError("not_found")
    if (
        record.get("id") != poll_id
        or record.get("status") not in STATUSES
        or record.get("ballot_mode") != BALLOT_MODE
    ):
        raise DomainError("invalid_field", "polls")
    stored_revision = _version(record.get("revision"))
    if revision is not _UNSPECIFIED and _version(revision) != stored_revision:
        raise DomainError("conflict")
    return record


def _advance(ctx: Context, record: dict) -> dict:
    _ensure_advanceable(record)
    return ctx.touch(record)


def _ensure_advanceable(record: dict) -> None:
    if _version(record.get("revision")) == 2**53 - 1:
        raise DomainError("invalid_field", "revision")


def _options(value) -> list[dict]:
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_OPTIONS:
        raise DomainError("invalid_field", "options")
    result = []
    seen = set()
    for index, raw in enumerate(value, 1):
        label = text(raw, f"options[{index - 1}]", 120)
        identity = label.casefold()
        if identity in seen:
            raise DomainError("invalid_field", "options")
        seen.add(identity)
        result.append({"id": f"O{index}", "label": label})
    return result


def _eligible(state: dict, value) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ELIGIBLE:
        raise DomainError("invalid_field", "eligible")
    result = []
    seen = set()
    for index, raw in enumerate(value):
        field = f"eligible[{index}]"
        if not isinstance(raw, dict):
            raise DomainError("invalid_field", field)
        fields(raw, {"member", "revision"}, {"member", "revision"})
        member_id = text(raw["member"], f"{field}.member", 80)
        if member_id in seen:
            raise DomainError("invalid_field", "eligible")
        member = state.get("members", {}).get(member_id)
        if (
            not isinstance(member, dict)
            or member.get("active") is not True
            or member.get("role") == "guest"
        ):
            raise DomainError("unknown_member")
        expected = _version(raw["revision"], f"{field}.revision")
        if _version(member.get("revision"), f"{field}.revision") != expected:
            raise DomainError("conflict", f"{field}.revision")
        seen.add(member_id)
        result.append({"member": member_id, "member_revision": expected})
    return result


def _deadline(value, now: datetime) -> str:
    if not isinstance(value, str):
        raise DomainError("invalid_field", "closes_at")
    result = timestamp(value, "closes_at")
    if result.microsecond:
        raise DomainError("invalid_field", "closes_at")
    current = timestamp(now, "now").astimezone(UTC)
    result = result.astimezone(UTC)
    if not MIN_DURATION <= result - current <= MAX_DURATION:
        raise DomainError("invalid_field", "closes_at")
    return result.isoformat()


def _eligible_entry(record: dict, actor: dict) -> dict | None:
    eligible = record.get("eligible")
    if not isinstance(eligible, list):
        raise DomainError("invalid_field", "eligible")
    for entry in eligible:
        if not isinstance(entry, dict):
            raise DomainError("invalid_field", "eligible")
        if entry.get("member") == actor.get("id"):
            expected = _version(entry.get("member_revision"), "member_revision")
            return entry if expected == actor.get("revision") else None
    return None


def _voter_record(state: dict, poll_id, actor: dict) -> dict:
    """Resolve a voter-scoped poll without exposing another electorate's IDs."""
    poll_id = text(poll_id, "id", 80)
    raw = _polls(state).get(poll_id)
    eligible = raw.get("eligible") if isinstance(raw, dict) else None
    if not isinstance(eligible, list):
        raise DomainError("forbidden")
    for entry in eligible:
        if not isinstance(entry, dict) or entry.get("member") != actor.get("id"):
            continue
        try:
            member_revision = _version(entry.get("member_revision"), "member_revision")
        except DomainError:
            raise DomainError("forbidden") from None
        if member_revision == actor.get("revision"):
            return _record(state, poll_id)
        break
    raise DomainError("forbidden")


def _poll_ballots(state: dict, poll_id: str) -> dict:
    result = _ballots(state).get(poll_id, {})
    if not isinstance(result, dict):
        raise DomainError("invalid_field", "poll_ballots")
    return result


def _aggregate(state: dict, record: dict) -> tuple[list[dict], int]:
    if record.get("status") == "archived":
        results = record.get("results")
        cast_count = record.get("cast_count")
        if not isinstance(results, list) or type(cast_count) is not int:
            raise DomainError("invalid_field", "polls")
        return deepcopy(results), cast_count
    option_ids = {item["id"] for item in record.get("options", []) if isinstance(item, dict)}
    eligible = {
        (entry.get("member"), entry.get("member_revision"))
        for entry in record.get("eligible", [])
        if isinstance(entry, dict)
    }
    counts = dict.fromkeys(option_ids, 0)
    cast_count = 0
    for member_id, ballot in _poll_ballots(state, record["id"]).items():
        if not isinstance(ballot, dict) or ballot.get("member") != member_id:
            raise DomainError("invalid_field", "poll_ballots")
        _version(ballot.get("revision"), "ballot_revision")
        identity = (member_id, ballot.get("member_revision"))
        option_id = ballot.get("option_id")
        if identity not in eligible or option_id not in counts:
            raise DomainError("invalid_field", "poll_ballots")
        counts[option_id] += 1
        cast_count += 1
    return (
        [{"option_id": item["id"], "count": counts[item["id"]]} for item in record["options"]],
        cast_count,
    )


def _receipt(record: dict) -> dict:
    return {key: record[key] for key in ("id", "revision", "status")}


def _create(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {
            "actor_revision",
            "question",
            "options",
            "eligible",
            "closes_at",
            "confirm_private_ballot_limits",
        },
        {
            "actor_revision",
            "question",
            "options",
            "eligible",
            "closes_at",
            "confirm_private_ballot_limits",
        },
    )
    actor = _require_parent(ctx, payload["actor_revision"])
    if payload["confirm_private_ballot_limits"] is not True:
        raise DomainError("confirmation_required")
    polls = _polls(ctx.state)
    records = [_record(ctx.state, poll_id) for poll_id in polls]
    if len(polls) >= MAX_POLLS:
        raise DomainError("command_too_large")
    if sum(record.get("status") == "open" for record in records) >= MAX_OPEN:
        raise DomainError("invalid_transition")
    question = text(payload["question"], "question", 240)
    options = _options(payload["options"])
    eligible = _eligible(ctx.state, payload["eligible"])
    closes_at = _deadline(payload["closes_at"], ctx.now)
    record = {
        "id": ctx.identifier("PL"),
        "revision": 1,
        "definition_revision": 1,
        "status": "open",
        "ballot_mode": BALLOT_MODE,
        "question": question,
        "options": options,
        "eligible": eligible,
        "closes_at": closes_at,
        "created_by": actor["id"],
        "creator_revision": actor["revision"],
        "created_at": ctx.now.isoformat(),
        "updated_at": ctx.now.isoformat(),
        "closed_at": None,
        "archived_at": None,
    }
    _mutable_polls(ctx)[record["id"]] = record
    return _receipt(record)


def _vote(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {"id", "definition_revision", "voter_revision", "option_id", "ballot_revision"},
        {"id", "definition_revision", "voter_revision", "option_id", "ballot_revision"},
    )
    actor = _current_actor(ctx)
    _actor_revision(actor, payload["voter_revision"], "voter_revision")
    record = _voter_record(ctx.state, payload["id"], actor)
    if record.get("status") != "open" or timestamp(ctx.now, "now").astimezone(UTC) >= timestamp(
        record.get("closes_at"), "closes_at"
    ).astimezone(UTC):
        raise DomainError("invalid_transition")
    if _version(payload["definition_revision"], "definition_revision") != _version(
        record.get("definition_revision"), "definition_revision"
    ):
        raise DomainError("conflict", "definition_revision")
    option_id = text(payload["option_id"], "option_id", 16)
    if option_id not in {option["id"] for option in record.get("options", [])}:
        raise DomainError("invalid_field", "option_id")

    poll_ballots = _poll_ballots(ctx.state, record["id"])
    existing = poll_ballots.get(actor["id"])
    if existing is None:
        if payload["ballot_revision"] is not None:
            raise DomainError("conflict", "ballot_revision")
        poll_ballots = _mutable_ballots(ctx).setdefault(record["id"], {})
        if not isinstance(poll_ballots, dict):
            raise DomainError("invalid_field", "poll_ballots")
        ballot = {
            "member": actor["id"],
            "member_revision": actor["revision"],
            "option_id": option_id,
            "revision": 1,
            "first_cast_at": ctx.now.isoformat(),
            "updated_at": ctx.now.isoformat(),
        }
        poll_ballots[actor["id"]] = ballot
        return {"id": record["id"], "ballot_revision": 1}

    if not isinstance(existing, dict):
        raise DomainError("invalid_field", "poll_ballots")
    current_revision = _version(existing.get("revision"), "ballot_revision")
    if _version(payload["ballot_revision"], "ballot_revision") != current_revision:
        raise DomainError("conflict", "ballot_revision")
    if current_revision == 2**53 - 1:
        raise DomainError("invalid_field", "ballot_revision")
    if (
        existing.get("member") != actor["id"]
        or existing.get("member_revision") != actor["revision"]
    ):
        raise DomainError("forbidden")
    if existing.get("option_id") == option_id:
        raise DomainError("invalid_transition")
    existing.update(
        option_id=option_id,
        revision=current_revision + 1,
        updated_at=ctx.now.isoformat(),
    )
    return {"id": record["id"], "ballot_revision": existing["revision"]}


def _close_record(ctx: Context, record: dict) -> dict:
    if record.get("status") != "open":
        raise DomainError("invalid_transition")
    _ensure_advanceable(record)
    close_at = min(
        timestamp(ctx.now, "now").astimezone(UTC),
        timestamp(record.get("closes_at"), "closes_at").astimezone(UTC),
    )
    record["status"] = "closed"
    record["closed_at"] = close_at.isoformat()
    return _advance(ctx, record)


def _close(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision", "actor_revision"}, {"id", "revision", "actor_revision"})
    _require_parent(ctx, payload["actor_revision"])
    record = _record(ctx.state, payload["id"], payload["revision"])
    return _receipt(_close_record(ctx, record))


def _archive(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision", "actor_revision"}, {"id", "revision", "actor_revision"})
    _require_parent(ctx, payload["actor_revision"])
    record = _record(ctx.state, payload["id"], payload["revision"])
    if record.get("status") != "closed":
        raise DomainError("invalid_transition")
    _ensure_advanceable(record)
    results, cast_count = _aggregate(ctx.state, record)
    eligible = record.get("eligible")
    if not isinstance(eligible, list):
        raise DomainError("invalid_field", "eligible")
    record.update(
        status="archived",
        results=results,
        cast_count=cast_count,
        eligible_count=len(eligible),
        archived_at=ctx.now.isoformat(),
    )
    for field in ("eligible", "definition_revision", "created_by", "creator_revision"):
        record.pop(field, None)
    _mutable_ballots(ctx).pop(record["id"], None)
    return _receipt(_advance(ctx, record))


def _purge(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {"id", "revision", "actor_revision", "confirm_delete"},
        {"id", "revision", "actor_revision", "confirm_delete"},
    )
    actor = _require_parent(ctx, payload["actor_revision"])
    if actor.get("role") != "owner":
        raise DomainError("forbidden")
    if payload["confirm_delete"] is not True:
        raise DomainError("confirmation_required")
    record = _record(ctx.state, payload["id"], payload["revision"])
    if record.get("status") != "archived":
        raise DomainError("invalid_transition")
    _polls(ctx.state).pop(record["id"])
    _mutable_ballots(ctx).pop(record["id"], None)
    return {"id": record["id"], "status": "deleted"}


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply one explicit poll command without notifications or external effects."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _module(ctx.state)
    if action == "create":
        return _create(ctx, payload)
    if action == "vote":
        return _vote(ctx, payload)
    if action == "close":
        return _close(ctx, payload)
    if action == "archive":
        return _archive(ctx, payload)
    if action == "purge":
        return _purge(ctx, payload)
    raise DomainError("unknown_action")


def _current_member(state: dict, actor: dict) -> dict | None:
    if not isinstance(actor, dict):
        return None
    current = state.get("members", {}).get(actor.get("id"))
    if (
        not isinstance(current, dict)
        or current.get("active") is not True
        or current.get("role") == "guest"
    ):
        return None
    try:
        _version(current.get("revision"), "actor_revision")
    except DomainError:
        return None
    return current


def _current_eligible(record: dict, actor: dict) -> bool:
    return _eligible_entry(record, actor) is not None


def _eligible_projection(state: dict, record: dict) -> list[dict]:
    result = []
    for entry in record.get("eligible", []):
        member = state.get("members", {}).get(entry.get("member"))
        try:
            current_revision = (
                _version(member.get("revision"), "member_revision")
                if isinstance(member, dict)
                else None
            )
        except DomainError:
            current_revision = None
        result.append(
            {
                **deepcopy(entry),
                "current": bool(
                    isinstance(member, dict)
                    and member.get("active") is True
                    and member.get("role") != "guest"
                    and current_revision == entry.get("member_revision")
                ),
            }
        )
    return result


def _active_row(state: dict, record: dict, actor: dict, parent: bool, now) -> dict:
    closes_at = timestamp(record.get("closes_at"), "closes_at").astimezone(UTC)
    effective_closed = record.get("status") == "closed" or (
        record.get("status") == "open"
        and now is not None
        and timestamp(now, "now").astimezone(UTC) >= closes_at
    )
    status = "closed" if effective_closed else "open"
    entry = _eligible_entry(record, actor)
    ballots = _poll_ballots(state, record["id"])
    own = ballots.get(actor["id"]) if entry is not None else None
    own_ballot = None
    if own is not None:
        if not isinstance(own, dict) or own.get("member_revision") != actor.get("revision"):
            raise DomainError("invalid_field", "poll_ballots")
        own_ballot = {
            "option_id": own.get("option_id"),
            "revision": _version(own.get("revision"), "ballot_revision"),
        }
    result = {
        key: deepcopy(record[key])
        for key in (
            "id",
            "revision",
            "definition_revision",
            "question",
            "options",
            "closes_at",
            "ballot_mode",
        )
    }
    result.update(
        status=status,
        eligible_count=len(record["eligible"]),
        can_vote=status == "open" and entry is not None,
        own_ballot=own_ballot,
    )
    if effective_closed:
        results, cast_count = _aggregate(state, record)
        result.update(
            closed_at=record.get("closed_at") or record["closes_at"],
            results=results,
            cast_count=cast_count,
        )
    if parent:
        result.update(
            eligible=_eligible_projection(state, record),
            created_by=record.get("created_by"),
            created_at=record.get("created_at"),
            can_close=status == "open",
            can_archive=record.get("status") == "closed",
            can_purge=False,
        )
    return result


def _archived_row(record: dict, actor: dict) -> dict:
    result = {
        key: deepcopy(record[key])
        for key in (
            "id",
            "revision",
            "status",
            "question",
            "options",
            "closes_at",
            "closed_at",
            "archived_at",
            "ballot_mode",
            "results",
            "cast_count",
            "eligible_count",
        )
    }
    result.update(
        can_vote=False,
        own_ballot=None,
        can_close=False,
        can_archive=False,
        can_purge=actor.get("role") == "owner",
    )
    return result


def view(state: dict, actor: dict, now: datetime | None = None) -> dict:
    """Return a pure projection; pass now to obtain deterministic deadline closure."""
    empty = {"open": [], "closed": [], "archived": []}
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "polls" not in modules:
        return empty
    current = _current_member(state, actor)
    if current is None:
        return empty
    parent = current.get("role") in PRIVILEGED
    open_rows, closed_rows, archived_rows = [], [], []
    for record in _polls(state).values():
        record = _record(state, record.get("id") if isinstance(record, dict) else "")
        if record["status"] == "archived":
            if parent:
                archived_rows.append(_archived_row(record, current))
            continue
        if not parent and not _current_eligible(record, current):
            continue
        row = _active_row(state, record, current, parent, now)
        (closed_rows if row["status"] == "closed" else open_rows).append(row)
    open_rows.sort(key=lambda row: (row["closes_at"], row["id"]))
    closed_rows.sort(key=lambda row: (row["closed_at"], row["id"]), reverse=True)
    archived_rows.sort(key=lambda row: (row["archived_at"], row["id"]), reverse=True)
    return {
        "open": open_rows,
        "closed": closed_rows,
        "archived": archived_rows[:MAX_ARCHIVED_VIEW],
    }


def tick(ctx: Context) -> None:
    """Persist every overdue close in one bounded restart-safe pass."""
    modules = ctx.state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "polls" not in modules:
        return
    now = timestamp(ctx.now, "now").astimezone(UTC)
    due = sorted(
        (
            record
            for record in _polls(ctx.state).values()
            if isinstance(record, dict)
            and record.get("status") == "open"
            and timestamp(record.get("closes_at"), "closes_at").astimezone(UTC) <= now
        ),
        key=lambda record: (record["closes_at"], record["id"]),
    )
    for record in due:
        _record(ctx.state, record["id"])
        _close_record(ctx, record)


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Opaque receipts survive only while their current identity scope remains valid."""
    if not isinstance(payload, dict) or not isinstance(result, dict):
        raise DomainError("forbidden")
    _module(ctx.state)
    if action == "vote":
        actor = _current_actor(ctx)
        _actor_revision(actor, payload.get("voter_revision"), "voter_revision")
        record = _voter_record(ctx.state, payload.get("id"), actor)
        if record.get("status") == "archived" or _eligible_entry(record, actor) is None:
            raise DomainError("forbidden")
        if _version(payload.get("definition_revision"), "definition_revision") != _version(
            record.get("definition_revision"), "definition_revision"
        ):
            raise DomainError("conflict")
        result_revision = _version(result.get("ballot_revision"), "ballot_revision")
        prior_revision = payload.get("ballot_revision")
        if (
            result_revision != 1
            if prior_revision is None
            else result_revision != _version(prior_revision, "ballot_revision") + 1
        ):
            raise DomainError("conflict")
        ballot = _poll_ballots(ctx.state, record["id"]).get(actor["id"])
        if (
            result.get("id") != record["id"]
            or not isinstance(ballot, dict)
            or ballot.get("member") != actor["id"]
            or ballot.get("member_revision") != actor["revision"]
            or _version(ballot.get("revision"), "ballot_revision") < result_revision
        ):
            raise DomainError("conflict")
        return
    if action in {"create", "close", "archive", "purge"}:
        actor = _require_parent(ctx, payload.get("actor_revision"))
        result_id = text(result.get("id"), "id", 80)
        if action == "purge":
            if (
                actor.get("role") != "owner"
                or result.get("status") != "deleted"
                or result_id != text(payload.get("id"), "id", 80)
            ):
                raise DomainError("forbidden")
            if result_id in _polls(ctx.state):
                raise DomainError("conflict")
            return
        record = _record(ctx.state, result_id)
        result_revision = _version(result.get("revision"))
        if result_revision > _version(record.get("revision")):
            raise DomainError("conflict")
        if action == "create" and (result.get("status") != "open" or result_revision != 1):
            raise DomainError("conflict")
        if action == "close" and (
            result_id != text(payload.get("id"), "id", 80)
            or result.get("status") != "closed"
            or record.get("status") not in {"closed", "archived"}
        ):
            raise DomainError("conflict")
        if action == "archive" and (
            result_id != text(payload.get("id"), "id", 80)
            or result.get("status") != "archived"
            or record.get("status") != "archived"
        ):
            raise DomainError("conflict")
        return
    raise DomainError("unknown_action")
