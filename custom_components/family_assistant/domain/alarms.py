"""Durable two-stage wake-up workflow; clock and transports are injected.

An answer is accepted only for the current nonce, current stage and exact member.
Only hashes of answers are stored, never exposed to a card or command response.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from hmac import compare_digest
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .context import Context
from .penalties import award
from .validation import DomainError, enum, fields, number, revision, text, timestamp

ACTIVE = {"first", "waiting_second", "second"}


def public_run(run: dict) -> dict:
    return deepcopy({key: value for key, value in run.items() if key != "challenge_secret"})


def _integer(value, name: str, low: int, high: int) -> int:
    result = number(value, name, low, high)
    if not result.is_integer():
        raise DomainError("invalid_field", name)
    return int(result)


def _challenge(ctx: Context, run: dict) -> None:
    left, right = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
    nonce = secrets.token_urlsafe(12)
    answer = left + right
    choices = [answer - 2, answer - 1, answer, answer + 1]
    secrets.SystemRandom().shuffle(choices)
    run["challenge"] = {
        "nonce": nonce,
        "question": f"{left} + {right}",
        "choices": choices,
        "created_at": ctx.now.isoformat(),
        "expires_at": (ctx.now + timedelta(minutes=5)).isoformat(),
    }
    run["challenge_secret"] = {
        "digest": hashlib.sha256(f"{nonce}:{answer}".encode()).hexdigest(),
        "attempts": 0,
    }
    # An undelivered older challenge must not be sent after its replacement.
    for event in ctx.state["outbox"].values():
        if (
            event["key"] == "alarm_challenge"
            and event["data"].get("run_id") == run["id"]
            and event["state"] in {"pending", "sending", "awaiting_channel"}
        ):
            event["state"] = "superseded"
    ctx.notify(
        run["member"],
        "alarm_challenge",
        {"run_id": run["id"], "stage": run["stage"], **run["challenge"]},
    )


def _finish(ctx: Context, run: dict, stage: str, reason: str = "") -> dict:
    run.update(stage=stage, siren_desired=False, finished_at=ctx.now.isoformat())
    run.pop("challenge", None)
    run.pop("challenge_secret", None)
    if reason:
        run["reason"] = reason
    for event in ctx.state["outbox"].values():
        if (
            event["key"] == "alarm_challenge"
            and event["data"].get("run_id") == run["id"]
            and event["state"] in {"pending", "sending", "awaiting_channel"}
        ):
            event["state"] = "superseded"
    if run.get("escalated_at") and not run["test"]:
        ctx.notify(
            "family", "alarm_closed", {"run_id": run["id"], "member": run["member"], "stage": stage}
        )
    return ctx.touch(run)


def cancel_disabled(ctx: Context) -> None:
    for run in ctx.state["alarm_runs"].values():
        member = ctx.state["members"].get(run["member"], {})
        schedule = ctx.state["alarms"].get(run["alarm_id"], {})
        if run["stage"] in ACTIVE and (
            "alarms" not in ctx.state["settings"]["modules"]
            or not member.get("active", False)
            or (not schedule.get("enabled", False) and not run.get("test"))
        ):
            _finish(ctx, run, "cancelled", "disabled")


def _new_run(ctx: Context, schedule: dict, run_id: str, scheduled: datetime, test=False) -> dict:
    if any(
        r["member"] == schedule["member"] and r["stage"] in ACTIVE
        for r in ctx.state["alarm_runs"].values()
    ):
        raise DomainError("alarm_already_active")
    run = {
        "id": run_id,
        "alarm_id": schedule["id"],
        "member": schedule["member"],
        "scheduled_at": scheduled.isoformat(),
        "started_at": ctx.now.isoformat(),
        "stage": "first",
        "siren_desired": schedule["profile"] == "strict",
        "profile": schedule["profile"],
        "timezone": schedule["timezone"],
        "test": test,
        "second_min": schedule["second_min"],
        "second_max": schedule["second_max"],
        "recheck_grace": schedule["recheck_grace"],
        "penalty": schedule["penalty"],
        "escalate_at": (scheduled + timedelta(minutes=30)).isoformat(),
    }
    ctx.state["alarm_runs"][run_id] = run
    _challenge(ctx, run)
    return ctx.touch(run)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if action == "save":
        ctx.require_parent()
        is_edit = "id" in payload
        required = {"member", "time", "days", "timezone"} | ({"revision"} if is_edit else set())
        fields(
            payload,
            {
                "id",
                "revision",
                "member",
                "name",
                "time",
                "days",
                "timezone",
                "enabled",
                "exceptions",
                "second_min",
                "second_max",
                "profile",
                "recheck_grace",
                "penalty",
            },
            required,
        )
        if not is_edit and "revision" in payload:
            raise DomainError("invalid_field", "revision")
        member = ctx.member(payload["member"])
        alarm_id = text(payload["id"], "id", 80) if is_edit else ctx.identifier("A")
        old = ctx.record("alarms", alarm_id, revision(payload["revision"])) if is_edit else None
        clock = text(payload["time"], "time", 5)
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
            raise DomainError("invalid_field", "time")
        zone = text(payload["timezone"], "timezone", 80)
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise DomainError("invalid_field", "timezone") from None
        days = payload["days"]
        if not isinstance(days, list) or not days or len(days) > 7:
            raise DomainError("invalid_field", "days")
        days = sorted({_integer(day, "days", 0, 6) for day in days})
        exceptions = payload.get("exceptions", (old or {}).get("exceptions", []))
        if not isinstance(exceptions, list) or len(exceptions) > 366:
            raise DomainError("invalid_field", "exceptions")
        try:
            exceptions = sorted({date.fromisoformat(day).isoformat() for day in exceptions})
        except (TypeError, ValueError):
            raise DomainError("invalid_field", "exceptions") from None
        values = {
            "second_min": 12,
            "second_max": 18,
            "recheck_grace": 60,
            "penalty": 0,
            "profile": "gentle",
            "enabled": True,
            "name": "",
        }
        values.update({k: v for k, v in (old or {}).items() if k in values})
        values.update({k: v for k, v in payload.items() if k in values})
        if not isinstance(values["enabled"], bool):
            raise DomainError("invalid_field", "enabled")
        for key, low, high in (
            ("second_min", 1, 25),
            ("second_max", 1, 25),
            ("recheck_grace", 0, 300),
            ("penalty", -10, 0),
        ):
            values[key] = _integer(values[key], key, low, high)
        if values["second_min"] > values["second_max"]:
            raise DomainError("invalid_field", "second_max")
        enum(values["profile"], {"gentle", "strict"}, "profile")
        if not isinstance(values["name"], str) or len(values["name"]) > 80:
            raise DomainError("invalid_field", "name")
        # Two enabled schedules for one member may not ring at the same local time.
        if values["enabled"] and any(
            a["id"] != alarm_id
            and a["enabled"]
            and a["member"] == member["id"]
            and a["timezone"] == zone
            and a["time"] == clock
            and set(a["days"]) & set(days)
            for a in ctx.state["alarms"].values()
        ):
            raise DomainError("schedule_overlap")
        record = {
            **(old or {}),
            **values,
            "id": alarm_id,
            "member": member["id"],
            "time": clock,
            "timezone": zone,
            "days": days,
            "exceptions": exceptions,
        }
        ctx.state["alarms"][alarm_id] = ctx.touch(record)
        cancel_disabled(ctx)
        return record
    if action in {"enable", "test"}:
        ctx.require_parent()
        fields(
            payload,
            {"id", "revision", "enabled"} if action == "enable" else {"id"},
            {"id", "revision", "enabled"} if action == "enable" else {"id"},
        )
        if action == "test":
            schedule = ctx.record("alarms", payload["id"])
            return public_run(_new_run(ctx, schedule, ctx.identifier("W"), ctx.now, test=True))
        schedule = ctx.record("alarms", payload["id"], revision(payload["revision"]))
        if not isinstance(payload.get("enabled"), bool):
            raise DomainError("invalid_field", "enabled")
        schedule["enabled"] = payload["enabled"]
        if not schedule["enabled"]:
            for run in ctx.state["alarm_runs"].values():
                if run["alarm_id"] == schedule["id"] and run["stage"] in ACTIVE:
                    _finish(ctx, run, "cancelled", "disabled")
        cancel_disabled(ctx)
        return ctx.touch(schedule)
    if action == "cancel":
        ctx.require_parent()
        fields(payload, {"id", "reason"}, {"id", "reason"})
        run = ctx.record("alarm_runs", payload["id"])
        if run["stage"] not in ACTIVE:
            raise DomainError("invalid_transition")
        return public_run(_finish(ctx, run, "cancelled", text(payload["reason"], "reason")))
    if action == "answer":
        fields(payload, {"id", "nonce", "answer"}, {"id", "nonce", "answer"})
        run = ctx.record("alarm_runs", payload["id"])
        if run["member"] != ctx.actor_id:
            raise DomainError("forbidden")
        challenge = run.get("challenge", {})
        if run["stage"] not in {"first", "second"} or not challenge:
            raise DomainError("challenge_expired")
        nonce = text(payload["nonce"], "nonce", 40)
        if not compare_digest(nonce, challenge["nonce"]) or ctx.now >= timestamp(
            challenge["expires_at"], "expires_at"
        ):
            raise DomainError("challenge_expired")
        answer = _integer(payload["answer"], "answer", -100, 100)
        digest = hashlib.sha256(f"{nonce}:{answer}".encode()).hexdigest()
        if not compare_digest(digest, run["challenge_secret"]["digest"]):
            run["challenge_secret"]["attempts"] += 1
            if run["challenge_secret"]["attempts"] >= 3:
                _challenge(ctx, run)
            ctx.touch(run)
            return {"accepted": False, "run": public_run(run)}
        if run["stage"] == "first":
            delay = secrets.randbelow(run["second_max"] - run["second_min"] + 1) + run["second_min"]
            run.update(
                stage="waiting_second",
                siren_desired=False,
                first_confirmed_at=ctx.now.isoformat(),
                second_at=(ctx.now + timedelta(minutes=delay)).isoformat(),
            )
            run.pop("challenge", None)
            run.pop("challenge_secret", None)
            for event in ctx.state["outbox"].values():
                if event["key"] == "alarm_challenge" and event["data"].get("run_id") == run["id"]:
                    if event["state"] in {"pending", "sending", "awaiting_channel"}:
                        event["state"] = "superseded"
            ctx.touch(run)
        else:
            _finish(ctx, run, "complete")
        return {"accepted": True, "run": public_run(run)}
    raise DomainError("unknown_action")


def scheduled_time(schedule: dict, day: date) -> datetime | None:
    zone = ZoneInfo(schedule["timezone"])
    naive = datetime.combine(day, time.fromisoformat(schedule["time"]))
    local = naive.replace(tzinfo=zone, fold=0)
    instant = local.astimezone(UTC)
    # Skip a nonexistent spring-forward local time; never silently ring an hour late.
    if instant.astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return instant


def tick(ctx: Context) -> None:
    cancel_disabled(ctx)
    if "alarms" not in ctx.state["settings"]["modules"]:
        return
    for schedule in ctx.state["alarms"].values():
        if not schedule["enabled"] or not ctx.state["members"][schedule["member"]]["active"]:
            continue
        today = ctx.now.astimezone(ZoneInfo(schedule["timezone"])).date()
        # Yesterday is needed for a 23:59 alarm when HA returns just after midnight.
        for day in (today - timedelta(days=1), today):
            if day.weekday() not in schedule["days"] or day.isoformat() in schedule["exceptions"]:
                continue
            due = scheduled_time(schedule, day)
            run_id = f"{schedule['id']}:{day.isoformat()}"
            if due is None or run_id in ctx.state["alarm_runs"] or ctx.now < due:
                continue
            if ctx.now - due > timedelta(minutes=30):
                continue  # No surprise alarm for days missed while HA was stopped.
            try:
                _new_run(ctx, schedule, run_id, due)
            except DomainError as err:
                if err.code != "alarm_already_active":
                    raise
                continue
    for run in ctx.state["alarm_runs"].values():
        if run["stage"] not in ACTIVE:
            continue
        if run["stage"] == "waiting_second" and ctx.now >= timestamp(run["second_at"], "second_at"):
            run["stage"] = "second"
            _challenge(ctx, run)
            ctx.touch(run)
        if run["stage"] == "second" and ctx.now >= timestamp(
            run["second_at"], "second_at"
        ) + timedelta(seconds=run["recheck_grace"]):
            if run["profile"] == "strict" and not run["siren_desired"]:
                run["siren_desired"] = True
                ctx.touch(run)
        challenge = run.get("challenge")
        if challenge and ctx.now >= timestamp(challenge["expires_at"], "expires_at"):
            _challenge(ctx, run)
            ctx.touch(run)
        if not run.get("escalated_at") and ctx.now >= timestamp(run["escalate_at"], "escalate_at"):
            run["escalated_at"] = ctx.now.isoformat()
            if not run["test"]:
                ctx.notify("family", "alarm_missed", {"run_id": run["id"], "member": run["member"]})
                award(
                    ctx,
                    source="alarm",
                    source_id=run["id"],
                    member=run["member"],
                    points=run["penalty"],
                    reason_key="alarm_missed",
                    reason_data={"run_id": run["id"]},
                    timezone=run["timezone"],
                )
            ctx.touch(run)
