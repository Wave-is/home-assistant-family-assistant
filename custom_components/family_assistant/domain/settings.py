"""Owner-controlled household preferences, persisted alongside family data."""

from ..const import LANGUAGES, MODULES
from .context import Context
from .validation import DomainError, enum, fields, text


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    if action != "save":
        raise DomainError("unknown_action")
    fields(
        payload,
        {"name", "language", "modules", "automatic_penalties", "daily_penalty_cap"},
        {"name", "language", "modules"},
    )
    modules = payload["modules"]
    if not isinstance(modules, list) or any(m not in MODULES for m in modules):
        raise DomainError("invalid_field", "modules")
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
    if "daily_penalty_cap" in payload:
        value = payload["daily_penalty_cap"]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise DomainError("invalid_field", "daily_penalty_cap")
        ctx.state["settings"]["daily_penalty_cap"] = value
    return ctx.state["settings"]
