"""Real native draft/scoping logic; only remote metadata is synthetic."""

import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest
import voluptuous as vol
from test_provider_options import config_flow, native  # noqa: F401

from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def chain(native, monkeypatch):  # noqa: F811
    class Select:
        def __init__(self, config):
            self.config = config

        def __call__(self, value):
            options = [
                item.get("value") if isinstance(item, dict) else item
                for item in self.config["options"]
            ]
            if value not in options and not self.config.get("custom_value"):
                raise vol.Invalid("selection")
            return value

    monkeypatch.setattr(sys.modules["homeassistant.helpers.selector"], "SelectSelector", Select)
    return native


async def submit(flow, form, values):
    assert form["type"] == "form", form
    return await getattr(flow, "async_step_" + form["step_id"])(form["data_schema"](values))


def text_row(identifier="first", **values):
    return {
        "id": identifier,
        "kind": "ollama",
        "name": identifier,
        "enabled": True,
        "url": "https://model.example.invalid",
        "model": "synthetic-qwen",
        **values,
    }


def image_row(identifier="image", **values):
    return {
        "id": identifier,
        "type": "comfyui",
        "name": identifier,
        "enabled": True,
        "url": "https://images.example.invalid",
        "model": "synthetic-checkpoint",
        **values,
    }


async def add(flow, manager, kind="ollama", **values):
    manager = await submit(flow, manager, {"action": "add"})
    manager = await submit(flow, manager, {"action": "continue", "kind": kind})
    return await submit(
        flow,
        manager,
        {
            "action": "save",
            "name": "Synthetic provider",
            "enabled": False,
            "url": "https://model.example.invalid",
            **values,
        },
    )


@pytest.mark.parametrize("kind", ["text", "image"])
async def test_empty_chain_is_optional_and_preserves_other_options_without_network(
    chain, monkeypatch, kind
):
    flow, entry, _, _ = chain
    entry.options = {"unrelated": {"keep": True}}
    if kind == "text":
        from custom_components.family_assistant.assistant import provider_registry

        async def denied(*args):
            raise AssertionError("save must not inspect a provider")

        monkeypatch.setattr(provider_registry, "inspect_provider", denied)
    manager = await getattr(
        flow, "async_step_" + ("provider_chain" if kind == "text" else "image_generation")
    )()
    result = await submit(flow, manager, {"enabled": False, "action": "save"})
    assert result["type"] == "create_entry"
    config = result["data"]["conversation" if kind == "text" else "image_generation"]
    assert config["providers"] == [] and config["enabled"] is False
    assert result["data"]["unrelated"] == {"keep": True}
    assert entry.options == {"unrelated": {"keep": True}}


async def test_legacy_rows_are_derived_then_ordered_without_rewriting_legacy_slots(chain):
    flow, entry, _, _ = chain
    legacy = {
        "url": "https://legacy.example.invalid",
        "model": "legacy",
        "api_key": "synthetic-legacy-key",
    }
    entry.options = {
        "conversation": {"enabled": False, "primary": legacy, "search": {"enabled": False}}
    }
    manager = await flow.async_step_provider_chain()
    assert flow._provider_list_draft["rows"][0]["id"] == "primary"
    manager = await add(flow, manager, "agy", name="Gateway", model="gemini", search_enabled=True)
    gateway = flow._provider_list_draft["rows"][-1]["id"]
    manager = await submit(flow, manager, {"action": "move_up", "provider": gateway})
    manager = await add(
        flow, manager, "ollama", name="Other model", model="qwen-small", enabled=True
    )
    third = flow._provider_list_draft["rows"][-1]["id"]
    manager = await submit(flow, manager, {"action": "move_up", "provider": third})
    result = await submit(flow, manager, {"action": "save", "enabled": True})
    config = result["data"]["conversation"]
    assert [row["id"] for row in config["providers"]] == [gateway, third, "primary"]
    assert config["providers"][0]["search_enabled"] is True
    assert config["primary"] == legacy and config["search"] == {"enabled": False}
    assert entry.options["conversation"].get("providers") is None


