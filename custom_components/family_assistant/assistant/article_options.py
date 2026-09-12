"""Owner-reviewed policy for explicit public article retrieval."""

from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from uuid import uuid4

import voluptuous as vol

from ..const import DOMAIN
from ..domain.validation import DomainError
from ..domain.validation import revision as strict_revision

DEFAULT_POLICY = {"enabled": False, "allow_children": False}
_STATE_PREFIX = "component.family_assistant.selector.article_policy_state.options."


def _digest(value) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise DomainError("invalid_field", "options") from None
    return hashlib.sha256(encoded).hexdigest()


def _policy(options) -> dict:
    if not isinstance(options, dict):
        raise DomainError("invalid_field", "articles")
    if "articles" not in options:
        return deepcopy(DEFAULT_POLICY)
    value = options["articles"]
    if not isinstance(value, dict) or set(value) != {
        "enabled",
        "allow_children",
        "revision",
    }:
        raise DomainError("invalid_field", "articles")
    if type(value["enabled"]) is not bool or type(value["allow_children"]) is not bool:
        raise DomainError("invalid_field", "articles")
    marker = value["revision"]
    if (
        not isinstance(marker, str)
        or len(marker) != 32
        or marker.lower() != marker
        or any(character not in "0123456789abcdef" for character in marker)
    ):
        raise DomainError("invalid_field", "articles")
    return deepcopy(value)


def _entry_current(flow, runtime) -> bool:
    try:
        from homeassistant.config_entries import ConfigEntryState
    except ImportError:
        return False
    entry = flow.config_entry
    entries = getattr(flow.hass, "config_entries", None)
    getter = getattr(entries, "async_get_entry", None)
    return bool(
        getattr(entry, "domain", None) == DOMAIN
        and getattr(entry, "state", None) is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None) is runtime
        and callable(getter)
        and getter(entry.entry_id) is entry
    )


async def _ha_user(flow):
    from ..flow_identity import user_id as flow_user_id

    user_id = flow_user_id(flow)
    getter = getattr(getattr(flow.hass, "auth", None), "async_get_user", None)
    if not isinstance(user_id, str) or not user_id or not callable(getter):
        raise DomainError("forbidden")
    user = getter(user_id)
    if inspect.isawaitable(user):
        user = await user
    if (
        user is None
        or getattr(user, "id", None) != user_id
        or getattr(user, "is_admin", False) is not True
        or getattr(user, "is_active", False) is not True
    ):
        raise DomainError("forbidden")
    return user


def _conversation_ready(runtime, state, options) -> bool:
    modules = state.get("settings", {}).get("modules", [])
    conversation = options.get("conversation")
    primary = conversation.get("primary") if isinstance(conversation, dict) else None
    ha_agent = conversation.get("ha_agent") if isinstance(conversation, dict) else None
    configured = (
        isinstance(primary, dict)
        and isinstance(primary.get("model"), str)
        and bool(primary["model"].strip())
    ) or (
        isinstance(ha_agent, dict)
        and ha_agent.get("type") == "ha_agent"
        and isinstance(ha_agent.get("entity_id"), str)
        and ha_agent["entity_id"].startswith("conversation.")
    )
    return bool(
        "conversation" in modules
        and isinstance(conversation, dict)
        and conversation.get("enabled") is True
        and configured
        and runtime.assistant is not None
    )


async def _scope(flow) -> dict:
    runtime, actor = flow._authorized_runtime()
    if not _entry_current(flow, runtime):
        raise DomainError("conflict")
    initial_state = runtime.engine.snapshot()
    initial_member = initial_state.get("members", {}).get(actor)
    if not isinstance(initial_member, dict):
        raise DomainError("forbidden")
    initial_marker = tuple(
        initial_member.get(key) for key in ("id", "revision", "active", "role", "ha_user_id")
    )
    user = await _ha_user(flow)
    # User lookup is an await boundary. Reauthorize before inspecting Options.
    current_runtime, current_actor = flow._authorized_runtime()
    if (
        current_runtime is not runtime
        or current_actor != actor
        or not _entry_current(flow, runtime)
    ):
        raise DomainError("conflict")
    state = runtime.engine.snapshot()
    member = state.get("members", {}).get(actor)
    current_marker = (
        tuple(member.get(key) for key in ("id", "revision", "active", "role", "ha_user_id"))
        if isinstance(member, dict)
        else None
    )
    if current_marker != initial_marker:
        raise DomainError("conflict")
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "owner"
        or member.get("ha_user_id") != user.id
    ):
        raise DomainError("forbidden")
    actor_revision = strict_revision(member.get("revision"))
    options = deepcopy(dict(flow.config_entry.options))
    policy = _policy(options)
    conversation = options.get("conversation")
    return {
        "runtime": runtime,
        "actor": actor,
        "actor_revision": actor_revision,
        "user_id": user.id,
        "entry_id": flow.config_entry.entry_id,
        "options_digest": _digest(options),
        "conversation_digest": _digest(conversation),
        "assistant": runtime.assistant,
        "conversation_module": "conversation" in state.get("settings", {}).get("modules", []),
        "ready": _conversation_ready(runtime, state, options),
        "policy": policy,
        "language": member.get("language")
        if member.get("language") in {"en", "ru", "uk"}
        else "en",
    }


