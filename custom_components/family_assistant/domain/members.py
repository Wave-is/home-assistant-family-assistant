"""Member management with owner protection and unique channel identities."""

from __future__ import annotations

from ..const import LANGUAGES, ROLES
from .context import Context
from .validation import DomainError, enum, fields, text
from .validation import revision as strict_revision


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if ctx.actor["role"] != "owner":
        raise DomainError("forbidden")
    if action != "save":
        raise DomainError("unknown_action")
    fields(
        payload,
        {"id", "revision", "name", "role", "language", "aliases", "ha_user_id", "active"},
        {"name", "role"},
    )
    member_id = text(payload["id"], "id", 80) if "id" in payload else None
    existing = ctx.state["members"].get(member_id, {}) if member_id else {}
    if existing:
        existing = ctx.record("members", member_id, strict_revision(payload.get("revision")))
    elif "revision" in payload:
        if member_id:
            raise DomainError("not_found")
        raise DomainError("invalid_field", "revision")
    if member_id is None:
        member_id = ctx.identifier("M")
    role = enum(payload["role"], ROLES, "role")
    language = enum(payload.get("language", existing.get("language", "en")), LANGUAGES, "language")
    active = payload.get("active", existing.get("active", True))
    if not isinstance(active, bool):
        raise DomainError("invalid_field", "active")
    aliases = payload.get("aliases", existing.get("aliases", []))
    if not isinstance(aliases, list) or len(aliases) > 20:
        raise DomainError("invalid_field", "aliases")
    aliases = [text(alias, "aliases", 80) for alias in aliases]
    user_id = payload.get("ha_user_id", existing.get("ha_user_id"))
    if user_id is not None:
        user_id = text(user_id, "ha_user_id", 128)
        if any(
            m.get("ha_user_id") == user_id and m["id"] != member_id
            for m in ctx.state["members"].values()
        ):
            raise DomainError("duplicate_identity")
    if existing.get("role") == "owner" and (role != "owner" or not active or not user_id):
        owners = [
            m
            for m in ctx.state["members"].values()
            if m["id"] != member_id
            and m["role"] == "owner"
            and m.get("active", True)
            and m.get("ha_user_id")
        ]
        if not owners:
            raise DomainError("last_owner")
    member = {
        **existing,
        "id": member_id,
        "name": text(payload["name"], "name", 80),
        "role": role,
        "language": language,
        "aliases": aliases,
        "ha_user_id": user_id,
        "active": active,
    }
    ctx.state["members"][member_id] = ctx.touch(member)
    return member