@pytest.mark.parametrize("kind", ["text", "image"])
async def test_secret_endpoint_scope_clear_and_no_echo_even_after_invalid_edit(chain, kind):
    flow, entry, _, _ = chain
    key = "synthetic-provider-secret"
    row = (text_row if kind == "text" else image_row)(api_key=key)
    bucket = "conversation" if kind == "text" else "image_generation"
    entry.options = {bucket: {"enabled": False, "providers": [row]}}
    manager = await getattr(
        flow, "async_step_" + ("provider_chain" if kind == "text" else bucket)
    )()
    edit = await submit(flow, manager, {"action": "edit", "provider": row["id"]})
    assert key not in repr(edit)
    failed = await submit(flow, edit, {"action": "save", "url": "https://other.example.invalid"})
    assert failed["errors"] == {"base": "provider_key_scope"}
    assert key not in repr(failed)
    assert entry.options[bucket]["providers"][0]["api_key"] == key
    manager = await submit(flow, failed, {"action": "save", "clear_key": True, "enabled": False})
    result = await submit(flow, manager, {"action": "save"})
    saved = result["data"][bucket]["providers"][0]
    assert not saved.get("api_key") and saved["url"] == "https://other.example.invalid"


@pytest.mark.parametrize("kind", ["text", "image"])
async def test_remove_requires_consent_and_cancel_discards_changes(chain, kind):
    flow, entry, _, _ = chain
    row = (text_row if kind == "text" else image_row)()
    bucket = "conversation" if kind == "text" else "image_generation"
    entry.options = {bucket: {"enabled": False, "providers": [row]}}
    before = deepcopy(entry.options)
    manager = await getattr(
        flow, "async_step_" + ("provider_chain" if kind == "text" else bucket)
    )()
    review = await submit(flow, manager, {"action": "remove", "provider": row["id"]})
    denied = await submit(flow, review, {"action": "remove"})
    assert denied["errors"] == {"base": "invalid_field"}
    manager = await submit(flow, denied, {"action": "back"})
    assert len(flow._provider_list_draft["rows"]) == 1
    review = await submit(flow, manager, {"action": "remove", "provider": row["id"]})
    manager = await submit(flow, review, {"action": "remove", "confirmed": True})
    assert flow._provider_list_draft["rows"] == []
    result = await submit(flow, manager, {"action": "cancel"})
    assert result == {"type": "abort", "reason": "provider_chain_cancelled"}
    assert entry.options == before and flow._provider_list_draft is None


async def test_explicit_empty_saved_chain_does_not_reactivate_retained_legacy_provider(chain):
    flow, entry, _, _ = chain
    legacy = {"url": "https://legacy.example.invalid", "model": "old"}
    entry.options = {
        "conversation": {"enabled": True, "primary": legacy, "providers": [text_row()]}
    }
    manager = await flow.async_step_provider_chain()
    review = await submit(flow, manager, {"action": "remove", "provider": "first"})
    manager = await submit(flow, review, {"action": "remove", "confirmed": True})
    result = await submit(flow, manager, {"action": "save", "enabled": False})
    assert result["data"]["conversation"]["providers"] == []
    assert result["data"]["conversation"]["primary"] == legacy


@pytest.mark.parametrize(
    "bad", [None, {"available": False, "models": "unsafe"}, {"available": True, "models": None}]
)
async def test_malformed_metadata_is_a_sanitized_failed_probe_without_options_write(
    chain, monkeypatch, bad
):
    flow, entry, _, _ = chain
    from custom_components.family_assistant.assistant import provider_registry

    async def inspect(*args):
        return bad

    monkeypatch.setattr(provider_registry, "inspect_provider", inspect)
    entry.options = {"conversation": {"providers": [text_row()]}}
    before = deepcopy(entry.options)
    manager = await flow.async_step_provider_chain()
    result = await submit(flow, manager, {"action": "test", "provider": "first"})
    assert result["errors"] == {"base": "provider_bad_response"}
    assert result["description_placeholders"]["models"] == "—"
    assert entry.options == before


