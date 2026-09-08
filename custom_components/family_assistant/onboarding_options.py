"""Owner-only guided readiness Options flow mixin."""

from __future__ import annotations

from .const import DOMAIN
from .domain.validation import DomainError
from .domain.validation import revision as strict_revision
from .onboarding import item, readiness

_STATUS_PREFIX = f"component.{DOMAIN}.selector.onboarding_status.options."


def _entry_current(flow, runtime) -> bool:
    manager = getattr(flow.hass, "config_entries", None)
    getter = getattr(manager, "async_get_entry", None)
    if callable(getter) and getter(flow.config_entry.entry_id) is not flow.config_entry:
        return False
    return getattr(flow.config_entry, "runtime_data", None) is runtime


def _scope(flow) -> dict:
    runtime, actor_id = flow._authorized_runtime()
    if not _entry_current(flow, runtime):
        raise DomainError("conflict")
    state = runtime.engine.snapshot()
    members = state.get("members")
    member = members.get(actor_id) if isinstance(members, dict) else None
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "owner"
    ):
        raise DomainError("forbidden")
    report = readiness(
        state,
        flow.config_entry.options,
        actor_id,
        {
            "telegram_ready": runtime.telegram is not None,
            "assistant_ready": runtime.assistant is not None,
        },
    )
    return {
        "runtime": runtime,
        "actor": actor_id,
        "actor_revision": strict_revision(member.get("revision")),
        "language": member.get("language", "en"),
        "report": report,
    }


def _same_identity(left: dict, right: dict) -> bool:
    return (
        left["runtime"] is right["runtime"]
        and left["actor"] == right["actor"]
        and left["actor_revision"] == right["actor_revision"]
    )


async def _localized_scope(flow) -> tuple[dict, dict[str, str]]:
    from homeassistant.helpers.translation import async_get_translations

    before = _scope(flow)
    translations = await async_get_translations(
        flow.hass,
        before["language"],
        "selector",
        {DOMAIN},
    )
    current = _scope(flow)
    if not _same_identity(before, current) or current["language"] != before["language"]:
        raise DomainError("conflict")
    labels = {}
    for status in ("ready", "attention", "optional", "off"):
        translated = translations.get(_STATUS_PREFIX + status)
        if not isinstance(translated, str) or not translated.strip():
            raise DomainError("not_ready")
        labels[status] = translated
    return current, labels


def _placeholders(scope: dict, labels: dict[str, str]) -> dict[str, str]:
    report = scope["report"]
    household = item(report, "household")
    members = item(report, "members")
    modules = item(report, "modules")
    telegram = item(report, "telegram")
    models = item(report, "models")
    siren = item(report, "siren")
    return {
        "household_status": labels[household["status"]],
        "members_status": labels[members["status"]],
        "modules_status": labels[modules["status"]],
        "telegram_status": labels[telegram["status"]],
        "models_status": labels[models["status"]],
        "siren_status": labels[siren["status"]],
        "active_members": str(members["counts"]["active"]),
        "ha_linked_members": str(members["counts"]["ha_linked"]),
        "telegram_linked_members": str(members["counts"]["telegram_linked"]),
        "enabled_modules": str(modules["counts"]["enabled"]),
        "private_chats": str(telegram["counts"]["private_links"]),
        "group_links": str(telegram["counts"]["group_linked"]),
        "search_enabled": str(models["counts"]["search_enabled"]),
        "siren_bindings": str(siren["counts"]["bindings"]),
    }


class GuidedOnboardingMixin:
    """Add a read-only guide without changing Options or runtime state."""

    async def async_step_guided_onboarding(self, user_input=None):
        try:
            scope, labels = await _localized_scope(self)
        except DomainError as error:
            return self.async_abort(reason=error.code)
        menu = ["general", "member", "telegram"]
        if item(scope["report"], "telegram")["status"] == "ready":
            menu.extend(("telegram_member", "telegram_group"))
        menu.extend(("conversation", "ha_agent", "search"))
        if item(scope["report"], "siren")["status"] != "off":
            menu.append("alarm_device")
        menu.append("guided_finish")
        return self.async_show_menu(
            step_id="guided_onboarding",
            menu_options=menu,
            description_placeholders=_placeholders(scope, labels),
        )

    async def async_step_guided_finish(self, user_input=None):
        try:
            _scope(self)
        except DomainError as error:
            return self.async_abort(reason=error.code)
        return self.async_abort(reason="guided_finished")
