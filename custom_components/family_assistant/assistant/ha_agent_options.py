"""Owner-reviewed selection of a bounded existing Home Assistant agent."""

from copy import deepcopy

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from ..const import DOMAIN
from ..domain.validation import DomainError
from ..domain.validation import revision as strict_revision
from .chat_service import conversation_digest

_PREFIX = "component.family_assistant.selector.ha_agent_state.options."


def _read_scope(flow):
    runtime, actor = flow._authorized_runtime()
    entry = flow.config_entry
    if (
        entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
        or flow.hass.config_entries.async_get_entry(entry.entry_id) is not entry
        or entry.runtime_data is not runtime
    ):
        raise DomainError("conflict")
    state = runtime.engine.snapshot()
    member = state.get("members", {}).get(actor)
    user_id = flow.context.get("user_id")
    if (
        not isinstance(member, dict)
        or member.get("id") != actor
        or member.get("active") is not True
        or member.get("role") != "owner"
        or not isinstance(user_id, str)
        or not user_id
        or member.get("ha_user_id") != user_id
    ):
        raise DomainError("forbidden")
    strict_revision(member.get("revision"))
    options = deepcopy(dict(entry.options))
    return {
        "runtime": runtime,
        "engine": runtime.engine,
        "entry_id": entry.entry_id,
        "actor": actor,
        "revision": member["revision"],
        "user_id": user_id,
        "language": member.get("language", "en"),
        "module": "conversation" in state.get("settings", {}).get("modules", []),
        "digest": conversation_digest(options),
        "options": options,
    }


def _same(left, right):
    return (
        isinstance(left, dict)
        and isinstance(right, dict)
        and left["runtime"] is right["runtime"]
        and left["engine"] is right["engine"]
        and all(left[key] == right[key] for key in left if key not in {"runtime", "engine"})
    )


async def _scope(flow):
    before = _read_scope(flow)
    user = await flow.hass.auth.async_get_user(before["user_id"])
    after = _read_scope(flow)
    if not _same(before, after):
        raise DomainError("conflict")
    if (
        user is None
        or user.id != before["user_id"]
        or user.is_active is not True
        or user.is_admin is not True
    ):
        raise DomainError("forbidden")
    return after


def _schema(options):
    conversation = options.get("conversation", {})
    config = conversation.get("ha_agent", {})
    schema = {
        vol.Required("enabled", default=bool(config) and conversation.get("enabled") is True): bool,
        vol.Required("timeout", default=config.get("timeout", 15)): vol.All(
            int, vol.Range(min=5, max=45)
        ),
    }
    entity_key = (
        vol.Optional("entity_id", default=config["entity_id"])
        if config
        else vol.Optional("entity_id")
    )
    schema[entity_key] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="conversation")
    )
    return vol.Schema(schema)


async def options_step(flow, user_input=None):
    try:
        current = await _scope(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        try:
            if not _same(current, getattr(flow, "_ha_agent_displayed", None)):
                raise DomainError("conflict")
            if (
                not isinstance(user_input, dict)
                or not {"enabled", "timeout"}
                <= set(user_input)
                <= {"enabled", "timeout", "entity_id"}
                or type(user_input["enabled"]) is not bool
                or type(user_input["timeout"]) is not int
                or not 5 <= user_input["timeout"] <= 45
            ):
                raise DomainError("invalid_field")
            options = deepcopy(current["options"])
            conversation = options.setdefault("conversation", {})
            provider = proof = None
            if user_input["enabled"]:
                if not current["module"]:
                    raise DomainError("module_disabled")
                from .ha_agent_provider import HAConversationAgent

                selected = {
                    "type": "ha_agent",
                    "entity_id": user_input.get("entity_id"),
                    "timeout": user_input["timeout"],
                }
                provider = HAConversationAgent(flow.hass, flow.config_entry, selected)
                try:
                    proof = await provider.inspect()
                except DomainError:
                    after = await _scope(flow)
                    if not _same(current, after):
                        raise DomainError("conflict") from None
                    raise
                after = await _scope(flow)
                if not _same(current, after):
                    raise DomainError("conflict")
                provider.validate_review(proof)
                conversation["ha_agent"] = {**selected, "binding": proof.binding}
                conversation["enabled"] = True
            else:
                conversation.pop("ha_agent", None)
                if not conversation.get("primary"):
                    conversation["enabled"] = False
            if options == current["options"]:
                raise DomainError("invalid_transition")
            flow._ha_agent_review = {
                "scope": current,
                "options": options,
                "provider": provider,
                "proof": proof,
                "enabled": user_input["enabled"],
                "entity": conversation.get("ha_agent", {}).get("entity_id", "—"),
            }
            return await review_step(flow)
        except DomainError as error:
            if error.code in {"conflict", "forbidden", "ha_agent_changed"}:
                flow._ha_agent_review = None
                return flow.async_abort(reason=error.code)
            errors["base"] = error.code
    flow._ha_agent_displayed = current
    return flow.async_show_form(
        step_id="ha_agent",
        data_schema=_schema(current["options"]),
        errors=errors,
    )


async def review_step(flow, user_input=None):
    review = getattr(flow, "_ha_agent_review", None)
    if not isinstance(review, dict):
        return await options_step(flow)
    try:
        current = await _scope(flow)
        if not _same(current, review["scope"]):
            raise DomainError("conflict")
        if review["provider"] is not None:
            review["provider"].validate_review(review["proof"])
    except DomainError as error:
        flow._ha_agent_review = None
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
            flow._ha_agent_review = None
            return await options_step(flow)
        else:
            result = flow.async_create_entry(title="", data=deepcopy(review["options"]))
            flow._ha_agent_review = None
            return result
    try:
        labels = await async_get_translations(flow.hass, current["language"], "selector", {DOMAIN})
        if not _same(current, await _scope(flow)):
            raise DomainError("conflict")
        if review["provider"] is not None:
            review["provider"].validate_review(review["proof"])
        state = labels.get(_PREFIX + ("enabled" if review["enabled"] else "disabled"))
        if not isinstance(state, str) or not state.strip():
            raise DomainError("not_ready")
    except DomainError as error:
        flow._ha_agent_review = None
        return flow.async_abort(reason=error.code)
    return flow.async_show_form(
        step_id="ha_agent_review",
        data_schema=vol.Schema({vol.Required("confirmed", default=False): bool}),
        errors=errors,
        description_placeholders={"entity": review["entity"], "state": state},
    )
