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
from .domain.validation import DomainError, text
from .telegram.errors import ERRORS
from .telegram.router import COPY


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
        self._entry = entry
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def supported_languages(self):
        return list(LANGUAGES)

    @property
    def available(self):
        return bool(
            self._entry.runtime_data is self._runtime
            and self._runtime.chat is not None
            and "conversation" in self._runtime.engine.snapshot()["settings"]["modules"]
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self._runtime.listeners.discard(self.async_write_ha_state))

    async def _async_handle_message(self, user_input, chat_log):
        language = user_input.language if user_input.language in LANGUAGES else "en"
        response = intent.IntentResponse(language=language)
        failed = False
        result_conversation_id = chat_log.conversation_id
        try:
            from .assistant.ha_scope import capture, retire_legacy_refs

            context = user_input.context
            context_id = text(getattr(context, "id", None), "context_id", 128)
            content = text(user_input.text, "text", 4096)
            scope = await capture(
                self.hass,
                self._entry.entry_id,
                getattr(context, "user_id", None),
                expected_runtime=self._runtime,
            )
            language = scope.language
            operation = (
                "assist:"
                + hashlib.sha256(
                    f"{scope.actor}:{scope.actor_revision}:{context_id}".encode()
                ).hexdigest()
            )
            conversation_id = chat_log.conversation_id or context_id
            result_conversation_id = conversation_id
            session = (
                "assist-session:"
                + hashlib.sha256(
                    f"{scope.actor}:{scope.actor_revision}:{conversation_id}".encode()
                ).hexdigest()
            )
            now = dt_util.utcnow()
            await retire_legacy_refs(scope, now)
            reply = await scope.chat.answer(
                runtime=scope.runtime,
                actor=scope.actor,
                actor_revision=scope.actor_revision,
                content=content,
                operation_id=operation,
                session_id=session,
                now=now,
                guard=scope.locked_guard,
                scope_check=scope.check,
                on_commit=scope.notify,
            )
            await scope.check()
        except (DomainError, TimeoutError, OSError) as err:
            failed = True
            code = (
                err.code
                if isinstance(err, DomainError)
                else ("provider_timeout" if isinstance(err, TimeoutError) else "storage_error")
            )
            reply = COPY[language]["error"].format(error=ERRORS[language].get(code, code))
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=user_input.agent_id, content=reply)
        )
        if failed:
            response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, reply)
        else:
            response.async_set_speech(reply)
        return ConversationResult(response=response, conversation_id=result_conversation_id)
