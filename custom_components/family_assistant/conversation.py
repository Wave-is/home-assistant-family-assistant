"""Standard HA conversation entity; every turn resolves the real HA user."""

import hashlib

from homeassistant.components.conversation import (
    AssistantContent,
    ConversationEntity,
    ConversationEntityFeature,
    ConversationResult,
)
from homeassistant.core import callback
from homeassistant.helpers import intent
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LANGUAGES
from .domain.validation import DomainError
from .telegram.errors import ERRORS
from .telegram.router import COPY, route


async def async_setup_entry(hass, entry, async_add_entities):
    added = False

    @callback
    def ensure_entity():
        nonlocal added
        if (
            not added
            and "conversation" in entry.runtime_data.engine.snapshot()["settings"]["modules"]
        ):
            added = True
            async_add_entities([FamilyConversation(entry)])

    entry.runtime_data.listeners.add(ensure_entity)
    entry.async_on_unload(lambda: entry.runtime_data.listeners.discard(ensure_entity))
    ensure_entity()


class FamilyConversation(ConversationEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "assistant"
    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(self, entry):
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def supported_languages(self):
        return list(LANGUAGES)

    @property
    def available(self):
        return "conversation" in self._runtime.engine.snapshot()["settings"]["modules"]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self._runtime.listeners.discard(self.async_write_ha_state))

    async def _async_handle_message(self, user_input, chat_log):
        language = user_input.language if user_input.language in LANGUAGES else "en"
        response = intent.IntentResponse(language=language)
        try:
            engine = self._runtime.engine
            actor = engine.actor_for_ha(user_input.context.user_id)
            role = engine.view(actor)["role"]
            if not self.available:
                raise DomainError("module_disabled")
            operation = (
                "assist:"
                + hashlib.sha256(
                    f"{actor}:{user_input.context.id}:{user_input.text}".encode()
                ).hexdigest()
            )
            conversation_key = hashlib.sha256(
                f"{actor}:{chat_log.conversation_id}".encode()
            ).hexdigest()
            # Only receipts from this actor/session are usable, never arbitrary chat_log text.
            refs = (
                engine.snapshot()["memory"].get("conversation_refs", {}).get(conversation_key, [])
            )

            async def fallback(actor, content, operation_id, now, refs):
                if not self._runtime.assistant:
                    raise DomainError("provider_not_configured")
                return await self._runtime.assistant.respond(
                    actor, content, operation_id, now, refs
                )

            reply = await route(
                engine, actor, user_input.text, operation, dt_util.utcnow(), refs, fallback=fallback
            )
            if (
                engine.actor_for_ha(user_input.context.user_id) != actor
                or engine.view(actor)["role"] != role
            ):
                raise DomainError("forbidden")

            def save_refs(ctx):
                from .telegram.context import result_refs

                result = ctx.state["processed"].get(operation, {}).get("result", {})
                if result:
                    ctx.state["memory"].setdefault("conversation_refs", {})[conversation_key] = (
                        result_refs(result)
                    )

            await engine.system_update("conversation_context", dt_util.utcnow(), save_refs)
            self._runtime.updated()
        except (DomainError, TimeoutError, OSError) as err:
            code = (
                err.code
                if isinstance(err, DomainError)
                else ("provider_timeout" if isinstance(err, TimeoutError) else "storage_error")
            )
            reply = COPY[language]["error"].format(error=ERRORS[language].get(code, code))
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=user_input.agent_id, content=reply)
        )
        response.async_set_speech(reply)
        return ConversationResult(response=response, conversation_id=chat_log.conversation_id)
