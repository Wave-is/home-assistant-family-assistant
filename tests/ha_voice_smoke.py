"""Actual authenticated Assist PCM/STT/intent path; synthetic recognizer/model only."""

import asyncio
from copy import deepcopy
from types import MappingProxyType
from uuid import uuid4

from aiohttp import ClientSession


async def verify_voice_shopping(hass, owner):
    from homeassistant.auth.const import GROUP_ID_USER
    from homeassistant.components import stt
    from homeassistant.components.assist_pipeline.pipeline import async_setup_pipeline_store
    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.storage import Store
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant.assistant.provider import Cascade
    from custom_components.family_assistant.assistant.service import Assistant
    from custom_components.family_assistant.telegram.proposal_reply import VOICE_PREVIEW

    class Recognizer(stt.SpeechToTextEntity):
        _attr_name = "Synthetic private STT"
        _attr_unique_id = "family-voice-smoke-stt"

        def __init__(self):
            self.transcript = ""
            self.inputs = []

        @property
        def supported_languages(self):
            return ["en", "ru", "uk"]

        @property
        def supported_formats(self):
            return [stt.AudioFormats.WAV]

        @property
        def supported_codecs(self):
            return [stt.AudioCodecs.PCM]

        @property
        def supported_bit_rates(self):
            return [stt.AudioBitRates.BITRATE_16]

        @property
        def supported_sample_rates(self):
            return [stt.AudioSampleRates.SAMPLERATE_16000]

        @property
        def supported_channels(self):
            return [stt.AudioChannels.CHANNEL_MONO]

        async def async_process_audio_stream(self, metadata, stream):
            data = b"".join([chunk async for chunk in stream])
            assert data, "PCM audio must actually reach the native STT entity"
            assert metadata.sample_rate == 16000 and metadata.bit_rate == 16
            self.inputs.append((metadata.language, len(data)))
            return stt.SpeechResult(self.transcript, stt.SpeechResultState.SUCCESS)

    class Planner:
        def __init__(self):
            self.calls = []
            self.name = "Synthetic voice milk"

        async def generate(self, messages, schema):
            self.calls.append(deepcopy(messages))
            return {
                "kind": "commands",
                "commands": [{"action": "shopping.add", "payload": {"name": self.name}}],
            }

    assert await async_setup_component(hass, "assist_pipeline", {})
    recognizer = Recognizer()
    await hass.data[stt.DATA_COMPONENT].async_add_entities([recognizer])
    pipeline_data = await async_setup_pipeline_store(hass)
    outsider = await hass.auth.async_create_user(
        "Synthetic voice outsider", group_ids=[GROUP_ID_USER]
    )

    async def speak(user, pipeline_id, content, conversation_id=None):
        recognizer.transcript = content
        refresh = await hass.auth.async_create_refresh_token(
            user, client_id="https://example.invalid/voice-smoke"
        )
        try:
            async with ClientSession() as client:
                async with client.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
                    assert (await ws.receive_json())["type"] == "auth_required"
                    await ws.send_json(
                        {
                            "type": "auth",
                            "access_token": hass.auth.async_create_access_token(refresh),
                        }
                    )
                    assert (await ws.receive_json())["type"] == "auth_ok"
                    await ws.send_json(
                        {
                            "id": 1,
                            "type": "assist_pipeline/run",
                            "pipeline": pipeline_id,
                            "start_stage": "stt",
                            "end_stage": "intent",
                            "input": {"sample_rate": 16000},
                            "timeout": 25,
                            "conversation_id": conversation_id,
                        }
                    )
                    events, handler_id = [], None
                    async with asyncio.timeout(30):
                        while True:
                            response = await ws.receive_json()
                            if response["type"] == "result":
                                assert response["success"], response
                                continue
                            assert response["type"] == "event", response
                            event = response["event"]
                            events.append(event)
                            assert event["type"] != "error", event
                            if event["type"] == "run-start":
                                handler_id = event["data"]["runner_data"]["stt_binary_handler_id"]
                            elif event["type"] == "stt-start":
                                assert isinstance(handler_id, int)
                                await ws.send_bytes(bytes([handler_id]) + b"\x01\x00" * 3200)
                                await ws.send_bytes(bytes([handler_id]))
                            elif event["type"] == "run-end":
                                break
                    assert (
                        next(e for e in events if e["type"] == "stt-end")["data"]["stt_output"][
                            "text"
                        ]
                        == content
                    )
                    return next(e for e in events if e["type"] == "intent-end")["data"][
                        "intent_output"
                    ]
        finally:
            hass.auth.async_remove_refresh_token(refresh)

    phrases = {
        "en": ("Please add synthetic voice milk", "confirm the proposal", "cancel the proposal"),
        "ru": ("Добавь синтетическое молоко", "подтверждаю предложение", "отмени предложение"),
        "uk": ("Додай синтетичне молоко", "підтверджую пропозицію", "скасуй пропозицію"),
    }
    for language, (request, confirm, cancel) in phrases.items():
        family = ConfigEntry(
            domain="family_assistant",
            title="Synthetic voice family " + language,
            data={
                "owner_user_id": owner.id,
                "owner_name": "Synthetic voice parent",
                "language": language,
                "modules": ["shopping", "conversation"],
            },
            options={"conversation": {"enabled": False}},
            version=1,
            minor_version=1,
            source="user",
            unique_id=None,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        await hass.config_entries.async_add(family)
        try:
            await hass.async_block_till_done()
            assert family.state is ConfigEntryState.LOADED
            runtime = family.runtime_data
            planner = Planner()
            runtime.assistant = Assistant(runtime.engine, Cascade([planner], {}))
            agent = next(
                r.entity_id
                for r in er.async_get(hass).entities.values()
                if r.domain == "conversation" and r.config_entry_id == family.entry_id
            )
            pipeline = await pipeline_data.pipeline_store.async_create_item(
                {
                    "name": "Synthetic voice " + language,
                    "language": language,
                    "conversation_engine": agent,
                    "conversation_language": language,
                    "stt_engine": recognizer.entity_id,
                    "stt_language": language,
                    "tts_engine": None,
                    "tts_language": None,
                    "tts_voice": None,
                    "wake_word_entity": None,
                    "wake_word_id": None,
                    "prefer_local_intents": False,
                }
            )
            before = runtime.engine.snapshot()["shopping"]
            preview = await speak(owner, pipeline.id, request)
            proposal = next(iter(runtime.engine.snapshot()["proposals"].values()))
            assert runtime.engine.snapshot()["shopping"] == before and len(planner.calls) == 1
            speech = preview["response"]["speech"]["plain"]["speech"]
            assert VOICE_PREVIEW[language].format(preview=proposal["preview"]) == speech
            assert proposal["id"] not in speech
            session = preview["conversation_id"]
            # A real HA outsider cannot reuse another person's native chat session.
            rejected = await speak(outsider, pipeline.id, confirm, session)
            assert rejected["response"]["response_type"] == "error"
            assert runtime.engine.snapshot()["shopping"] == before and len(planner.calls) == 1
            # A fresh conversation never guesses another session's pending proposal.
            missing = await speak(owner, pipeline.id, confirm)
            assert missing["response"]["response_type"] == "error"
            assert len(planner.calls) == 1 and runtime.engine.snapshot()["shopping"] == before
            # Pending proposal + actor-scoped references survive native entry reload.
            assert await hass.config_entries.async_unload(family.entry_id)
            assert await hass.config_entries.async_setup(family.entry_id)
            await hass.async_block_till_done()
            runtime = family.runtime_data
            runtime.assistant = Assistant(runtime.engine, Cascade([planner], {}))
            applied = await speak(owner, pipeline.id, confirm, session)
            assert applied["response"]["response_type"] != "error", applied
            assert len(runtime.engine.snapshot()["shopping"]) == len(before) + 1
            assert len(planner.calls) == 1
            again = await speak(owner, pipeline.id, confirm, session)
            assert again["response"]["response_type"] == "error"
            assert len(runtime.engine.snapshot()["shopping"]) == len(before) + 1
            # Cancellation is equally explicit and uses no second model request.
            planner.name = "Synthetic voice cancelled bread"
            proposed = await speak(owner, pipeline.id, request)
            cancelled = await speak(owner, pipeline.id, cancel, proposed["conversation_id"])
            assert cancelled["response"]["response_type"] != "error"
            assert (
                len(planner.calls) == 2
                and len(runtime.engine.snapshot()["shopping"]) == len(before) + 1
            )
            stored = await Store(hass, 1, f"family_assistant.{family.entry_id}").async_load()
            assert stored["shopping"] == runtime.engine.snapshot()["shopping"]
            assert recognizer.inputs[-1][0] == language
            # Child voice review creates a parent-review proposal, not an approved item.
            child_user = await hass.auth.async_create_user(
                "Synthetic voice child", group_ids=[GROUP_ID_USER]
            )
            member = await runtime.engine.execute(
                "owner",
                "members.save",
                {
                    "name": "Synthetic voice child",
                    "role": "child",
                    "language": language,
                    "ha_user_id": child_user.id,
                },
                uuid4().hex,
                dt_util.utcnow(),
            )
            planner.name = "Synthetic child voice fruit"
            child_preview = await speak(child_user, pipeline.id, request)
            child_result = await speak(
                child_user, pipeline.id, confirm, child_preview["conversation_id"]
            )
            assert child_result["response"]["response_type"] != "error", child_result
            child_item = next(
                i
                for i in runtime.engine.snapshot()["shopping"].values()
                if i["name"] == planner.name
            )
            assert child_item["status"] == "pending" and child_item["creator"] == member["id"]
        finally:
            if family.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(family.entry_id)
    print(
        "PASS: actual authenticated Assist PCM/STT/intent EN/RU/UK shopping preview, "
        "spoken confirmation/cancel, child approval boundary, outsider/session denial, "
        "native reload and Store"
    )
