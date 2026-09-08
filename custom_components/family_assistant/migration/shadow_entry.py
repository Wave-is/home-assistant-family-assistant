"""A persistent ConfigEntry seal, not source-coherence or activation authority.

Both halves are required: an exact immutable shadow Store and a marker kept in
the independently persisted HA entry. Losing either must never create a blank
writable household. Marker creation is internal, after reviewed staging only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from hmac import compare_digest

from ..domain.shadow import SCHEMA, validate
from ..domain.validation import DomainError

KEY = "migration_shadow"


def entry_marker(state, expected_fingerprint):
    """Seal exact shadow bytes; this alone does not validate the conversion."""
    try:
        if (
            type(state) is not dict
            or not validate(state)
            or type(expected_fingerprint) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint)
        ):
            raise DomainError("migration_shadow_invalid")
        content = json.dumps(
            state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if not compare_digest(hashlib.sha256(content).hexdigest(), expected_fingerprint):
            raise DomainError("migration_shadow_invalid")
        return {"version": 1, "mode": "read_only", "fingerprint": expected_fingerprint}
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise DomainError("migration_shadow_invalid") from None


def validate_entry_state(data, state):
    """Return False only for an ordinary entry; damaged shadows always raise."""
    if not isinstance(data, Mapping):
        raise DomainError("migration_shadow_invalid")
    shadow_state = type(state) is dict and (
        KEY in state or "migration_archive" in state or state.get("schema_version") == SCHEMA
    )
    if KEY not in data and not shadow_state:
        return False
    try:
        marker = data[KEY]
        if (
            not isinstance(marker, Mapping)
            or set(marker) != {"version", "mode", "fingerprint"}
            or type(marker["version"]) is not int
            or marker["version"] != 1
            or marker["mode"] != "read_only"
            or entry_marker(state, marker["fingerprint"]) != dict(marker)
            or data.get("modules") != []
            or not isinstance(data.get("owner_user_id"), str)
            or not data["owner_user_id"]
            or state["members"]["owner"]["ha_user_id"] != data["owner_user_id"]
            or state["members"]["owner"]["active"] is not True
            or state["members"]["owner"]["role"] != "owner"
        ):
            raise DomainError("migration_shadow_invalid")
    except (KeyError, TypeError, AttributeError):
        raise DomainError("migration_shadow_invalid") from None
    return True