@pytest.mark.parametrize("kind", ["text", "image"])
async def test_model_discovery_is_explicit_retryable_and_does_not_generate_or_save(
    chain, monkeypatch, kind
):
    flow, entry, _, _ = chain
    calls = []

    async def inspect(*args):
        calls.append(True)
        if len(calls) == 1:
            raise DomainError("provider_unreachable")
        return {
            "available": True,
            "models": ["synthetic-model"],
            "encoders": ["synthetic-encoder"],
            "vaes": ["synthetic-vae"],
        }

    if kind == "text":
        from custom_components.family_assistant.assistant import provider_registry

        monkeypatch.setattr(provider_registry, "inspect_provider", inspect)
    else:
        from custom_components.family_assistant.assistant.image_providers import ImageProvider

        monkeypatch.setattr(ImageProvider, "inspect", inspect)
    row = (text_row if kind == "text" else image_row)(model="", enabled=False)
    bucket = "conversation" if kind == "text" else "image_generation"
    entry.options = {bucket: {"providers": [row]}}
    manager = await getattr(
        flow, "async_step_" + ("provider_chain" if kind == "text" else bucket)
    )()
    assert calls == []
    result = await submit(flow, manager, {"action": "test", "provider": row["id"]})
    assert result["errors"] == {"base": "provider_unreachable"}
    result = await submit(flow, result, {"action": "test"})
    assert (
        result["errors"] == {} and result["description_placeholders"]["models"] == "synthetic-model"
    )
    manager = await submit(flow, result, {"action": "back"})
    edit = await submit(flow, manager, {"action": "edit", "provider": row["id"]})
    field = next(
        value for key, value in edit["data_schema"].schema.items() if key.schema == "model"
    )
    assert field.config["options"] == ["synthetic-model"] and field.config["custom_value"] is True
    assert calls == [True, True] and entry.options[bucket]["providers"][0]["model"] == ""


@pytest.mark.parametrize("kind", ["text", "image"])
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("drift", ["options", "owner", "ha_user", "reload", "backup"])
async def test_probe_await_revokes_both_success_and_error_forms_after_scope_changes(
    chain, monkeypatch, now, kind, failed, drift
):
    flow, entry, runtime, user = chain

    async def inspect(*args):
        if drift == "options":
            entry.options = {"newer": True}
        elif drift == "owner":
            await runtime.engine.system_update(
                "changed-owner", now, lambda ctx: ctx.state["members"]["owner"].update(revision=2)
            )
        elif drift == "ha_user":
            user.is_active = False
        elif drift == "reload":
            replacement = SimpleNamespace(engine=runtime.engine)
            entry.runtime_data = replacement
            flow.hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
        else:
            flow.hass.data["family_assistant"]["backup"] = object()
        if failed:
            raise DomainError("provider_unreachable")
        return {"available": True, "models": ["must-not-leak-after-revocation"]}

    if kind == "text":
        from custom_components.family_assistant.assistant import provider_registry

        monkeypatch.setattr(provider_registry, "inspect_provider", inspect)
    else:
        from custom_components.family_assistant.assistant.image_providers import ImageProvider

        monkeypatch.setattr(ImageProvider, "inspect", inspect)
    row = (text_row if kind == "text" else image_row)()
    entry.options = {"conversation" if kind == "text" else "image_generation": {"providers": [row]}}
    manager = await getattr(
        flow, "async_step_" + ("provider_chain" if kind == "text" else "image_generation")
    )()
    result = await submit(flow, manager, {"action": "test", "provider": row["id"]})
    assert result["type"] == "abort" and result["reason"] in {
        "conflict",
        "forbidden",
        "backup_in_progress",
    }
    assert "data_schema" not in result and "description_placeholders" not in result


async def test_chain_draft_cannot_be_rebased_by_reopening_a_step_after_options_change(chain):
    flow, entry, _, _ = chain
    manager = await flow.async_step_provider_chain()
    manager = await add(flow, manager, model="synthetic-qwen")
    entry.options = {"newer": True}
    assert await flow.async_step_provider_chain() == {"type": "abort", "reason": "conflict"}
    assert entry.options == {"newer": True}


async def test_comfy_preset_and_generation_settings_are_drafts_and_never_start_an_image(chain):
    flow, entry, _, _ = chain
    manager = await flow.async_step_image_generation()
    manager = await add(
        flow,
        manager,
        "comfyui",
        model="diffusion",
        workflow="z_image_turbo",
        encoder="encoder",
        vae="vae",
        enabled=True,
    )
    settings = await submit(flow, manager, {"action": "settings"})
    with pytest.raises(vol.Invalid):
        settings["data_schema"]({"action": "save", "steps": True})
    with pytest.raises(vol.Invalid):
        settings["data_schema"]({"action": "save", "cfg": True})
    manager = await submit(
        flow,
        settings,
        {
            "action": "save",
            "width": 768,
            "height": 1024,
            "steps": 8,
            "cfg": 1,
            "negative_prompt": "synthetic-negative",
        },
    )
    result = await submit(flow, manager, {"action": "save", "enabled": True})
    config = result["data"]["image_generation"]
    assert config["providers"][0]["workflow"] == "z_image_turbo"
    assert config["providers"][0]["encoder"] == "encoder" and config["providers"][0]["vae"] == "vae"
    assert (config["width"], config["height"], config["steps"], config["cfg"]) == (768, 1024, 8, 1)
    assert entry.options == {}
