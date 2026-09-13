"""Actual authenticated native Options, synthetic provider metadata/inference only."""

import json
from copy import deepcopy
from unittest.mock import patch


async def verify_provider_chain_options(hass, entry, form, post):
    from custom_components.family_assistant.assistant import provider as provider_module
    from custom_components.family_assistant.assistant.image_providers import ImageProvider
    from custom_components.family_assistant.domain.validation import DomainError

    initial = deepcopy(dict(entry.options))
    calls = []

    async def request_json(_session, method, url, **kwargs):
        calls.append((method, url))
        if url.endswith("/api/tags"):
            return {"models": [{"name": "synthetic-model"}]}
        assert method == "POST" and url.endswith("/api/chat")
        assert kwargs["json"]["model"] == "synthetic-model"
        if "gateway.example.invalid" in url:
            raise DomainError("provider_unreachable")
        return {"message": {"content": json.dumps({"reply": "synthetic typed response"})}}

    async def image_inspect(_provider):
        calls.append(("GET", "synthetic-image-metadata-only"))
        return {
            "available": True,
            "models": ["synthetic-diffusion"],
            "encoders": ["synthetic-encoder"],
            "vaes": ["synthetic-vae"],
        }

    def selected(result):
        return next(
            field["default"] for field in result["data_schema"] if field["name"] == "provider"
        )

    async def add(path, kind, name, url, **extra):
        result = await post(path, {"action": "add"})
        assert result["step_id"].endswith("_kind"), result
        result = await post(path, {"action": "continue", "kind": kind})
        assert result["step_id"].endswith("_edit"), result
        result = await post(
            path,
            {
                "action": "save",
                "name": name,
                "enabled": True,
                "url": url,
                "model": "synthetic-model",
                **extra,
            },
        )
        assert not result["errors"], result
        return selected(result)

    try:
        with (
            patch.object(provider_module, "request_json", request_json),
            patch.object(ImageProvider, "inspect", image_inspect),
        ):
            manager, path = await form("provider_chain")
            assert manager["step_id"] == "provider_chain"
            # Remove legacy-derived rows only in the draft. Their old slots remain.
            legacy_ids = [
                option["value"]
                for field in manager["data_schema"]
                if field["name"] == "provider"
                for option in field["selector"]["select"]["options"]
                if option["value"] != "_none"
            ]
            for identifier in legacy_ids:
                review = await post(path, {"action": "remove", "provider": identifier})
                assert review["step_id"] == "provider_chain_remove"
                denied = await post(path, {"action": "remove"})
                assert denied["errors"] == {"base": "invalid_field"}
                await post(path, {"action": "remove", "confirmed": True})
            gateway = await add(
                path,
                "agy",
                "Synthetic gateway",
                "https://gateway.example.invalid",
                api_key="synthetic-native-chain-key",
            )
            second = await add(path, "ollama", "Synthetic Qwen A", "https://qwen-a.example.invalid")
            third = await add(path, "ollama", "Synthetic Qwen B", "https://qwen-b.example.invalid")
            assert calls == [], "Configuring a provider must not make HTTP requests"
            result = await post(path, {"action": "test", "provider": second})
            assert result["step_id"] == "provider_chain_test" and not result["errors"]
            assert result["description_placeholders"]["models"] == "synthetic-model"
            assert calls == [("GET", "https://qwen-a.example.invalid/api/tags")]
            await post(path, {"action": "back"})
            await post(path, {"action": "move_up", "provider": third})
            await post(path, {"action": "move_down", "provider": third})
            assert (await post(path, {"action": "save", "enabled": True}))["type"] == "create_entry"
            await hass.async_block_till_done()
            rows = entry.options["conversation"]["providers"]
            assert [row["id"] for row in rows] == [gateway, second, third]
            assert entry.options["conversation"]["primary"] == initial["conversation"]["primary"]
            assert entry.options["synthetic_unrelated"] == initial["synthetic_unrelated"]
            cascade = entry.runtime_data.assistant.cascade
            assert [provider.url for provider in cascade.providers] == [row["url"] for row in rows]
            calls.clear()
            reply = await cascade.generate(
                [{"role": "user", "content": "Synthetic read-only response"}],
                {"type": "object"},
                lambda value: value,
            )
            assert reply == {"reply": "synthetic typed response"}
            assert calls == [
                ("POST", "https://gateway.example.invalid/api/chat"),
                ("POST", "https://qwen-a.example.invalid/api/chat"),
            ]
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            await entry.runtime_data.scheduler.stop()
            assert [
                provider.url for provider in entry.runtime_data.assistant.cascade.providers
            ] == [row["url"] for row in rows]

            manager, path = await form("provider_chain")
            edit = await post(path, {"action": "edit", "provider": gateway})
            assert "synthetic-native-chain-key" not in repr(edit)
            failed = await post(
                path, {"action": "save", "url": "https://new-gateway.example.invalid"}
            )
            assert failed["errors"] == {"base": "provider_key_scope"}
            await post(path, {"action": "save", "clear_key": True, "enabled": False})
            assert (await post(path, {"action": "save"}))["type"] == "create_entry"
            await hass.async_block_till_done()
            assert not entry.options["conversation"]["providers"][0].get("api_key")
            assert len(entry.runtime_data.assistant.cascade.providers) == 2

            manager, path = await form("image_generation")
            image = await add(
                path,
                "comfyui",
                "Synthetic offline images",
                "https://images.example.invalid",
                enabled=False,
                model="",
                workflow="z_image_turbo",
            )
            result = await post(path, {"action": "test", "provider": image})
            assert (
                not result["errors"]
                and result["description_placeholders"]["encoders"] == "synthetic-encoder"
            )
            await post(path, {"action": "back"})
            edit = await post(path, {"action": "edit", "provider": image})
            choices = next(
                field["selector"]["select"]["options"]
                for field in edit["data_schema"]
                if field["name"] == "model"
            )
            assert choices == ["synthetic-diffusion"]
            await post(
                path,
                {
                    "action": "save",
                    "model": "synthetic-diffusion",
                    "encoder": "synthetic-encoder",
                    "vae": "synthetic-vae",
                    "enabled": True,
                },
            )
            settings = await post(path, {"action": "settings"})
            assert settings["step_id"] == "image_generation_settings"
            await post(path, {"action": "save", "width": 768, "height": 1024, "steps": 8, "cfg": 1})
            assert (await post(path, {"action": "save", "enabled": True}))["type"] == "create_entry"
            await hass.async_block_till_done()
            assert entry.options["image_generation"]["providers"][0]["workflow"] == "z_image_turbo"
            assert entry.options["image_generation"]["steps"] == 8
            assert not entry.runtime_data.engine.snapshot().get("image_generation"), (
                "Provider credentials must not enter Store"
            )
            manager, path = await form("image_generation")
            await post(path, {"action": "remove", "provider": image})
            await post(path, {"action": "remove", "confirmed": True})
            assert (await post(path, {"action": "cancel"}))["type"] == "abort"
            assert len(entry.options["image_generation"]["providers"]) == 1

            manager, path = await form("provider_chain")
            for identifier in [gateway, second, third]:
                await post(path, {"action": "remove", "provider": identifier})
                await post(path, {"action": "remove", "confirmed": True})
            assert (await post(path, {"action": "save", "enabled": False}))[
                "type"
            ] == "create_entry"
            await hass.async_block_till_done()
            assert entry.options["conversation"]["providers"] == []
            assert entry.runtime_data.assistant is None
            assert entry.options["conversation"]["primary"] == initial["conversation"]["primary"]
            # Exercise the actual native/runtime contracts without any legacy
            # primary slot: a single AGY is sufficient for chat and articles.
            from ha_backup_smoke import _websocket

            actor = entry.runtime_data.engine.snapshot()["members"]["owner"]
            user = await hass.auth.async_get_user(actor["ha_user_id"])
            assert user is not None and user.is_active

            async def sources():
                response = await _websocket(
                    hass,
                    user,
                    {"id": 1976, "type": "family_assistant/view", "entry_id": entry.entry_id},
                )
                assert response["success"]
                view = response["result"]
                return view["conversation_source"], view["article_source"]

            single = deepcopy(dict(entry.options))
            single["conversation"] = {"enabled": True, "providers": [deepcopy(rows[0])]}
            single.pop("articles", None)
            hass.config_entries.async_update_entry(entry, options=single)
            await hass.async_block_till_done()
            await entry.runtime_data.scheduler.stop()
            assert "primary" not in entry.options["conversation"]
            assert [
                provider.kind for provider in entry.runtime_data.assistant.cascade.providers
            ] == ["agy"]
            chat, source = await sources()
            assert chat["configured"] and chat["allowed"] and chat["revision"]
            assert source["configured"] and not source["enabled"] and not source["allowed"]
            editor, article_path = await form("articles")
            assert editor["step_id"] == "articles"
            review = await post(article_path, {"enabled": True, "allow_children": False})
            assert review["step_id"] == "article_policy_review" and not review["errors"]
            assert (await post(article_path, {"confirmed": True}))["type"] == "create_entry"
            await hass.async_block_till_done()
            chat, source = await sources()
            assert source["configured"] and source["allowed"] and source["revision"]
            assert "synthetic-native-chain-key" not in repr((source, chat))
    finally:
        hass.config_entries.async_update_entry(entry, options=initial)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
    print(
        "PASS: actual HA ordered optional text/image provider Options, explicit metadata, "
        "fallback ordering, secret clearing, empty chain and reload"
    )
