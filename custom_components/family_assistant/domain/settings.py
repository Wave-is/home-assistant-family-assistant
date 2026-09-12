"""Owner-controlled household preferences, persisted alongside family data."""

from ..const import LANGUAGES, MODULES
from . import digest_settings
from .context import Context
from .household import timezone
from .recurrence import clock
from .validation import DomainError, enum, fields, revision, text

EDITABLE = {
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
    *digest_settings.DEFAULTS,
}


def current_revision(state):
    return revision(state.get("settings_revision", 1))


def onboarding(state):
    return dict(
        state.get("onboarding", {"revision": 1, "step": 1, "completed": False, "skipped": []})
    )


def _onboarding(ctx, payload):
    fields(payload, {"revision", "step", "completed", "skipped"}, {"revision", "step"})
    previous = onboarding(ctx.state)
    if revision(payload["revision"]) != previous["revision"]:
        raise DomainError("conflict")
    if type(payload["step"]) is not int or payload["step"] not in {1, 2, 3, 4}:
        raise DomainError("invalid_field", "step")
    completed = payload.get("completed", previous["completed"])
    if type(completed) is not bool or (completed and payload["step"] != 4):
        raise DomainError("invalid_field", "completed")
    skipped = payload.get("skipped", previous["skipped"])
    if (
        not isinstance(skipped, list)
        or len(skipped) > 2
        or any(not isinstance(step, str) or step not in {"telegram", "modules"} for step in skipped)
    ):
        raise DomainError("invalid_field", "skipped")
    result = {
        "revision": revision(previous["revision"] + 1),
        "step": payload["step"],
        "completed": completed,
        "skipped": sorted(set(skipped)),
    }
    ctx.state["onboarding"] = result
    return result


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    if action == "onboarding":
        return _onboarding(ctx, payload)
    if action == "module_toggle":
        fields(payload, {"revision", "module", "enabled"}, {"revision", "module", "enabled"})
        module = enum(payload["module"], MODULES, "module")
        if type(payload["enabled"]) is not bool:
            raise DomainError("invalid_field", "enabled")
        # Derive the merged list inside the transaction, AFTER replay lookup.
        # Hash only the caller's stable intent, never a fresh snapshot on retry.
        modules = set(ctx.state["settings"]["modules"])
        modules.add(module) if payload["enabled"] else modules.discard(module)
        payload = {"revision": payload["revision"], "changes": {"modules": sorted(modules)}}
        action = "patch"
    if action == "patch":
        fields(payload, {"revision", "changes"}, {"revision", "changes"})
        if revision(payload["revision"]) != current_revision(ctx.state):
            raise DomainError("conflict")
        changes = payload["changes"]
        if not isinstance(changes, dict) or not changes or changes.keys() - EDITABLE:
            raise DomainError("invalid_field", "changes")
        payload = {
            **{key: ctx.state["settings"][key] for key in ("name", "language", "modules")},
            **changes,
        }
        action = "save"
    if action == "digest_policy":
        result = digest_settings.handle(ctx, payload)
        ctx.state["settings_revision"] = revision(current_revision(ctx.state) + 1)
        return result
    if action == "developer_policy":
        from .developer_diagnostics import configure

        return configure(ctx, payload)
    if action != "save":
        raise DomainError("unknown_action")
    if "revision" in payload and revision(payload["revision"]) != current_revision(ctx.state):
        raise DomainError("conflict")
    previous_digest_policy = digest_settings.fingerprint(ctx.state)
    fields(
        payload,
        {
            "revision",
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
            *digest_settings.DEFAULTS,
        },
        {"name", "language", "modules"},
    )
    modules = payload["modules"]
    digest_values = digest_settings.validate(
        {key: payload[key] for key in digest_settings.DEFAULTS if key in payload}
    )
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
    ctx.state["settings"].update(digest_values)
    digest_settings.advance(ctx.state, previous_digest_policy)
    ctx.state["settings_revision"] = revision(current_revision(ctx.state) + 1)
    return ctx.state["settings"]
