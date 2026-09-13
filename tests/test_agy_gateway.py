"""Gateway contracts using actual nested CLI events and real HTTP adapter calls."""

import asyncio
import hashlib
import io
import json
import os
import socket
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from services.agy_gateway.auth import verify_bearer_token
from services.agy_gateway.chat import extract_stream_json_content
from services.agy_gateway.config import GatewayConfig
from services.agy_gateway.hooks import decision
from services.agy_gateway.images import (
    JOB_MANAGER_KEY,
    ImageJobManager,
    StorageUnavailable,
    detect_image_mime,
    validate_uuid,
    verify_image_file,
)
from services.agy_gateway.process import (
    OutputLimitExceededError,
    ProcessExecutionError,
    run_agy_command,
    setup_job_runtime_directory,
)
from services.agy_gateway.search import extract_verified_search_results, is_public_url
from services.agy_gateway.server import create_app

TEST_API_KEY = "synthetic-secret-token-12345"
HEADERS = {"Authorization": "Bearer " + TEST_API_KEY}
MODEL = "synthetic-gateway-model"


def identifier(number=1):
    return str(UUID(int=number))


def terminal(response="", *, status="SUCCESS", error=None):
    return (
        json.dumps(
            {"event": "result", "result": {"status": status, "response": response, "error": error}}
        )
        + "\n"
    )


def tool(name="generate_image", *, output=None, error=None, state="DONE"):
    info = {"name": name, "parameters": {"ImageName": "family_result"}}
    if output is not None:
        info["output"] = output
    if error is not None:
        info["error"] = error
    return (
        json.dumps(
            {
                "event": "step_update",
                "step_update": {
                    "state": state,
                    "step_type": "tool",
                    "tool_name": name,
                    "tool_info": info,
                },
            }
        )
        + "\n"
    )


