"""Persistent read-only migration isolation, not permission to activate a copy."""

import re

from .validation import DomainError

_SHA256 = re.compile(r"[0-9a-f]{64}")
# Older releases reject this schema before constructing any runtime workers.
SCHEMA = "legacy-shadow-v1"


def validate(state: dict) -> bool:
    """Absence is ordinary runtime; any malformed/unsafe marker fails closed."""
    try:
        return _validate(state)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise DomainError("migration_shadow_invalid") from None


def _validate(state: dict) -> bool:
    if "migration_shadow" not in state:
        return False
    marker = state["migration_shadow"]
    if (
        state.get("schema_version") != SCHEMA
        or type(marker) is not dict
        or set(marker) != {"version", "mode", "source_fingerprint", "conversion_fingerprint"}
        or type(marker["version"]) is not int
        or marker["version"] != 1
        or marker["mode"] != "read_only"
        or any(
            type(marker[key]) is not str or not _SHA256.fullmatch(marker[key])
            for key in ("source_fingerprint", "conversion_fingerprint")
        )
        or state.get("settings", {}).get("modules") != []
        or state.get("settings", {}).get("automatic_penalties") is not False
        or any(
            type(state.get(bucket)) is not dict or state[bucket]
            for bucket in (
                "alarm_runs",
                "alarm_outputs",
                "outbox",
                "network",
                "telegram",
                "enrollments",
                "proposals",
                "assistant_jobs",
                "routine_runs",
                "incidents",
                "processed",
                "notification_rates",
            )
        )
        or type(state.get("alarms")) is not dict
        or any(
            type(row) is not dict or row.get("enabled") is not False
            for row in state["alarms"].values()
        )
    ):
        raise DomainError("migration_shadow_invalid")
    return True
