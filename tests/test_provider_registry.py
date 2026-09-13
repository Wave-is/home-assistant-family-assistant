"""Owner-configured ordering, static validation and legacy compatibility."""

from copy import deepcopy

import pytest
from test_assistant_provider_order import configured, ha_modules, names  # noqa: F401

from custom_components.family_assistant.assistant.provider import AGY, Ollama
from custom_components.family_assistant.assistant.provider_registry import (
    http_provider,
    inspect_provider,
    normalize_provider,
    normalize_providers,
    provider_rows,
)
from custom_components.family_assistant.domain.validation import DomainError
from tests.test_assistant import Response, Session


def row(identifier="first", **changes):
    return {
        "id": identifier,
        "kind": "ollama",
        "url": f"https://{identifier}.example.invalid",
        "model": "synthetic-model",
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Upper"},
        {"id": "x" * 41},
        {"kind": "shell"},
        {"enabled": 1},
        {"allow_http": "false"},
        {"timeout": True},
        {"timeout": 4},
        {"timeout": 61},
        {"name": "x" * 81},
        {"model": ""},
        {"api_key": "CANARY\r\nInjected: header"},
        {"api_key": 123},
        {"api_key": "x" * 2049},
        {"url": "https://user:CANARY@example.invalid"},
        {"url": "http://example.invalid"},
        {"search_enabled": True},
        {"tools": ["home_assistant"]},
    ],
)
def test_rows_reject_invalid_or_tool_fields_without_echo(change):
    with pytest.raises(DomainError) as caught:
        normalize_provider(row(**change))
    assert "CANARY" not in str(caught.value)


@pytest.mark.parametrize("rows", [None, {}, [row()] * 2, [row(str(i)) for i in range(9)]])
def test_invalid_registry_shape_and_duplicate_ids(rows):
    with pytest.raises(DomainError):
        normalize_providers(rows)


def test_valid_canonical_rows_are_independent_and_static_even_disabled():
    source = row(kind="agy", name="Private gateway", enabled=False, search_enabled=True, timeout=60)
    before = deepcopy(source)
    result = normalize_provider(source)
    assert source == before
    assert result == {**source, "allow_http": False}
    assert normalize_provider(row(timeout=5))["timeout"] == 5
    assert (
        normalize_provider(row(url="http://localhost:11434/", allow_http=True))["url"]
        == "http://localhost:11434"
    )
    with pytest.raises(DomainError):
        normalize_provider(row(enabled=False, url="invalid"))


def test_ha_ref_has_one_reviewed_config_and_no_http_or_unreviewed_scope_fields():
    native = {"id": "native", "kind": "ha_agent", "enabled": True}
    assert normalize_provider(native) == {**native, "name": "native"}
    for change in ({"url": "https://example.invalid"}, {"entity_id": "conversation.other"}):
        with pytest.raises(DomainError):
            normalize_provider({**native, **change})
    with pytest.raises(DomainError):
        normalize_providers([native, {**native, "id": "another"}])


def test_explicit_empty_list_never_revives_legacy_config_and_legacy_read_never_writes():
    config = {
        "agy": {"url": "https://agy.example.invalid", "model": "agy"},
        "ha_agent": {"type": "ha_agent", "entity_id": "conversation.reviewed", "timeout": 15},
        "primary": {"url": "https://qwen.example.invalid", "model": "qwen"},
        "fallback": {"url": "https://backup.example.invalid", "model": "qwen", "enabled": False},
    }
    before = deepcopy(config)
    rows = provider_rows(config)
    assert [r["kind"] for r in rows] == ["agy", "ha_agent", "ollama", "ollama"]
    assert rows[-1]["enabled"] is False and config == before
    assert provider_rows({**config, "providers": []}) == []


