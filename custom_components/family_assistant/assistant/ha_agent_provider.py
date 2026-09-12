"""Verified Core 2026.8.2 Ollama adapter; no native Home Assistant control tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import llm

from ..const import DOMAIN
from ..domain.validation import DomainError
from .provider import ActorProviderUnavailable, ActorRequest

_BINDING_KEYS = {"config_entry_id", "config_subentry_id"}
_MEMBER_KEYS = ("id", "revision", "active", "role", "ha_user_id", "language")


def _digest(value):
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise DomainError("ha_agent_unsupported") from None
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, repr=False)
class TargetSnapshot:
    """Opaque, ephemeral selection proof; never persist provider objects or data."""

    registry: Any
    agent: Any
    entry: Any
    subentry: Any
    client: Any
    fingerprint: str

    @property
    def binding(self):
        return {
            "config_entry_id": self.entry.entry_id,
            "config_subentry_id": self.subentry.subentry_id,
        }


def _no_api(value):
    return (
        value is None
        or (isinstance(value, str) and value == "")
        or (isinstance(value, list) and not value)
    )


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite")
    return result


def _parse_result(result):
    if type(result) is not conversation.ConversationResult:
        raise DomainError("provider_bad_response")
    response = result.as_dict().get("response")
    if not isinstance(response, dict) or response.get("response_type") not in {
        "action_done",
        "query_answer",
    }:
        raise DomainError("provider_bad_response")
    try:
        content = response["speech"]["plain"]["speech"]
    except (KeyError, TypeError):
        raise DomainError("provider_bad_response") from None
    if not isinstance(content, str) or not content.strip() or len(content) > 20_000:
        raise DomainError("provider_bad_response")
    try:
        parsed = json.loads(
            content, object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_float
        )
    except (ValueError, TypeError, RecursionError):
        raise DomainError("provider_bad_response") from None
    if not isinstance(parsed, dict):
        raise DomainError("provider_bad_response")
    return parsed


def _input(messages, schema):
    if not isinstance(messages, list) or not messages or len(messages) > 64:
        raise DomainError("invalid_field", "messages")
    grouped = {"system": [], "user": []}
    for message in messages:
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or not isinstance(message["role"], str)
            or message["role"] not in grouped
            or not isinstance(message["content"], str)
        ):
            raise DomainError("invalid_field", "messages")
        grouped[message["role"]].append(message["content"])
    if not grouped["user"] or not isinstance(schema, dict):
        raise DomainError("invalid_field", "messages")
    try:
        encoded = json.dumps(schema, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise DomainError("invalid_field", "schema") from None
    system = "\n\n".join(
        [*grouped["system"], "Respond strictly in JSON matching the following schema:\n" + encoded]
    )
    user = "\n\n".join(grouped["user"])
    if len(system) + len(user) > 200_000:
        raise DomainError("invalid_field", "messages")
    return user, system


class HAConversationAgent:
    def __init__(self, hass, family_entry, config):
        required = {"type", "entity_id", "timeout"}
        if (
            not isinstance(config, dict)
            or not required <= set(config) <= required | {"binding"}
            or config.get("type") != "ha_agent"
            or not isinstance(config.get("entity_id"), str)
            or len(config["entity_id"]) > 128
            or not re.fullmatch(r"conversation\.[a-z0-9_]+", config["entity_id"])
            or type(config.get("timeout")) is not int
            or not 5 <= config["timeout"] <= 60
        ):
            raise DomainError("invalid_field", "ha_agent")
        if "binding" in config:
            binding = config["binding"]
            if (
                not isinstance(binding, dict)
                or set(binding) != _BINDING_KEYS
                or any(
                    not isinstance(value, str) or not value.strip() or len(value) > 128
                    for value in binding.values()
                )
            ):
                raise DomainError("invalid_field", "ha_agent")
        self.hass = hass
        self.family_entry = family_entry
        self.config = deepcopy(config)
        self.entity_id = config["entity_id"]
        self.timeout = config["timeout"]
        self._runtime = getattr(family_entry, "runtime_data", None)
        self._engine = getattr(self._runtime, "engine", None)

    def _target(self):
        from homeassistant.const import __version__

        if __version__ != "2026.8.2":
            raise DomainError("ha_agent_unsupported")
        try:
            from homeassistant.components.ollama.conversation import OllamaConversationEntity
        except ImportError:
            raise DomainError("ha_agent_unsupported") from None
        registry = er.async_get(self.hass).async_get(self.entity_id)
        if registry is None or registry.disabled_by is not None:
            raise DomainError("ha_agent_unavailable")
        if registry.domain != "conversation" or registry.platform != "ollama":
            raise DomainError("ha_agent_unsupported")
        agent = conversation.async_get_agent(self.hass, self.entity_id)
        if agent is None:
            raise DomainError("ha_agent_unavailable")
        if type(agent) is not OllamaConversationEntity:
            raise DomainError("ha_agent_unsupported")
        if agent.supported_features & conversation.ConversationEntityFeature.CONTROL:
            raise DomainError("ha_agent_unsupported")
        state = self.hass.states.get(self.entity_id)
        # ConversationEntity.state is last activity, not connection health. Before
        # its first request an available native entity legitimately has unknown.
        if not agent.available or state is None or state.state == "unavailable":
            raise DomainError("ha_agent_unavailable")
        entry = self.hass.config_entries.async_get_entry(registry.config_entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            raise DomainError("ha_agent_unavailable")
        if entry.domain != "ollama":
            raise DomainError("ha_agent_unsupported")
        subentry = entry.subentries.get(registry.config_subentry_id)
        if subentry is None:
            raise DomainError("ha_agent_unavailable")
        if agent.entry is not entry or agent.subentry is not subentry:
            raise DomainError("ha_agent_changed")
        mappings = (entry.data, entry.options, subentry.data)
        for values in mappings:
            if not isinstance(values, Mapping):
                raise DomainError("ha_agent_unsupported")
            if not _no_api(values.get("llm_hass_api")):
                raise DomainError("ha_agent_unsupported")
            prompt = values.get("prompt")
            if prompt is not None and prompt not in ("", llm.DEFAULT_INSTRUCTIONS_PROMPT):
                raise DomainError("ha_agent_unsupported")
        client = getattr(entry, "runtime_data", None)
        if client is None:
            raise DomainError("ha_agent_unavailable")
        proof = TargetSnapshot(
            registry,
            agent,
            entry,
            subentry,
            client,
            _digest([dict(values) for values in mappings]),
        )
        if "binding" in self.config and self.config["binding"] != proof.binding:
            raise DomainError("ha_agent_changed")
        return proof

    async def inspect(self):
        """No inference, no credentials copied, and no family option mutation."""
        return self._target()

    def validate_review(self, proof):
        try:
            current = self._target()
        except DomainError:
            raise DomainError("ha_agent_changed") from None
        if (
            not isinstance(proof, TargetSnapshot)
            or any(
                getattr(current, key) is not getattr(proof, key)
                for key in ("registry", "agent", "entry", "subentry", "client")
            )
            or current.fingerprint != proof.fingerprint
        ):
            raise DomainError("ha_agent_changed")

    def _member(self, request):
        entry = self.family_entry
        if (
            self._runtime is None
            or self._engine is None
            or self.hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or entry.runtime_data is not self._runtime
            or self._runtime.engine is not self._engine
            or self.hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
            is not self._runtime
        ):
            raise DomainError("conflict")
        options = entry.options.get("conversation")
        if (
            not isinstance(options, Mapping)
            or options.get("enabled") is not True
            or options.get("ha_agent") != self.config
        ):
            raise DomainError("ha_agent_changed")
        if not isinstance(request, ActorRequest):
            raise DomainError("forbidden")
        state = self._engine.snapshot()
        member = state.get("members", {}).get(request.actor)
        if (
            not isinstance(member, dict)
            or member.get("id") != request.actor
            or member.get("active") is not True
            or member.get("role") not in {"owner", "parent", "adult", "child"}
        ):
            raise DomainError("forbidden")
        if (
            type(member.get("revision")) is not int
            or member["revision"] != request.revision
            or member.get("language") != request.language
            or "conversation" not in state.get("settings", {}).get("modules", [])
        ):
            raise DomainError("conflict")
        return member

    async def generate_for_actor(self, messages, schema, request):
        if any(isinstance(message, dict) and message.get("images") for message in messages):
            # Core conversation.async_converse has no image input in this adapter.
            # Do not silently answer a photo request using only its caption.
            raise ActorProviderUnavailable("provider_images_unsupported")
        text, system = _input(messages, schema)
        member = self._member(request)
        proof = self._target()
        marker = tuple(member.get(key) for key in _MEMBER_KEYS)
        user_id = member.get("ha_user_id")
        if not isinstance(user_id, str) or not user_id:
            raise ActorProviderUnavailable("ha_agent_account_required")

        def guard():
            current = self._member(request)
            if tuple(current.get(key) for key in _MEMBER_KEYS) != marker:
                raise DomainError("forbidden")
            self.validate_review(proof)

        def check_user(user):
            if (
                user is None
                or user.id != user_id
                or user.is_active is not True
                or not user.permissions.check_entity(self.entity_id, POLICY_READ)
            ):
                raise DomainError("forbidden")

        user = await self.hass.auth.async_get_user(user_id)
        guard()
        check_user(user)
        error = None
        try:
            async with asyncio.timeout(self.timeout):
                result = await conversation.async_converse(
                    hass=self.hass,
                    text=text,
                    conversation_id=None,
                    context=Context(user_id=user_id),
                    language=request.language,
                    agent_id=self.entity_id,
                    extra_system_prompt=system,
                )
        except TimeoutError:
            error = "provider_timeout"
        except Exception:  # noqa: BLE001 - never expose native/provider error contents
            error = "provider_unreachable"
        guard()
        current_user = await self.hass.auth.async_get_user(user_id)
        guard()
        if current_user is not user:
            raise DomainError("forbidden")
        check_user(current_user)
        if error:
            raise DomainError(error)
        return _parse_result(result)

    async def generate(self, messages, schema):
        """An absent server-supplied actor never becomes the household owner."""
        raise DomainError("forbidden")