def _same_scope(left, right) -> bool:
    keys = {
        "actor",
        "actor_revision",
        "user_id",
        "entry_id",
        "options_digest",
        "conversation_digest",
        "assistant",
        "conversation_module",
        "ready",
        "policy",
        "language",
    }
    return bool(
        isinstance(left, dict)
        and isinstance(right, dict)
        and left["runtime"] is right["runtime"]
        and all(
            left[key] is right[key] if key == "assistant" else left[key] == right[key]
            for key in keys
        )
    )


async def _localized_labels(flow, before) -> dict[str, str]:
    from homeassistant.helpers.translation import async_get_translations

    translations = await async_get_translations(
        flow.hass,
        before["language"],
        "selector",
        {DOMAIN},
    )
    after = await _scope(flow)
    if not _same_scope(before, after):
        raise DomainError("conflict")
    labels = {}
    for value in ("enabled", "disabled", "allowed", "not_allowed"):
        translated = translations.get(_STATE_PREFIX + value)
        if not isinstance(translated, str) or not translated.strip():
            raise DomainError("not_ready")
        labels[value] = translated
    return labels


def _editor_schema(policy):
    return vol.Schema(
        {
            vol.Required("enabled", default=policy["enabled"]): bool,
            vol.Required("allow_children", default=policy["allow_children"]): bool,
        }
    )


async def options_step(flow, user_input=None):
    """Select a policy and move to a separately named review step."""
    try:
        current = await _scope(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        displayed = getattr(flow, "_articles_displayed_scope", None)
        try:
            if not _same_scope(current, displayed):
                raise DomainError("conflict")
            if not isinstance(user_input, dict) or set(user_input) != {
                "enabled",
                "allow_children",
            }:
                raise DomainError("invalid_field")
            if (
                type(user_input["enabled"]) is not bool
                or type(user_input["allow_children"]) is not bool
            ):
                raise DomainError("invalid_field")
            if user_input["enabled"] and not current["ready"]:
                raise DomainError("provider_model_missing")
            selected = {
                "enabled": user_input["enabled"],
                "allow_children": user_input["allow_children"],
            }
            if all(selected[key] == current["policy"][key] for key in DEFAULT_POLICY):
                raise DomainError("invalid_transition")
            flow._article_policy_review = {
                "scope": displayed,
                "policy": {**selected, "revision": uuid4().hex},
            }
            return await review_step(flow)
        except DomainError as error:
            errors["base"] = error.code
    flow._articles_displayed_scope = current
    return flow.async_show_form(
        step_id="articles",
        data_schema=_editor_schema(current["policy"]),
        errors=errors,
    )


async def review_step(flow, user_input=None):
    """Commit only the exact, currently authorized policy that was reviewed."""
    review = getattr(flow, "_article_policy_review", None)
    if not isinstance(review, dict):
        return await options_step(flow)
    try:
        current = await _scope(flow)
        if not _same_scope(current, review["scope"]):
            raise DomainError("conflict")
        if review["policy"]["enabled"] and not current["ready"]:
            raise DomainError("provider_model_missing")
    except DomainError as error:
        flow._article_policy_review = None
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        if (
            not isinstance(user_input, dict)
            or set(user_input) != {"confirmed"}
            or type(user_input["confirmed"]) is not bool
        ):
            errors["base"] = "invalid_field"
        elif not user_input["confirmed"]:
            flow._article_policy_review = None
            return await options_step(flow)
        else:
            options = deepcopy(dict(flow.config_entry.options))
            if _digest(options) != current["options_digest"]:
                flow._article_policy_review = None
                return flow.async_abort(reason="conflict")
            options["articles"] = deepcopy(review["policy"])
            result = flow.async_create_entry(title="", data=options)
            if result.get("type") != "abort":
                flow._article_policy_review = None
            return result
    selected = review["policy"]
    try:
        labels = await _localized_labels(flow, current)
    except DomainError as error:
        flow._article_policy_review = None
        return flow.async_abort(reason=error.code)
    return flow.async_show_form(
        step_id="article_policy_review",
        data_schema=vol.Schema({vol.Required("confirmed", default=False): bool}),
        errors=errors,
        description_placeholders={
            "enabled": labels["enabled"] if selected["enabled"] else labels["disabled"],
            "children": labels["allowed"] if selected["allow_children"] else labels["not_allowed"],
        },
    )


__all__ = ["DEFAULT_POLICY", "options_step", "review_step"]