@pytest.mark.asyncio
async def test_agy_kind_uses_observed_ollama_contract_and_explicit_credentials():
    session = Session(
        Response(200, {"models": [{"name": "synthetic-model"}]}),
        Response(200, {"message": {"content": '{"kind":"answer","text":"synthetic"}'}}),
    )
    config = normalize_provider(row(kind="agy", api_key="SYNTHETIC_KEY", timeout=30))
    client = http_provider(session, config)
    assert type(client) is AGY and isinstance(client, Ollama)
    await client.inspect()
    schema = {"type": "object", "properties": {"text": {"type": "string", "maxLength": 5000}}}
    assert await client.generate([], schema) == {"kind": "answer", "text": "synthetic"}
    assert [call[:2] for call in session.calls] == [
        ("GET", "https://first.example.invalid/api/tags"),
        ("POST", "https://first.example.invalid/api/chat"),
    ]
    for _, _, options in session.calls:
        assert options["headers"] == {"Authorization": "Bearer SYNTHETIC_KEY"}
        assert options["allow_redirects"] is False and options["timeout"].total == 30
    assert "tools" not in session.calls[-1][2]["json"]
    assert session.calls[-1][2]["json"]["format"] == schema


@pytest.mark.asyncio
async def test_metadata_discovery_requires_no_placeholder_and_disabled_draft_has_no_model():
    draft = row(model="", enabled=False)
    assert normalize_provider(draft)["model"] == ""
    with pytest.raises(DomainError, match="invalid_field"):
        normalize_provider({**draft, "enabled": True})
    session = Session(Response(200, {"models": [{"name": "available-model"}]}))
    assert await inspect_provider(session, {**draft, "enabled": True}) == {
        "available": True,
        "models": ["available-model"],
    }
    assert len(session.calls) == 1 and session.calls[0][0] == "GET"
    session = Session(Response(200, {"models": [{"name": "available-model"}]}))
    with pytest.raises(DomainError, match="provider_model_missing"):
        await inspect_provider(session, row(model="missing"))


@pytest.mark.parametrize(
    "rows,expected",
    [
        (
            [row("backup"), row("agy", kind="agy"), row("disabled", enabled=False)],
            ["synthetic-model"] * 2,
        ),
        ([], []),
        ([{"id": "native", "kind": "ha_agent"}], ["ha_agent"]),
    ],
)
def test_runtime_uses_exact_explicit_order_and_keeps_old_native_scope(configured, rows, expected):  # noqa: F811
    env = configured("agy", "ha_agent", "primary")
    previous = env.runtime.assistant
    env.family_entry.options["conversation"]["providers"] = rows
    before = deepcopy(env.family_entry.options)
    old_sessions = len(env.session_requests)
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.family_entry.options == before and env.runtime.assistant is not previous
    if expected:
        cascade = env.runtime.assistant.cascade
        assert names(cascade) == expected and cascade.budget == 90
        if len(rows) == 3:
            assert [p.kind for p in cascade.providers] == ["ollama", "agy"]
    else:
        assert env.runtime.assistant is None and env.runtime.chat is not None
    if not rows or rows[0]["kind"] == "ha_agent":
        assert len(env.session_requests) == old_sessions


def test_invalid_optional_list_fails_closed_but_deterministic_chat_survives(configured):  # noqa: F811
    env = configured("primary")
    env.family_entry.options["conversation"]["providers"] = [row(api_key="CANARY\nsecret")]
    sessions = len(env.session_requests)
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.runtime.assistant is None and env.runtime.chat is not None
    assert len(env.session_requests) == sessions
    assert env.runtime.health["conversation"] == "invalid_field"


def test_search_requires_explicit_agy_opt_in(configured):  # noqa: F811
    env = configured("primary")
    env.family_entry.options["conversation"]["providers"] = [row("agy", kind="agy")]
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.runtime.assistant.search is None
    env.family_entry.options["conversation"]["providers"][0]["search_enabled"] = True
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert len(env.runtime.assistant.search.sources) == 1


@pytest.mark.parametrize(
    "search",
    [
        [],
        {"enabled": "false"},
        {"enabled": True},
        {"enabled": True, "url": "https://search.example.invalid", "api_key": "CANARY\nsecret"},
    ],
)
def test_malformed_search_cannot_crash_or_create_transport(configured, search):  # noqa: F811
    env = configured("primary")
    env.family_entry.options["conversation"]["search"] = search
    sessions = len(env.session_requests)
    env.runtime_module.async_configure_assistant(env.hass, env.family_entry)
    assert env.runtime.assistant is None and env.runtime.chat is not None
    assert env.runtime.health["conversation"] in {"invalid_field", "provider_invalid_url"}
    assert len(env.session_requests) == sessions
