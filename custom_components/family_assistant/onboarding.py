"""Pure, bounded readiness summary for the guided Options flow.

The summary intentionally contains only status enums and counts.  Connection
values, member identifiers and runtime error details never leave this module.
"""

from __future__ import annotations

from collections.abc import Mapping

from .const import LANGUAGES, MODULES
from .domain.household import timezone
from .domain.validation import DomainError

SCHEMA = 1
STATUSES = frozenset({"ready", "attention", "optional", "off"})
MAX_COUNT = 10_000


def _count(value: int) -> int:
    return min(max(value, 0), MAX_COUNT)


def _item(key: str, status: str, action: str, **counts: int) -> dict:
    if status not in STATUSES:
        raise ValueError(status)
    return {
        "key": key,
        "status": status,
        "action": action,
        "counts": {name: _count(value) for name, value in counts.items()},
    }


def _positive_int(value) -> bool:
    return type(value) is int and value > 0


def _nonzero_int(value) -> bool:
    return type(value) is int and value != 0


def _revision(value) -> bool:
    return type(value) is int and 1 <= value <= 2**53 - 1


def _text(value, maximum: int) -> bool:
    return isinstance(value, str) and len(value) <= maximum and bool(value.strip())


def _members(state: Mapping, actor_id: str) -> tuple[dict, list[dict], bool]:
    raw = state.get("members")
    if not isinstance(raw, Mapping):
        raise DomainError("forbidden")
    actor = raw.get(actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("active") is not True
        or actor.get("role") != "owner"
        or actor.get("id") != actor_id
        or actor.get("language") not in LANGUAGES
        or not _text(actor.get("name"), 80)
    ):
        raise DomainError("forbidden")
    current: list[dict] = []
    malformed = False
    for index, (member_id, member) in enumerate(raw.items()):
        if index >= MAX_COUNT:
            malformed = True
            break
        if not isinstance(member_id, str) or not isinstance(member, dict):
            malformed = True
            continue
        if member.get("active") is not True:
            if member.get("active") is not False:
                malformed = True
            continue
        if (
            member.get("id") != member_id
            or member.get("role") not in {"owner", "parent", "adult", "child", "guest"}
            or member.get("language") not in LANGUAGES
            or not _text(member.get("name"), 80)
            or not _revision(member.get("revision"))
            or (member.get("ha_user_id") is not None and not _text(member.get("ha_user_id"), 128))
            or (
                member.get("telegram_id") is not None
                and not _positive_int(member.get("telegram_id"))
            )
        ):
            malformed = True
            continue
        current.append(member)
    return actor, current, malformed


def _settings(state: Mapping) -> tuple[dict, set[str], bool]:
    settings = state.get("settings")
    if not isinstance(settings, dict):
        return {}, set(), True
    modules = settings.get("modules")
    module_error = (
        not isinstance(modules, list)
        or len(modules) > MAX_COUNT
        or any(not isinstance(value, str) or value not in MODULES for value in modules)
        or len(set(modules)) != len(modules)
    )
    enabled = set(modules) if not module_error else set()
    household_error = (
        not _text(settings.get("name"), 80) or settings.get("language") not in LANGUAGES
    )
    try:
        timezone(settings.get("timezone"))
    except DomainError:
        household_error = True
    return settings, enabled, household_error or module_error


def _telegram(
    state: Mapping,
    options: Mapping,
    members: list[dict],
    runtime_status: Mapping,
) -> dict:
    private_links = sum(_positive_int(member.get("telegram_id")) for member in members)
    telegram_state = state.get("telegram")
    group_linked = int(
        isinstance(telegram_state, Mapping) and _nonzero_int(telegram_state.get("group_id"))
    )
    config = options.get("telegram")
    if config is None:
        return _item(
            "telegram",
            "off",
            "telegram",
            private_links=private_links,
            group_linked=group_linked,
        )
    if not isinstance(config, Mapping) or type(config.get("enabled")) is not bool:
        status = "attention"
    elif config["enabled"] is False:
        status = "off"
    else:
        bot = config.get("bot")
        configured = (
            _text(config.get("token"), 4096)
            and isinstance(bot, Mapping)
            and _positive_int(bot.get("id"))
            and _text(bot.get("username"), 64)
        )
        status = (
            "ready" if configured and runtime_status.get("telegram_ready") is True else "attention"
        )
    return _item(
        "telegram",
        status,
        "telegram",
        private_links=private_links,
        group_linked=group_linked,
    )


