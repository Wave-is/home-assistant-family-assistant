"""Owner-controlled household preferences, persisted alongside family data."""

from ..const import LANGUAGES, MODULES
from .context import Context
from .household import timezone
from .recurrence import clock
from .validation import DomainError, enum, fields, text


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    if action != "save":
        raise DomainError("unknown_action")
    fields(
        payload,
        {
            "name",
            "language",
            "modules",
            "automatic_penalties",
            "daily_penalty_cap",
            "timezone",
            "pantry_expiry_reminders",
            "pantry_expiry_days",
            "school_preparation_reminders",
            "school_preparation_days_before",
            "school_preparation_time",
        },
        {"name", "language", "modules"},
    )
    modules = payload["modules"]
    if not isinstance(modules, list) or any(m not in MODULES for m in modules):
        raise DomainError("invalid_field", "modules")
    if "pantry_expiry_reminders" in payload and not isinstance(
        payload["pantry_expiry_reminders"], bool
    ):
        raise DomainError("invalid_field", "pantry_expiry_reminders")
    if "pantry_expiry_days" in payload:
        expiry_days = payload["pantry_expiry_days"]
        if type(expiry_days) is not int or not 0 <= expiry_days <= 30:
            raise DomainError("invalid_field", "pantry_expiry_days")
    if (
        "school_preparation_reminders" in payload
        and type(payload["school_preparation_reminders"]) is not bool
    ):
        raise DomainError("invalid_field", "school_preparation_reminders")
    if "school_preparation_days_before" in payload:
        days_before = payload["school_preparation_days_before"]
        if type(days_before) is not int or days_before not in {0, 1}:
            raise DomainError("invalid_field", "school_preparation_days_before")
    if "school_preparation_time" in payload:
        try:
            clock(payload["school_preparation_time"])
        except DomainError:
            raise DomainError("invalid_field", "school_preparation_time") from None
    ctx.state["settings"].update(
        {
            "name": text(payload["name"], "name", 80),
            "language": enum(payload["language"], LANGUAGES, "language"),
            "modules": sorted(set(modules)),
        }
    )
    if "automatic_penalties" in payload:
        if not isinstance(payload["automatic_penalties"], bool):
            raise DomainError("invalid_field", "automatic_penalties")
        ctx.state["settings"]["automatic_penalties"] = payload["automatic_penalties"]
    if "timezone" in payload:
        ctx.state["settings"]["timezone"] = timezone(payload["timezone"])
    if "daily_penalty_cap" in payload:
        value = payload["daily_penalty_cap"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise DomainError("invalid_field", "daily_penalty_cap")
        ctx.state["settings"]["daily_penalty_cap"] = value
    if "pantry_expiry_reminders" in payload:
        ctx.state["settings"]["pantry_expiry_reminders"] = payload["pantry_expiry_reminders"]
    if "pantry_expiry_days" in payload:
        ctx.state["settings"]["pantry_expiry_days"] = payload["pantry_expiry_days"]
    if "school_preparation_reminders" in payload:
        ctx.state["settings"]["school_preparation_reminders"] = payload[
            "school_preparation_reminders"
        ]
    if "school_preparation_days_before" in payload:
        ctx.state["settings"]["school_preparation_days_before"] = payload[
            "school_preparation_days_before"
        ]
    if "school_preparation_time" in payload:
        ctx.state["settings"]["school_preparation_time"] = payload["school_preparation_time"]
    return ctx.state["settings"]