def png(color="blue"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(stream, format="PNG")
    return stream.getvalue()


def payload(number=1, **changes):
    return {
        "request_id": identifier(number),
        "prompt": "Synthetic flowers",
        "model": MODEL,
        "width": 512,
        "height": 512,
        **changes,
    }


@pytest.fixture
def gateway_config(tmp_path):
    return GatewayConfig(api_key=TEST_API_KEY, models=(MODEL,), data_dir=tmp_path, host="127.0.0.1")


@pytest.fixture
async def app_client(gateway_config):
    async with TestClient(TestServer(create_app(gateway_config))) as client:
        yield client


async def completed(client):
    await asyncio.wait_for(client.app[JOB_MANAGER_KEY].queue.join(), 3)


async def generated(_args, *, cwd, **_kwargs):
    # The observed tool DONE contains parameters but no output path. Only the
    # post-tool hook's fixed output file can provide artifact bytes.
    (cwd / "image.png").write_bytes(png())
    return tool() + terminal("Image generated")


def test_gateway_config_env_and_private_repr():
    with patch.dict(
        os.environ,
        {
            "AGY_API_KEY": "env-key",
            "AGY_MODELS": "model-a, model-b",
            "PORT": "9090",
            "AGY_BIN": "custom-agy",
        },
    ):
        config = GatewayConfig.from_env()
        config.validate()
        assert config.api_key == "env-key" and config.models == ("model-a", "model-b")
        assert config.port == 9090 and config.agy_bin == "custom-agy"
        assert "env-key" not in repr(config)


@pytest.mark.parametrize("key", ["", "   ", "synthetic\nkey", "x" * 2049])
def test_factory_cannot_start_without_valid_bearer_secret(gateway_config, key):
    with pytest.raises(ValueError, match="gateway_api_key_required"):
        create_app(replace(gateway_config, api_key=key))


def test_auth_constant_time():
    assert verify_bearer_token("Bearer " + TEST_API_KEY, TEST_API_KEY)
    for supplied in (None, "", "Basic abc", "Bearer wrong"):
        assert not verify_bearer_token(supplied, TEST_API_KEY)


async def test_health_auth_models_and_body_bounds(app_client):
    assert await (await app_client.get("/health")).json() == {"status": "ok"}
    assert (await app_client.get("/api/tags")).status == 401
    assert (
        await app_client.get("/api/tags", headers={"Authorization": "Bearer wrong"})
    ).status == 401
    assert await (await app_client.get("/api/tags", headers=HEADERS)).json() == {
        "models": [{"name": MODEL}]
    }
    assert await (await app_client.get("/v1/images/models", headers=HEADERS)).json() == {
        "models": [MODEL]
    }
    for path in ("/api/chat", "/v1/search", "/v1/images"):
        response = await app_client.post(path, headers=HEADERS, data=b"x" * 262145)
        assert response.status == 413 and await response.json() == {"error": "body_too_large"}


def test_runtime_profiles_and_actual_terminal_event(tmp_path):
    setup_job_runtime_directory(tmp_path)
    assert {path.stem for path in (tmp_path / ".agents" / "agents").glob("*.md")} >= {
        "family-text",
        "family-search",
        "family-image",
    }
    assert json.loads(extract_stream_json_content(terminal('{"answer":42}'))) == {"answer": 42}
    assert extract_stream_json_content('{"message":{"content":"invented envelope"}}') == ""
    assert extract_stream_json_content(terminal("not successful", status="ERROR")) == ""


@pytest.mark.parametrize("over_limit", [False, True])
async def test_real_process_contract_uses_print_and_preserves_output_bound(tmp_path, over_limit):
    process = MagicMock(returncode=0)
    process.stdout, process.stderr = asyncio.StreamReader(), asyncio.StreamReader()
    process.stdout.feed_data(b"x" * 2000 if over_limit else terminal("hello").encode())
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    process.wait = AsyncMock(return_value=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as launch:
        args = ["agy", "--agent", "family-text", "--non-interactive"]
        if over_limit:
            with pytest.raises(OutputLimitExceededError):
                await run_agy_command(
                    args, stdin_text="Synthetic prompt", cwd=tmp_path, max_output_bytes=1024
                )
        else:
            assert "hello" in await run_agy_command(
                args, stdin_text="Synthetic prompt", cwd=tmp_path
            )
        sent, options = launch.call_args
        assert "--print" in sent and "--new-project" in sent and "--non-interactive" not in sent
        assert "Synthetic prompt" == sent[-1] and not options.get("shell")
        assert options["env"]["AGY_GATEWAY_MODE"] == "chat"
        assert "AGY_API_KEY" not in options["env"]


async def test_chat_and_ha_provider_interoperate_using_actual_events(app_client):
    from custom_components.family_assistant.assistant.provider import AGY

    async with ClientSession() as session:
        provider = AGY(
            session,
            {
                "url": str(app_client.make_url("")),
                "model": MODEL,
                "allow_http": True,
                "api_key": TEST_API_KEY,
            },
        )
        await provider.inspect()
        with patch(
            "services.agy_gateway.chat.run_agy_command",
            AsyncMock(return_value=terminal('{"kind":"answer","text":"Synthetic"}')),
        ):
            assert await provider.generate(
                [{"role": "user", "content": "Hello"}], {"type": "object"}
            ) == {"kind": "answer", "text": "Synthetic"}
        response = await app_client.post(
            "/api/chat",
            headers=HEADERS,
            json={"model": "unknown", "messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status == 400


@pytest.mark.parametrize(
    "reply,status",
    [
        ({"text": "Hello"}, 200),
        ({"text": "Too long"}, 502),
        ({"text": "Hello", "extra": True}, 502),
        ({"other": "Hello"}, 502),
    ],
)
async def test_gateway_preserves_and_independently_enforces_full_schema(app_client, reply, status):
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string", "maxLength": 5}},
        "required": ["text"],
        "additionalProperties": False,
    }
    with patch(
        "services.agy_gateway.chat.run_agy_command",
        AsyncMock(return_value=terminal(json.dumps(reply))),
    ) as process:
        response = await app_client.post(
            "/api/chat",
            headers=HEADERS,
            json={"messages": [{"role": "user", "content": "Hello"}], "format": schema},
        )
        assert response.status == status
        assert json.dumps(schema) in process.call_args.kwargs["stdin_text"]
        assert "--json-schema" not in process.call_args.args[0]


@pytest.mark.parametrize("key", ["$ref", "$dynamicRef", "$recursiveRef"])
async def test_remote_schema_references_are_rejected_before_any_process(app_client, key):
    with patch("services.agy_gateway.chat.run_agy_command", AsyncMock()) as process:
        response = await app_client.post(
            "/api/chat",
            headers=HEADERS,
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "format": {key: "https://schema.example.org/object"},
            },
        )
        assert response.status == 400
        process.assert_not_called()


def test_search_provenance_and_private_url_filter():
    items = [
        {"url": "https://public.example.org/article", "title": "Public", "snippet": "Evidence"}
    ]
    assert (
        extract_verified_search_results(
            tool("search_web", output=items) + terminal("https://invented.example.org"), 5
        )
        == items
    )
    assert (
        extract_verified_search_results(
            '{"tool":"search_web","output":' + json.dumps(items) + "}", 5
        )
        == []
    )
    assert is_public_url("https://public.example.org/article")
    private = "http://" + ".".join(str(part) for part in (192, 168, 1, 1))
    for value in (
        private,
        "http://localhost",
        "http://127.0.0.1",
        "https://server.lan",
        "file:///etc/passwd",
    ):
        assert not is_public_url(value)


async def test_search_and_ha_adapter_interoperate_without_live_dns(app_client):
    from custom_components.family_assistant.assistant.agy_search import AGYSearch

    async def resolve(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    item = {"url": "https://public.example.org/article", "title": "Public", "snippet": "Evidence"}
    async with ClientSession() as session:
        adapter = AGYSearch(
            session,
            {
                "url": str(app_client.make_url("")),
                "model": MODEL,
                "allow_http": True,
                "api_key": TEST_API_KEY,
            },
            resolve=resolve,
        )
        with patch(
            "services.agy_gateway.search.run_agy_command",
            AsyncMock(return_value=tool("search_web", output=[item]) + terminal()),
        ):
            assert await adapter.query("Public news", "en") == [item]
    for extra in ({"child": True}, {"safesearch": 2}):
        response = await app_client.post(
            "/v1/search", headers=HEADERS, json={"query": "News", **extra}
        )
        assert response.status == 501


def test_image_decode_and_confined_path(tmp_path):
    directory = tmp_path / "job"
    directory.mkdir()
    data = png()
    assert detect_image_mime(data) == "image/png"
    assert detect_image_mime(b"\x89PNG\r\n\x1a\nnot an image") is None
    image = directory / "image.png"
    image.write_bytes(data)
    assert verify_image_file(image, directory) == (data, "image/png")
    outside = tmp_path / "outside.png"
    outside.write_bytes(data)
    assert verify_image_file(outside, directory) is None


def test_image_symlink_is_not_read(tmp_path):
    directory = tmp_path / "job"
    directory.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(png())
    link = directory / "linked.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("OS does not grant synthetic symlink creation")
    assert verify_image_file(link, directory) is None


@pytest.mark.parametrize("mode", ["chat", "search", "image"])
@pytest.mark.parametrize(
    "name",
    [
        "run_command",
        "write_to_file",
        "view_file",
        "mcp_call",
        "spawn_subagent",
        "schedule_task",
        "browser_subagent",
        "send_message",
    ],
)
def test_hook_denies_external_tools_in_every_profile(mode, name):
    assert not decision({"toolCall": {"name": name, "args": {}}}, mode)


@pytest.mark.parametrize("mode", ["chat", "search", "image"])
def test_hook_allows_bounded_native_finish_only(mode):
    assert decision({"toolCall": {"name": "finish", "args": {"result": "Synthetic"}}}, mode)
    assert not decision({"toolCall": {"name": "finish", "args": {"result": "x" * 200001}}}, mode)


def test_hook_exact_search_query_and_new_image_constraints():
    query = "Synthetic astronomy"
    digest = hashlib.sha256(query.encode()).hexdigest()
    call = {"toolCall": {"name": "search_web", "args": {"query": query}}}
    assert decision(call, "search", digest)
    assert not decision(call, "image", digest)
    assert not decision(call, "search", "wrong")
    assert not decision(
        {"toolCall": {"name": "search_web", "args": {"query": query, "domain": "private.invalid"}}},
        "search",
        digest,
    )
    image = {
        "toolCall": {
            "name": "generate_image",
            "args": {"Prompt": "Synthetic flowers", "ImageName": "family_result"},
        }
    }
    assert decision(image, "image")
    assert not decision(image, "chat")
    image["toolCall"]["args"]["ImagePaths"] = ["private-input.png"]
    assert not decision(image, "image")
    image["toolCall"]["args"].pop("ImagePaths")
    image["toolCall"]["args"]["ImageName"] = "../other"
    assert not decision(image, "image")


async def test_image_request_id_idempotency_and_real_client_success(app_client):
    from custom_components.family_assistant.assistant.image_providers import ImageProvider

    with patch("services.agy_gateway.images.run_agy_command", side_effect=generated) as generate:
        response = await app_client.post("/v1/images", headers=HEADERS, json=payload())
        first = await response.json()
        assert response.status == 200 and first["job_id"] == identifier()
        assert first["status"] in {"queued", "running", "succeeded"}
        repeated = await app_client.post("/v1/images", headers=HEADERS, json=payload())
        assert (await repeated.json())["job_id"] == identifier()
        conflict = await app_client.post(
            "/v1/images", headers=HEADERS, json=payload(prompt="Changed")
        )
        assert conflict.status == 409
        # Equal prompts from different actors' request IDs remain separate jobs.
        other = await app_client.post("/v1/images", headers=HEADERS, json=payload(2))
        assert (await other.json())["job_id"] == identifier(2)
        await completed(app_client)
        assert generate.call_count == 2
        async with ClientSession() as session:
            provider = ImageProvider(
                session,
                {
                    "id": "gateway",
                    "type": "agy_gateway",
                    "url": str(app_client.make_url("")),
                    "allow_http": True,
                    "api_key": TEST_API_KEY,
                    "model": MODEL,
                },
            )
            assert (await provider.inspect())["models"] == [MODEL]
            assert (
                await provider.submit(
                    "Synthetic flowers", identifier(), {"width": 512, "height": 512}
                )
                == identifier()
            )
            assert await provider.poll(identifier()) == {}
            assert await provider.content(identifier(), None) == (png(), "image/png")
        assert generate.call_count == 2
        job = app_client.app[JOB_MANAGER_KEY].load_job(identifier())
        assert job["prompt"] == "" and job["image_file"] == "image.png"


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(),
        OutputLimitExceededError("private stderr"),
        ProcessExecutionError("private stderr", 1),
        RuntimeError("private stderr"),
    ],
)
async def test_uncertain_execution_never_allows_client_fallback(app_client, failure):
    from custom_components.family_assistant.assistant.image_providers import (
        ImageError,
        ImageProvider,
    )

    with patch(
        "services.agy_gateway.images.run_agy_command", AsyncMock(side_effect=failure)
    ) as generate:
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
        response = await app_client.get("/v1/images/" + identifier(), headers=HEADERS)
        assert await response.json() == {
            "job_id": identifier(),
            "status": "uncertain",
            "error": {"code": "execution_uncertain"},
        }
        async with ClientSession() as session:
            provider = ImageProvider(
                session,
                {
                    "id": "gateway",
                    "type": "agy_gateway",
                    "url": str(app_client.make_url("")),
                    "allow_http": True,
                    "api_key": TEST_API_KEY,
                    "model": MODEL,
                },
            )
            with pytest.raises(ImageError) as caught:
                await provider.poll(identifier())
            assert caught.value.uncertain and not caught.value.fallback
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        assert generate.call_count == 1


@pytest.mark.parametrize(
    "stdout,status,code",
    [
        (terminal("I drew a picture"), "failed", "no_output"),
        (terminal(status="ERROR", error="RESOURCE_EXHAUSTED"), "failed", "quota_exceeded"),
        (
            tool(error={"code": "RESOURCE_EXHAUSTED"}, state="ERROR") + terminal(status="ERROR"),
            "failed",
            "quota_exceeded",
        ),
        (
            tool()
            + tool(error={"code": "RESOURCE_EXHAUSTED"}, state="ERROR")
            + terminal(status="ERROR"),
            "uncertain",
            "execution_uncertain",
        ),
        (
            tool(error={"code": "RESOURCE_EXHAUSTED"}) + terminal(status="ERROR"),
            "uncertain",
            "execution_uncertain",
        ),
        (tool() + terminal(), "uncertain", "execution_uncertain"),
        ('{"tool":"generate_image","output":"other.png"}', "uncertain", "execution_uncertain"),
    ],
)
async def test_only_confirmed_no_output_or_quota_is_failed(app_client, stdout, status, code):
    with patch("services.agy_gateway.images.run_agy_command", AsyncMock(return_value=stdout)):
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
    response = await app_client.get("/v1/images/" + identifier(), headers=HEADERS)
    assert await response.json() == {
        "job_id": identifier(),
        "status": status,
        "error": {"code": code},
    }


async def test_model_paths_and_unrecorded_artifacts_never_count_as_images(app_client):
    async def fake(_args, *, cwd, **_kwargs):
        (cwd / "other.png").write_bytes(png())
        return tool(output={"file": "other.png"}) + terminal()

    with patch("services.agy_gateway.images.run_agy_command", side_effect=fake):
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
    assert app_client.app[JOB_MANAGER_KEY].load_job(identifier())["status"] == "uncertain"


async def test_restart_recovers_queued_running_as_uncertain_and_preserves_hash(gateway_config):
    manager = ImageJobManager(gateway_config)
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    await manager.submit_job(identifier(2), "Synthetic flowers", MODEL, 512, 512)
    job = manager.load_job(identifier(2))
    job["status"] = "running"
    manager.save_job_atomic(job)
    restarted = ImageJobManager(gateway_config)
    restarted.recover_on_startup()
    assert restarted.queue.empty()
    for number in (1, 2):
        record = restarted.load_job(identifier(number))
        assert record["status"] == "uncertain" and record["prompt"] == ""
        assert await restarted.submit_job(
            identifier(number), "Synthetic flowers", MODEL, 512, 512
        ) == (identifier(number), False)
    with pytest.raises(web.HTTPConflict):
        await restarted.submit_job(identifier(), "Changed", MODEL, 512, 512)


@pytest.mark.parametrize("corrupt", [b"not-json", b"{}", b'{"job_id":"unexpected"}', b"x" * 17000])
async def test_corrupt_record_fails_closed_without_reexecution(gateway_config, corrupt):
    manager = ImageJobManager(gateway_config)
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    manager._job_file_path(identifier()).write_bytes(corrupt)
    with pytest.raises(StorageUnavailable):
        await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    with pytest.raises(StorageUnavailable):
        ImageJobManager(gateway_config).recover_on_startup()
    assert manager.queue.qsize() == 1


async def test_atomic_save_failure_and_bounded_tombstone_capacity(gateway_config):
    manager = ImageJobManager(replace(gateway_config, max_jobs=2))
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    await manager.submit_job(identifier(2), "Another", MODEL, 512, 512)
    with pytest.raises(web.HTTPTooManyRequests):
        await manager.submit_job(identifier(3), "Third", MODEL, 512, 512)
    assert await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512) == (
        identifier(),
        False,
    )
    fresh = ImageJobManager(replace(gateway_config, data_dir=gateway_config.data_dir / "failure"))
    with patch("services.agy_gateway.images.os.replace", side_effect=OSError("PRIVATE_ERROR")):
        with pytest.raises(StorageUnavailable):
            await fresh.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    assert fresh.queue.empty()
    with pytest.raises(StorageUnavailable):
        ImageJobManager(fresh.config).recover_on_startup()


