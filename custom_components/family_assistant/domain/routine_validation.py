"""Pure routine validation logic for family assistant routines."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .context import Context
from .recurrence import validate as validate_recurrence
from .routine_conditions import validate as validate_condition
from .validation import DomainError, fields, text

ALLOWED_MODES = frozenset({"normal", "holidays", "guests", "ill", "vacation"})
ENTITY_REGEX = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
STEP_FIELDS = {
    "title",
    "offset_minutes",
    "confirmation",
    "completion_condition",
    "skip_when",
    "escalate_minutes",
}


def configuration(state: dict) -> dict:
    """Return routine settings configuration with deepcopied defaults."""
    defaults = {
        "modes": ["normal"],
        "entity_allowlist": [],
        "revision": 0,
    }
    routines_settings = state.get("settings", {}).get("routines", {})
    merged = deepcopy(defaults)
    merged.update(deepcopy(routines_settings))
    return merged


def entities(condition: Any) -> set[str]:
    """Recursively collect all entity_ids referenced by entity_state nodes."""
    if not isinstance(condition, dict):
        return set()
    found: set[str] = set()
    kind = condition.get("kind")
    if kind == "entity_state":
        entity_id = condition.get("entity_id")
        if isinstance(entity_id, str):
            found.add(entity_id)
    elif isinstance(kind, str) and kind in {"all", "any"}:
        children = condition.get("conditions", [])
        if isinstance(children, list):
            for child in children:
                found.update(entities(child))
    return found


def condition(value: Any, allowlist: list[str] | set[str] | frozenset[str]) -> dict | None:
    """Validate condition structure and ensure referenced entities are in allowlist."""
    if value is None:
        return None
    normalized = validate_condition(value)
    allowed = set(allowlist) if isinstance(allowlist, (list, set, frozenset)) else set()
    referenced = entities(normalized)
    forbidden = referenced - allowed
    if forbidden:
        raise DomainError("forbidden")
    return normalized


def validate_modes(value: Any) -> list[str]:
    """Validate modes list: sorted unique list 1..5, strict strings, normal exclusive."""
    if not isinstance(value, list) or not 1 <= len(value) <= 5:
        raise DomainError("invalid_field", "modes")
    for item in value:
        if not isinstance(item, str) or item not in ALLOWED_MODES:
            raise DomainError("invalid_field", "modes")
    unique = sorted(set(value))
    if len(unique) != len(value):
        raise DomainError("invalid_field", "modes")
    if "normal" in unique and len(unique) > 1:
        raise DomainError("invalid_field", "modes")
    return unique


def validate_allowlist(value: Any) -> list[str]:
    """Validate allowlist: 0..50 distinct lowercase domain.object regex IDs <= 255."""
    if not isinstance(value, list) or len(value) > 50:
        raise DomainError("invalid_field", "entity_allowlist")
    seen = set()
    result = []
    for item in value:
        if (
            not isinstance(item, str)
            or len(item) > 255
            or not ENTITY_REGEX.fullmatch(item)
            or item.lower() != item
        ):
            raise DomainError("invalid_field", "entity_allowlist")
        if item in seen:
            raise DomainError("invalid_field", "entity_allowlist")
        seen.add(item)
        result.append(item)
    return result


def _validate_step(step: Any, allowlist: list[str] | set[str] | frozenset[str]) -> dict:
    if not isinstance(step, dict):
        raise DomainError("invalid_field", "steps")
    fields(step, STEP_FIELDS, {"title"})
    step_title = text(step["title"], "title", 255)

    offset_val = step.get("offset_minutes", 0)
    if type(offset_val) is not int or not 0 <= offset_val <= 10080:
        raise DomainError("invalid_field", "offset_minutes")

    conf_val = step.get("confirmation", "manual")
    if not isinstance(conf_val, str) or conf_val not in {"manual", "entity_state", "none"}:
        raise DomainError("invalid_field", "confirmation")

    raw_comp = step.get("completion_condition")
    comp_cond = condition(raw_comp, allowlist)

    if conf_val == "entity_state":
        if comp_cond is None or not entities(comp_cond):
            raise DomainError("invalid_field", "completion_condition")
    else:  # manual or none
        if comp_cond is not None:
            raise DomainError("invalid_field", "completion_condition")

    raw_skip = step.get("skip_when")
    skip_cond = condition(raw_skip, allowlist)

    escalate_val = step.get("escalate_minutes", 15)
    if escalate_val is not None:
        if type(escalate_val) is not int or not 1 <= escalate_val <= 1440:
            raise DomainError("invalid_field", "escalate_minutes")

    return {
        "title": step_title,
        "offset_minutes": offset_val,
        "confirmation": conf_val,
        "completion_condition": comp_cond,
        "skip_when": skip_cond,
        "escalate_minutes": escalate_val,
    }


def normalize_template(
    ctx: Context, value: Any, allowlist: list[str] | set[str] | frozenset[str] | None = None
) -> dict:
    """Validate a template without mutating the caller's dictionary."""
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "template")

    if allowlist is None:
        cfg = configuration(ctx.state)
        allowlist = cfg.get("entity_allowlist", [])

    title_val = text(value.get("title"), "title", 255)

    desc_raw = value.get("description", "")
    if desc_raw is None:
        desc_val = ""
    elif isinstance(desc_raw, str):
        if len(desc_raw) > 2000:
            raise DomainError("invalid_field", "description")
        desc_val = desc_raw.strip()
    else:
        raise DomainError("invalid_field", "description")

    raw_assignees = value.get("assignees")
    if not isinstance(raw_assignees, list) or not 1 <= len(raw_assignees) <= 20:
        raise DomainError("invalid_field", "assignees")
    assignees: list[str] = []
    seen_assignees = set()
    for m_id in raw_assignees:
        if not isinstance(m_id, str):
            raise DomainError("invalid_field", "assignees")
        member = ctx.member(m_id)
        if member.get("role") == "guest" or not member.get("active", True):
            raise DomainError("invalid_field", "assignees")
        if member["id"] in seen_assignees:
            raise DomainError("invalid_field", "assignees")
        seen_assignees.add(member["id"])
        assignees.append(member["id"])

    enabled_val = value.get("enabled")
    if type(enabled_val) is not bool:
        raise DomainError("invalid_field", "enabled")

    rule_raw = value.get("rule")
    rule_val = validate_recurrence(rule_raw) if rule_raw is not None else None

    skip_raw = value.get("skip_when")
    skip_val = condition(skip_raw, allowlist)

    raw_steps = value.get("steps")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 30:
        raise DomainError("invalid_field", "steps")

    normalized_steps = []
    prev_offset = -1
    for step in raw_steps:
        norm_step = _validate_step(step, allowlist)
        if norm_step["offset_minutes"] < prev_offset:
            raise DomainError("invalid_field", "offset_minutes")
        prev_offset = norm_step["offset_minutes"]
        normalized_steps.append(norm_step)

    result = deepcopy(value)
    result["title"] = title_val
    result["description"] = desc_val
    result["assignees"] = assignees
    result["enabled"] = enabled_val
    result["rule"] = rule_val
    result["skip_when"] = skip_val
    result["steps"] = normalized_steps
    return result
