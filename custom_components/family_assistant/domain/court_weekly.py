"""Opt-in, immutable weekly court reports; never reset balances or issue a penalty."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from . import court_rules
from .context import Context
from .court_periods import period_bounds, summarize
from .validation import DomainError, fields, timestamp

DEFAULTS = {
    "weekly_enabled": False,
    "weekday": 0,
    "time": "00:00",
    "second_adult_review": False,
    "thresholds": [],
    "revision": 0,
}


def configuration(state):
    return deepcopy({**DEFAULTS, **state["settings"].get("court", {})})


def configure(ctx, payload):
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    fields(payload, set(DEFAULTS), {"revision"})
    previous = configuration(ctx.state)
    if type(payload["revision"]) is not int or payload["revision"] < 0:
        raise DomainError("invalid_field", "revision")
    if previous["revision"] != payload["revision"]:
        raise DomainError("conflict")
    value = {**previous, **payload}
    if "thresholds" in payload:
        value["thresholds"] = court_rules.validate(ctx, payload["thresholds"])
    for key in ("weekly_enabled", "second_adult_review"):
        if type(value[key]) is not bool:
            raise DomainError("invalid_field", key)
    period_bounds(
        ctx.now, ctx.state["settings"].get("timezone", "UTC"), value["weekday"], value["time"]
    )
    if (
        value["second_adult_review"]
        and sum(
            m.get("active", True) and m["role"] in {"owner", "parent"}
            for m in ctx.state["members"].values()
        )
        < 2
    ):
        raise DomainError("invalid_field", "second_adult_review")
    if any(value[k] != previous[k] for k in ("weekly_enabled", "weekday", "time", "thresholds")):
        value["effective_at"] = ctx.now.isoformat()
    value["revision"] += 1
    ctx.state["settings"]["court"] = value
    return value


def view(state, records, now=None):
    config = configuration(state)
    zone = state["settings"].get("timezone", "UTC")
    start, end = period_bounds(now or datetime.now(UTC), zone, config["weekday"], config["time"])
    totals = summarize(records, start, end)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": zone,
        **totals,
        "thresholds": court_rules.project(config["thresholds"], totals["rows"]),
        "rule_revision": config["revision"],
    }


def tick(ctx):
    config = configuration(ctx.state)
    if "court" not in ctx.state["settings"]["modules"] or not config["weekly_enabled"]:
        for event in ctx.state["outbox"].values():
            if event["key"] == "court_weekly" and event["state"] in {"pending", "awaiting_channel"}:
                event["state"] = "superseded"
        return
    zone = ctx.state["settings"].get("timezone", "UTC")
    current_start, _ = period_bounds(ctx.now, zone, config["weekday"], config["time"])
    effective = timestamp(config.get("effective_at", ctx.now.isoformat()), "effective_at")
    if current_start <= effective:
        return
    start, end = period_bounds(
        current_start - timedelta(microseconds=1), zone, config["weekday"], config["time"]
    )
    # At most the latest completed period after downtime, never a backlog storm.
    identifier = f"{start.isoformat()}/{end.isoformat()}"
    reports = ctx.state["court_reports"]
    if identifier in reports:
        return
    report = {
        "id": identifier,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": zone,
        "created_at": ctx.now.isoformat(),
        **summarize(list(ctx.state["court"].values()), start, end),
    }
    report["thresholds"] = court_rules.project(config["thresholds"], report["rows"])
    report["rule_revision"] = config["revision"]
    reports[identifier] = report
    notifier = Context(ctx.state, ctx.actor, ctx.now, f"court-weekly:{identifier}")
    notifier.notify("family", "court_weekly", {"report_id": identifier})


def require_independent_reviewer(ctx, record):
    if not configuration(ctx.state)["second_adult_review"]:
        return
    if ctx.actor_id in {record["actor"], record.get("appeal", {}).get("actor")}:
        raise DomainError("forbidden")