def _models(options: Mapping, enabled: set[str], runtime_status: Mapping) -> dict:
    config = options.get("conversation")
    search_enabled = int(
        isinstance(config, Mapping)
        and isinstance(config.get("search"), Mapping)
        and bool(config["search"])
        and config["search"].get("enabled", True) is True
    )
    if "conversation" not in enabled:
        status = "off"
    elif config is None:
        status = "off"
    elif not isinstance(config, Mapping) or type(config.get("enabled")) is not bool:
        status = "attention"
    elif config["enabled"] is False:
        status = "off"
    else:
        primary = config.get("primary")
        ha_agent = config.get("ha_agent")
        configured = (
            isinstance(primary, Mapping)
            and _text(primary.get("url"), 2048)
            and _text(primary.get("model"), 128)
        ) or (
            isinstance(ha_agent, Mapping)
            and ha_agent.get("type") == "ha_agent"
            and _text(ha_agent.get("entity_id"), 128)
            and ha_agent["entity_id"].startswith("conversation.")
        )
        status = (
            "ready" if configured and runtime_status.get("assistant_ready") is True else "attention"
        )
    return _item("models", status, "conversation", search_enabled=search_enabled)


def _siren(options: Mapping, enabled: set[str], members: list[dict]) -> dict:
    if "alarms" not in enabled:
        return _item("siren", "off", "alarm_device", bindings=0)
    bindings = options.get("alarm_devices")
    if bindings is None or bindings == {}:
        return _item("siren", "optional", "alarm_device", bindings=0)
    if not isinstance(bindings, Mapping):
        return _item("siren", "attention", "alarm_device", bindings=0)
    current_ids = {member["id"] for member in members}
    valid = 0
    malformed = False
    for index, (member_id, binding) in enumerate(bindings.items()):
        if index >= MAX_COUNT:
            malformed = True
            break
        if (
            member_id not in current_ids
            or not isinstance(binding, Mapping)
            or not _text(binding.get("entity_id"), 255)
            or not binding["entity_id"].startswith("siren.")
            or binding.get("confirmed") is not True
        ):
            malformed = True
            continue
        valid += 1
    return _item(
        "siren",
        "attention" if malformed else "ready" if valid else "optional",
        "alarm_device",
        bindings=valid,
    )


def readiness(state, options, actor_id: str, runtime_status=None) -> dict:
    """Return a secret-free readiness summary for one already selected entry."""
    if not isinstance(state, Mapping) or not isinstance(actor_id, str):
        raise DomainError("forbidden")
    if not isinstance(options, Mapping):
        options = {}
        options_malformed = True
    else:
        options_malformed = False
    if runtime_status is None:
        runtime_status = {}
    if (
        not isinstance(runtime_status, Mapping)
        or len(runtime_status) > 2
        or any(
            key not in {"telegram_ready", "assistant_ready"} or type(value) is not bool
            for key, value in runtime_status.items()
        )
    ):
        runtime_status = {}
        options_malformed = True

    _actor, members, members_malformed = _members(state, actor_id)
    _current_settings, enabled, settings_malformed = _settings(state)
    active = len(members)
    ha_linked = sum(_text(member.get("ha_user_id"), 128) for member in members)
    telegram_linked = sum(_positive_int(member.get("telegram_id")) for member in members)
    unlinked = sum(
        not _text(member.get("ha_user_id"), 128) and not _positive_int(member.get("telegram_id"))
        for member in members
        if member.get("id") != actor_id
    )

    items = [
        _item(
            "household",
            "attention" if settings_malformed else "ready",
            "general",
            configured=0 if settings_malformed else 1,
        ),
        _item(
            "members",
            "attention" if members_malformed or unlinked else "ready",
            "member",
            active=active,
            ha_linked=ha_linked,
            telegram_linked=telegram_linked,
        ),
        _item(
            "modules",
            "attention" if settings_malformed else "ready",
            "general",
            enabled=len(enabled),
        ),
    ]
    external_runtime = runtime_status if not options_malformed else {}
    items.extend(
        (
            _telegram(state, options, members, external_runtime),
            _models(options, enabled, external_runtime),
            _siren(options, enabled, members),
        )
    )
    if options_malformed:
        for item in items[3:]:
            item["status"] = "attention"
    return {"schema": SCHEMA, "items": items}


def item(report: dict, key: str) -> dict:
    """Return one exact readiness item or fail closed on a malformed report."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise DomainError("invalid_field")
    rows = report.get("items")
    if not isinstance(rows, list):
        raise DomainError("invalid_field")
    matches = [row for row in rows if isinstance(row, dict) and row.get("key") == key]
    if len(matches) != 1 or matches[0].get("status") not in STATUSES:
        raise DomainError("invalid_field")
    return matches[0]