async def test_24h_cleanup_erases_private_files_but_not_idempotency(gateway_config):
    now = [datetime(2026, 9, 13, tzinfo=UTC)]
    manager = ImageJobManager(gateway_config, clock=lambda: now[0])
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    with patch("services.agy_gateway.images.run_agy_command", side_effect=generated):
        await manager._process_job(manager.queue.get_nowait())
    directory = manager.runs_dir / identifier()
    assert (directory / "image.png").exists()
    now[0] += timedelta(hours=25)
    await manager.collect()
    assert not directory.exists()
    job = manager.load_job(identifier())
    assert job["prompt"] == "" and job["image_file"] is None
    assert job["status"] == "uncertain" and job["error"]["code"] == "expired"
    assert await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512) == (
        identifier(),
        False,
    )
    assert manager.queue.empty()


async def test_cancellation_is_durable_uncertain(gateway_config):
    manager = ImageJobManager(gateway_config)
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)
    entered = asyncio.Event()

    async def hanging(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    with patch("services.agy_gateway.images.run_agy_command", side_effect=hanging):
        pending = asyncio.create_task(manager._process_job(manager.queue.get_nowait()))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert manager.load_job(identifier())["status"] == "uncertain"


@pytest.mark.parametrize(
    "change",
    [
        {"width": True},
        {"height": 512.0},
        {"prompt": ""},
        {"model": []},
        {"request_id": "../escape"},
        {"extra": "not allowed"},
    ],
)
async def test_image_api_rejects_invalid_fields_before_queueing(app_client, change):
    assert (
        await app_client.post("/v1/images", headers=HEADERS, json=payload(**change))
    ).status == 400
    assert app_client.app[JOB_MANAGER_KEY].queue.empty()


def test_uuid_requires_canonical_exact_case():
    assert validate_uuid(identifier()) == identifier()
    with pytest.raises(ValueError):
        validate_uuid("not-an-id")


async def test_confirmed_tool_quota_allows_actual_client_fallback(app_client):
    from custom_components.family_assistant.assistant.image_providers import (
        ImageError,
        ImageProvider,
    )

    response = tool(error={"code": "RESOURCE_EXHAUSTED"}, state="ERROR") + terminal(status="ERROR")
    with patch("services.agy_gateway.images.run_agy_command", AsyncMock(return_value=response)):
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
    async with ClientSession() as session:
        provider = ImageProvider(
            session,
            {
                "id": "gateway",
                "type": "agy_gateway",
                "url": str(app_client.make_url("")),
                "allow_http": True,
                "api_key": TEST_API_KEY,
                "model": MODEL,
            },
        )
        with pytest.raises(ImageError) as caught:
            await provider.poll(identifier())
        assert caught.value.code == "provider_quota_exceeded"
        assert caught.value.fallback and not caught.value.uncertain


@pytest.mark.parametrize(
    "stdout,artifact,fallback",
    [
        (terminal(status="ERROR", error="RESOURCE_EXHAUSTED"), False, True),
        (tool(state="ERROR", error={"code": "RESOURCE_EXHAUSTED"}), False, True),
        (terminal(status="ERROR", error="RESOURCE_EXHAUSTED"), True, False),
        (tool(state="ERROR", error={"code": "RESOURCE_EXHAUSTED"}), True, False),
        (tool() + tool(state="ERROR", error={"code": "RESOURCE_EXHAUSTED"}), False, False),
        (tool(state="ACTIVE") + terminal(status="ERROR", error="quota"), False, False),
        (terminal(status="ERROR", error="unknown failure"), False, False),
    ],
)
async def test_nonzero_process_quota_proof_and_artifact_guard_interoperate(
    app_client, stdout, artifact, fallback
):
    from custom_components.family_assistant.assistant.image_providers import (
        ImageError,
        ImageProvider,
    )

    async def launch(*_args, **options):
        if artifact:
            (Path(options["cwd"]) / "image.png").write_bytes(png())
        process = MagicMock(returncode=1)
        process.stdout, process.stderr = asyncio.StreamReader(), asyncio.StreamReader()
        process.stdout.feed_data(stdout.encode())
        process.stdout.feed_eof()
        process.stderr.feed_data(b"PRIVATE_STDERR_CANARY")
        process.stderr.feed_eof()
        process.wait = AsyncMock(return_value=1)
        return process

    with patch("asyncio.create_subprocess_exec", side_effect=launch) as process:
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
        result = await app_client.get("/v1/images/" + identifier(), headers=HEADERS)
        assert await result.json() == {
            "job_id": identifier(),
            "status": "failed" if fallback else "uncertain",
            "error": {"code": "quota_exceeded" if fallback else "execution_uncertain"},
        }
        async with ClientSession() as session:
            provider = ImageProvider(
                session,
                {
                    "id": "gateway",
                    "type": "agy_gateway",
                    "model": MODEL,
                    "url": str(app_client.make_url("")),
                    "allow_http": True,
                    "api_key": TEST_API_KEY,
                },
            )
            with pytest.raises(ImageError) as caught:
                await provider.poll(identifier())
            assert caught.value.fallback is fallback
            assert caught.value.uncertain is not fallback
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        assert process.call_count == 1


async def test_http_corrupt_record_cannot_be_requeued_or_disclosed(app_client):
    with patch(
        "services.agy_gateway.images.run_agy_command", AsyncMock(return_value=terminal())
    ) as process:
        await app_client.post("/v1/images", headers=HEADERS, json=payload())
        await completed(app_client)
        manager = app_client.app[JOB_MANAGER_KEY]
        manager._job_file_path(identifier()).write_bytes(b"PRIVATE_CORRUPT_CANARY")
        response = await app_client.post("/v1/images", headers=HEADERS, json=payload())
        assert response.status == 503
        assert await response.json() == {"error": "storage_unavailable"}
        assert process.call_count == 1


async def test_uncertain_artifact_reserves_bounded_disk_until_cleanup(gateway_config):
    now = [datetime(2026, 9, 13, tzinfo=UTC)]
    manager = ImageJobManager(replace(gateway_config, max_retained_jobs=1), clock=lambda: now[0])
    await manager.submit_job(identifier(), "Synthetic flowers", MODEL, 512, 512)

    async def lost_terminal(_args, *, cwd, **_kwargs):
        (cwd / "image.png").write_bytes(png())
        return tool()

    with patch("services.agy_gateway.images.run_agy_command", side_effect=lost_terminal):
        await manager._process_job(manager.queue.get_nowait())
    assert manager.load_job(identifier())["status"] == "uncertain"
    with pytest.raises(web.HTTPTooManyRequests):
        await manager.submit_job(identifier(2), "Another", MODEL, 512, 512)
    now[0] += timedelta(hours=25)
    await manager.collect()
    assert not (manager.runs_dir / identifier()).exists()
    assert await manager.submit_job(identifier(2), "Another", MODEL, 512, 512) == (
        identifier(2),
        True,
    )
