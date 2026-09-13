"""Real image service lifecycle with synthetic HA identity/config boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_assistant_provider_order import configured, ha_modules  # noqa: F401

from custom_components.family_assistant.assistant.image_jobs import ImageJobs, digest
from custom_components.family_assistant.domain.validation import DomainError


def image_config(**changes):
    return {
        "enabled": True,
        "providers": [
            {
                "id": "synthetic-image",
                "type": "agy_gateway",
                "url": "https://images.example.invalid",
                "model": "synthetic-image-model",
            }
        ],
        **changes,
    }


def setup(configure, tmp_path, config):
    env = configure("primary")
    env.hass.config = SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts)))
    env.family_entry.options["image_generation"] = config
    env.runtime_module.async_configure_images(env.hass, env.family_entry)
    return env


def test_constructs_actual_service_without_network_and_fences_replacements(configured, tmp_path):  # noqa: F811
    config = image_config()
    env = setup(configured, tmp_path, config)
    service = env.runtime.image_generation
    assert isinstance(service, ImageJobs)
    assert env.runtime.image_generation_digest == digest(config)
    assert len(service.providers) == 1
    assert service.files.root.is_relative_to(tmp_path)
    assert not service.files.root.exists()  # Construction did not create/download anything.
    service._guard()
    env.runtime_module.async_configure_images(env.hass, env.family_entry)
    assert env.runtime.image_generation is not service and service._closed
    with pytest.raises(DomainError, match="forbidden"):
        service.scope_check()
    env.runtime.image_generation._guard()
    latest = env.runtime.image_generation
    env.runtime_module.stop_images(env.runtime)
    assert latest._closed and env.runtime.image_generation is None
    with pytest.raises(DomainError, match="forbidden"):
        latest.scope_check()


@pytest.mark.parametrize("change", ["options", "runtime", "engine_closed"])
def test_provider_options_runtime_and_closed_writer_invalidate_image_scope(
    configured,  # noqa: F811
    tmp_path,
    change,
):
    env = setup(configured, tmp_path, image_config())
    service = env.runtime.image_generation
    if change == "options":
        env.family_entry.options["image_generation"] = image_config(enabled=False)
    elif change == "runtime":
        env.family_entry.runtime_data = SimpleNamespace()
    else:
        env.runtime.engine._closed = True
    with pytest.raises(DomainError):
        service.scope_check()


def test_disabled_image_service_can_cleanup_but_cannot_generate(configured, tmp_path):  # noqa: F811
    env = setup(configured, tmp_path, image_config(enabled=False))
    service = env.runtime.image_generation
    assert isinstance(service, ImageJobs)
    service.scope_check()
    with pytest.raises(DomainError, match="module_disabled"):
        service._guard()
    assert not service.files.root.exists()
    env.runtime.engine._state["settings"]["modules"].remove("conversation")
    env.family_entry.options["image_generation"]["enabled"] = True
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.runtime.image_generation is not service and service._closed
    with pytest.raises(DomainError, match="module_disabled"):
        env.runtime.image_generation._guard()


def test_malformed_optional_image_config_does_not_disable_text_or_deterministic_commands(
    configured,  # noqa: F811
    tmp_path,
):
    env = setup(configured, tmp_path, image_config(width="invalid"))
    assert env.runtime.image_generation is None
    assert env.runtime.health["images"] == "invalid_field"
    assert "image_generation" not in env.runtime.health
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.runtime.assistant is not None and env.runtime.chat is not None


@pytest.mark.parametrize("mode", ["valid", "invalid", "empty", "stop"])
def test_reconfigure_or_stop_clears_old_worker_and_legacy_image_health(
    configured,  # noqa: F811
    tmp_path,
    mode,
):
    env = setup(configured, tmp_path, image_config())
    old = env.runtime.image_generation
    env.runtime.health.update(
        images="image_unavailable", image_generation="media_unavailable", media="storage_error"
    )
    if mode == "stop":
        env.runtime_module.stop_images(env.runtime)
    else:
        env.family_entry.options["image_generation"] = {
            "valid": image_config(),
            "invalid": image_config(width="bad"),
            "empty": {},
        }[mode]
        env.runtime_module.async_configure_images(env.hass, env.family_entry)
    assert old._closed
    assert "image_generation" not in env.runtime.health
    assert env.runtime.health.get("images") == ("invalid_field" if mode == "invalid" else None)
    assert env.runtime.health["media"] == "storage_error"


@pytest.mark.parametrize("prior", [None, "media_unavailable", "image_unavailable", "storage_error"])
async def test_cleanup_success_only_clears_cleanup_error(configured, tmp_path, prior):  # noqa: F811
    env = setup(configured, tmp_path, image_config())
    env.runtime.image_generation.collect = AsyncMock(return_value=False)
    if prior:
        env.runtime.health["images"] = prior
    await env.runtime_module.async_collect_images(env.runtime)
    expected = None if prior == "media_unavailable" else prior
    assert env.runtime.health.get("images") == expected


@pytest.mark.parametrize("replace_service", [False, True])
async def test_cleanup_failure_is_current_service_scoped(
    configured,  # noqa: F811
    tmp_path,
    replace_service,
):
    env = setup(configured, tmp_path, image_config())

    async def failed():
        if replace_service:
            env.runtime_module.async_configure_images(env.hass, env.family_entry)
            env.runtime.health["images"] = "storage_error"
        raise OSError("SYNTHETIC_PRIVATE_ERROR")

    env.runtime.image_generation.collect = failed
    await env.runtime_module.async_collect_images(env.runtime)
    expected = "storage_error" if replace_service else "media_unavailable"
    assert env.runtime.health.get("images") == expected
    assert "image_generation" not in env.runtime.health
