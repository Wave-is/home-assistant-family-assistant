"""Synthetic HTTP, actual Engine, private files and real Pillow image verification."""

import asyncio
import io
import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from PIL import Image

from custom_components.family_assistant.assistant.image_files import ImageFiles
from custom_components.family_assistant.assistant.image_jobs import ImageJobs, project
from custom_components.family_assistant.assistant.image_providers import (
    ImageProvider,
    normalize_config,
    normalize_provider,
)
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_validation import MediaValidationError, verify
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram.image_generation import prompt
from tests.test_assistant import enable

REMOTE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def png(size=(7, 5)):
    output = io.BytesIO()
    Image.new("RGB", size, (20, 40, 80)).save(output, format="PNG")
    return output.getvalue()


async def decode(path):
    try:
        return await asyncio.to_thread(verify, path)
    except MediaValidationError as error:
        raise DomainError(error.code) from None


class Response:
    def __init__(self, status, body, mime="application/json"):
        self.status, self.body = (
            status,
            body if isinstance(body, bytes) else json.dumps(body).encode(),
        )
        self.headers, self.content = {"Content-Type": mime}, self

    async def iter_chunked(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start : start + size]


class Request:
    def __init__(self, session, method, url, kwargs):
        self.session, self.method, self.url, self.kwargs = session, method, url, kwargs

    async def __aenter__(self):
        return await self.session.handle(self.method, self.url, self.kwargs)

    async def __aexit__(self, *_args):
        pass


class Session:
    def __init__(self):
        self.calls, self.overrides = [], {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, deepcopy(kwargs)))
        assert kwargs["allow_redirects"] is False
        return Request(self, method, url, kwargs)

    async def handle(self, method, url, kwargs):
        host, path = url.split(".invalid", 1)
        if override := self.overrides.get((method, path)):
            return await override(host, kwargs)
        if path == "/v1/images/models":
            return Response(200, {"models": ["paint"]})
        if path.startswith("/object_info/"):
            node = path.split("/")[-1]
            field, models = {
                "CheckpointLoaderSimple": ("ckpt_name", ["local.safetensors"]),
                "UNETLoader": ("unet_name", ["z_image_turbo_bf16.safetensors"]),
                "CLIPLoader": ("clip_name", ["qwen_3_4b_fp8_mixed.safetensors"]),
                "VAELoader": ("vae_name", ["ae.safetensors"]),
            }[node]
            return Response(200, {node: {"input": {"required": {field: [models]}}}})
        if method == "POST" and path == "/v1/images":
            return Response(202, {"job_id": kwargs["json"]["request_id"], "status": "queued"})
        if path.startswith("/v1/images/") and not path.endswith("/content"):
            return Response(200, {"job_id": path.split("/")[-1], "status": "succeeded"})
        if path == "/prompt":
            return Response(200, {"prompt_id": REMOTE, "number": 0, "node_errors": {}})
        if path.startswith("/history/"):
            return Response(
                200,
                {
                    REMOTE: {
                        "status": {"completed": True, "status_str": "success"},
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "synthetic.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        },
                    }
                },
            )
        if path.endswith("/content") or path == "/view":
            return Response(200, png(), "image/png")
        raise AssertionError((method, path))


def configuration(*types):
    return {
        "enabled": True,
        "providers": [
            {
                "id": f"provider{index}",
                "type": kind,
                "url": f"https://{kind}{index}.example.invalid",
                "model": "paint" if kind == "agy_gateway" else "local.safetensors",
                "api_key": "synthetic-provider-secret",
            }
            for index, kind in enumerate(types)
        ],
    }


@pytest.fixture
async def env(engine, store, now, tmp_path):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["parent"]["telegram_id"] = 202
    engine = Engine(state, store.save)
    session, clock = Session(), SimpleNamespace(now=now)
    files = ImageFiles(tmp_path / "private", decoder=decode)
    config = configuration("agy_gateway", "comfyui")
    scope = {"valid": True}

    def guard():
        if not scope["valid"]:
            raise DomainError("forbidden")

    def service(selected=None, source=None):
        return ImageJobs(
            source or engine,
            session,
            files,
            selected or config,
            clock=lambda: clock.now,
            scope_check=guard,
            scope_id="synthetic-household",
        )

    delivered = []

    async def deliver(job, data, mime, guard):
        guard()
        delivered.append((deepcopy(job), data, mime))
        return "100"

    return SimpleNamespace(
        engine=engine,
        store=store,
        now=now,
        clock=clock,
        session=session,
        files=files,
        config=config,
        jobs=service(),
        service=service,
        scope=scope,
        delivered=delivered,
        deliver=deliver,
    )


async def enqueue(env, *, operation="synthetic-request", prompt="A friendly blue robot"):
    return await env.jobs.enqueue(
        "parent",
        prompt,
        operation,
        bot_id=9001,
        chat_id=202,
        reply_to=30,
        command_guard=lambda state: None,
    )


def stored(env):
    return next(iter(env.jobs.engine.snapshot()["image_jobs"].values()))


def posts(env):
    return [(url, kwargs) for method, url, kwargs in env.session.calls if method == "POST"]


@pytest.mark.asyncio
async def test_real_chain_private_verified_file_durable_replay(env):
    row = await enqueue(env)
    assert not env.session.calls
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "complete"
    assert env.delivered[0][1:] == (png(), "image/png")
    assert len(posts(env)) == 1
    assert not any("comfyui" in url for _, url, _ in env.session.calls)
    assert posts(env)[0][1]["json"] == {
        "request_id": row["id"],
        "prompt": "A friendly blue robot",
        "model": "paint",
        "width": 512,
        "height": 512,
    }
    raw = json.dumps(env.engine.snapshot())
    assert "synthetic-provider-secret" not in raw and "base64" not in raw
    assert project(env.engine.snapshot(), "child") == []
    assert set(project(env.engine.snapshot(), "parent")[0]) == {
        "id",
        "status",
        "created_at",
        "expires_at",
    }
    assert len(list(env.files.root.iterdir())) == 1
    env.jobs = env.service(source=Engine(env.engine.snapshot(), env.store.save))
    assert (await enqueue(env))["status"] == "complete"
    await env.jobs.step(9001, env.deliver)
    assert len(posts(env)) == len(env.delivered) == 1
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await enqueue(env, prompt="Changed prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["quota", "offline", "failed_quota"])
async def test_confirmed_no_submission_or_zero_output_allows_comfy_fallback(env, reason):
    async def failure(_host, _kwargs):
        if reason == "offline":
            raise TimeoutError
        return Response(429, {})

    if reason == "offline":
        env.session.overrides[("GET", "/v1/images/models")] = failure
    elif reason == "quota":
        env.session.overrides[("POST", "/v1/images")] = failure
    row = await enqueue(env)
    if reason == "failed_quota":

        async def failed(_host, _kwargs):
            return Response(
                200, {"job_id": row["id"], "status": "failed", "error": {"code": "quota_exceeded"}}
            )

        env.session.overrides[("GET", "/v1/images/" + row["id"])] = failed
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "queued" and stored(env)["provider_index"] == 1
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "complete" and len(env.delivered) == 1
    graph = posts(env)[-1][1]["json"]["prompt"]
    assert graph["6"]["inputs"]["text"] == "A friendly blue robot"
    assert graph["5"]["inputs"]["batch_size"] == 1


@pytest.mark.asyncio
async def test_z_image_turbo_uses_official_local_only_graph_and_exact_assets(env):
    config = configuration("comfyui")
    config.update(steps=8, cfg=1)
    config["providers"][0].update(
        workflow="z_image_turbo",
        model="z_image_turbo_bf16.safetensors",
        encoder="qwen_3_4b_fp8_mixed.safetensors",
        vae="ae.safetensors",
    )
    env.jobs = env.service(config)
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    graph = posts(env)[0][1]["json"]["prompt"]
    assert graph["4"]["class_type"] == "UNETLoader"
    assert graph["10"]["inputs"] == {
        "clip_name": "qwen_3_4b_fp8_mixed.safetensors",
        "type": "lumina2",
        "device": "default",
    }
    assert graph["11"]["inputs"] == {"vae_name": "ae.safetensors"}
    assert graph["12"]["inputs"] == {"model": ["4", 0], "shift": 3}
    assert graph["5"]["class_type"] == "EmptySD3LatentImage"
    assert graph["7"]["class_type"] == "ConditioningZeroOut"
    assert graph["3"]["inputs"]["sampler_name"] == "res_multistep"
    assert graph["3"]["inputs"]["scheduler"] == "simple"
    assert graph["3"]["inputs"]["cfg"] == 1 and graph["3"]["inputs"]["steps"] == 8
    assert stored(env)["status"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["agy_gateway", "comfyui"])
async def test_submission_timeout_never_reposts_after_restart(env, kind):
    env.jobs = env.service(configuration(kind, "comfyui"))

    async def timeout(_host, _kwargs):
        raise TimeoutError

    env.session.overrides[("POST", "/v1/images" if kind == "agy_gateway" else "/prompt")] = timeout
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    config = deepcopy(env.jobs.config)
    # Exact raw config digest is intentionally pinned; restart with same source config.
    env.jobs = env.service(
        configuration(kind, "comfyui"), Engine(env.engine.snapshot(), env.store.save)
    )
    await env.jobs.step(9001, env.deliver)
    assert len(posts(env)) == 1
    assert stored(env)["status"] == ("complete" if kind == "agy_gateway" else "uncertain")
    assert len(env.delivered) == (1 if kind == "agy_gateway" else 0)
    assert config["providers"][1]["type"] == "comfyui"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoke", "rebind", "disable", "provider"])
async def test_inflight_authority_change_never_fetches_or_sends_result(env, change):
    async def mutate(_host, kwargs):
        if change == "provider":
            env.scope["valid"] = False
        else:

            def update(ctx):
                if change == "disable":
                    ctx.state["settings"]["modules"].remove("conversation")
                elif change == "revoke":
                    ctx.state["members"]["parent"]["active"] = False
                else:
                    ctx.state["members"]["parent"]["telegram_id"] = 303

            await env.engine.system_update("synthetic-revoke", env.now, update)
        return Response(202, {"job_id": kwargs["json"]["request_id"], "status": "queued"})

    env.session.overrides[("POST", "/v1/images")] = mutate
    await enqueue(env)
    try:
        await env.jobs.step(9001, env.deliver)
    except DomainError as error:
        assert change == "provider" and error.code == "forbidden"
    assert not env.delivered
    assert not any(url.endswith("/content") for _, url, _ in env.session.calls)
    assert not env.files.root.exists()


@pytest.mark.asyncio
async def test_uncertain_telegram_send_is_never_blindly_retried(env):
    sends = []

    async def uncertain(*args):
        sends.append(args)
        raise DeliveryError("telegram_timeout", uncertain=True)

    await enqueue(env)
    await env.jobs.step(9001, uncertain)
    assert stored(env)["status"] == "uncertain"
    await env.jobs.step(9001, uncertain)
    assert len(sends) == len(posts(env)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", ["submitting", "polling", "delivering"])
async def test_store_failure_leaves_safe_durable_intent(env, checkpoint):
    original = env.store.save

    async def fail(state):
        row = next(iter(state.get("image_jobs", {}).values()), {})
        if row.get("status") == checkpoint:
            raise OSError("synthetic storage failure")
        await original(state)

    env.jobs = env.service(configuration("comfyui"), Engine(env.engine.snapshot(), fail))
    await enqueue(env)
    with pytest.raises(OSError):
        await env.jobs.step(9001, env.deliver)
    assert len(posts(env)) == (0 if checkpoint == "submitting" else 1)
    assert not env.delivered
    recovered = Engine(env.jobs.engine.snapshot(), original)
    env.jobs = env.service(configuration("comfyui"), recovered)
    await env.jobs.step(9001, env.deliver)
    if checkpoint == "polling":
        assert stored(env)["status"] == "uncertain" and len(posts(env)) == 1
    else:
        assert stored(env)["status"] == "complete" and len(posts(env)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,mime",
    [
        (b"not an image", "image/png"),
        (png(), "text/html"),
        (b"x" * 6_000_001, "image/png"),
        (png((1025, 1)), "image/png"),
    ],
    ids=["corrupt", "wrong-mime", "oversize-bytes", "oversize-dimensions"],
)
async def test_invalid_or_oversize_output_never_delivers(env, content, mime):
    row = await enqueue(env)

    async def bad(_host, _kwargs):
        return Response(200, content, mime)

    env.session.overrides[("GET", "/v1/images/" + row["id"] + "/content")] = bad
    await env.jobs.step(9001, env.deliver)
    assert not env.delivered
    assert stored(env)["status"] == "failed"
    assert not env.files.root.exists() or not list(env.files.root.iterdir())


@pytest.mark.asyncio
async def test_retention_cleanup_does_not_need_telegram_and_keeps_dedup(env):
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    env.clock.now += timedelta(hours=25)
    assert await env.jobs.collect()
    assert not list(env.files.root.iterdir())
    assert stored(env)["status"] == "complete" and not stored(env)["artifact"]
    assert (await enqueue(env))["status"] == "complete"
    assert len(posts(env)) == 1


@pytest.mark.asyncio
async def test_queue_bounds_and_private_history(env):
    for index in range(3):
        await enqueue(env, operation=f"job{index}")
    with pytest.raises(DomainError, match="image_busy"):
        await enqueue(env, operation="job4")
    assert len(project(env.engine.snapshot(), "parent")) == 3
    assert project(env.engine.snapshot(), "owner") == []
    assert not env.session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["../secret", "https://evil.invalid/x", "a\\b", "/absolute", ".."])
async def test_comfy_output_path_cannot_escape_configured_endpoint(env, path):
    env.jobs = env.service(configuration("comfyui"))

    async def bad(_host, _kwargs):
        return Response(
            200,
            {
                REMOTE: {
                    "status": {"completed": True},
                    "outputs": {
                        "9": {"images": [{"filename": path, "subfolder": "", "type": "output"}]}
                    },
                }
            },
        )

    env.session.overrides[("GET", "/history/" + REMOTE)] = bad
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "failed" and not env.delivered
    assert not any(url.endswith("/view") for _, url, _ in env.session.calls)


@pytest.mark.parametrize(
    "value", ["draw a blue robot", "нарисуй синего робота", "намалюй синього робота", "/draw robot"]
)
def test_only_explicit_draw_requests(value):
    assert prompt(value)


@pytest.mark.parametrize(
    "value",
    [
        "do not draw a robot",
        "не нарисуй робота",
        "не малюй робота",
        "I like drawings",
        '"draw a robot"',
        "describe this photo",
    ],
)
def test_dialogue_negation_and_quotations_are_not_drawing_requests(value):
    assert prompt(value) is None


def test_disabled_drafts_require_no_endpoint_or_model_but_enabled_config_is_strict():
    assert normalize_provider({"id": "draft", "type": "comfyui", "enabled": False})["url"] == ""
    with pytest.raises(DomainError):
        normalize_provider({"id": "draft", "type": "comfyui"})
    with pytest.raises(DomainError):
        normalize_config({"enabled": True, "providers": []})
    with pytest.raises(DomainError):
        normalize_config({"width": True})


@pytest.mark.asyncio
async def test_discovery_before_model_selection_is_read_only(env):
    row = {
        "id": "draft",
        "type": "comfyui",
        "enabled": False,
        "url": "https://comfy.example.invalid",
        "workflow": "z_image_turbo",
    }
    result = await ImageProvider(env.session, row).inspect()
    assert result["models"] == ["z_image_turbo_bf16.safetensors"]
    assert result["encoders"] == ["qwen_3_4b_fp8_mixed.safetensors"]
    assert result["vaes"] == ["ae.safetensors"]
    assert not posts(env)


@pytest.mark.asyncio
async def test_accepted_job_get_quota_never_starts_fallback(env):
    row = await enqueue(env)

    async def limited(_host, _kwargs):
        return Response(429, {})

    env.session.overrides[("GET", "/v1/images/" + row["id"])] = limited
    await env.jobs.step(9001, env.deliver)
    assert len(posts(env)) == 1
    assert stored(env)["provider_index"] == 0
    assert not env.delivered


@pytest.mark.asyncio
async def test_provider_authentication_is_terminal(env):
    async def denied(_host, _kwargs):
        return Response(403, {})

    env.session.overrides[("POST", "/v1/images")] = denied
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "failed"
    assert len(posts(env)) == 1 and not env.delivered


@pytest.mark.asyncio
async def test_request_identifiers_are_scoped_to_household(env):
    first = await enqueue(env)
    other = ImageJobs(
        Engine(env.engine.snapshot(), env.store.save),
        env.session,
        env.files,
        env.config,
        clock=lambda: env.now,
        scope_check=lambda: None,
        scope_id="another-household",
    )
    second = await other.enqueue(
        "parent",
        "A friendly blue robot",
        "synthetic-request",
        bot_id=9001,
        chat_id=202,
        reply_to=30,
        command_guard=lambda state: None,
    )
    assert first["id"] != second["id"]
    assert UUID(first["id"]) and UUID(second["id"])


@pytest.mark.asyncio
async def test_gateway_uncertain_status_is_not_failed_or_fallback(env):
    row = await enqueue(env)

    async def uncertain(_host, _kwargs):
        return Response(200, {"job_id": row["id"], "status": "uncertain"})

    env.session.overrides[("GET", "/v1/images/" + row["id"])] = uncertain
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == "uncertain"
    assert len(posts(env)) == 1 and not env.delivered
    notices = [
        event
        for event in env.engine.snapshot()["outbox"].values()
        if event["data"].get("image_job_id") == row["id"]
    ]
    assert len(notices) == 1 and "uncertain" in notices[0]["data"]["text"]
    assert notices[0]["data"]["private_context"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["agy_gateway", "comfyui"])
async def test_cancelled_post_keeps_recoverable_or_uncertain_intent(env, kind):
    started = asyncio.Event()

    async def pending(_host, _kwargs):
        started.set()
        await asyncio.Event().wait()

    env.jobs = env.service(configuration(kind, "comfyui"))
    env.session.overrides[("POST", "/v1/images" if kind == "agy_gateway" else "/prompt")] = pending
    await enqueue(env)
    running = asyncio.create_task(env.jobs.step(9001, env.deliver))
    await started.wait()
    running.cancel("synthetic reload")
    with pytest.raises(asyncio.CancelledError, match="synthetic reload"):
        await running
    assert stored(env)["status"] == "submitting"
    restarted = Engine(env.jobs.engine.snapshot(), env.store.save)
    env.jobs = env.service(configuration(kind, "comfyui"), restarted)
    await env.jobs.step(9001, env.deliver)
    assert stored(env)["status"] == ("complete" if kind == "agy_gateway" else "uncertain")
    assert len(posts(env)) == 1


@pytest.mark.asyncio
async def test_expired_old_bot_job_is_cancelled_by_cleanup_without_bot(env):
    await enqueue(env)
    env.clock.now += timedelta(minutes=11)
    assert await env.jobs.collect()
    assert stored(env)["status"] == "cancelled"
    assert await env.jobs.collect()
    assert stored(env)["blob_reserved"] is False
    assert not env.session.calls


@pytest.mark.asyncio
async def test_disabled_cleanup_deletes_orphan_after_revocation_during_publish(env):
    row = await enqueue(env)
    original = env.files.put

    async def revoked_put(*args, **kwargs):
        result = await original(*args, **kwargs)

        def revoke(ctx):
            ctx.state["members"]["parent"]["active"] = False

        await env.engine.system_update("synthetic-publish-revoke", env.now, revoke)
        return result

    env.files.put = revoked_put
    await env.jobs.step(9001, env.deliver)
    assert not env.delivered and stored(env)["status"] == "cancelled"
    assert (env.files.root / row["blob_key"]).exists()
    assert await env.jobs.collect()
    assert not list(env.files.root.iterdir())


@pytest.mark.asyncio
async def test_missing_cache_after_restore_does_not_regenerate(env):
    original = env.store.save

    async def stop_at_delivery(state):
        row = next(iter(state.get("image_jobs", {}).values()), {})
        if row.get("status") == "delivering":
            raise OSError("synthetic stop")
        await original(state)

    env.jobs = env.service(
        configuration("comfyui"), Engine(env.engine.snapshot(), stop_at_delivery)
    )
    await enqueue(env)
    with pytest.raises(OSError):
        await env.jobs.step(9001, env.deliver)
    await env.files.remove(stored(env)["blob_key"])
    env.jobs = env.service(configuration("comfyui"), Engine(env.jobs.engine.snapshot(), original))
    with pytest.raises(OSError):
        await env.jobs.step(9001, env.deliver)
    assert len(posts(env)) == 1 and not env.delivered


@pytest.mark.asyncio
async def test_confirmed_telegram_rate_limit_obeys_retry_after_without_regeneration(env):
    sends = []

    async def limited(*args):
        sends.append(args)
        raise DeliveryError("telegram_rate_limited", retryable=True, retry_after=60)

    await enqueue(env)
    await env.jobs.step(9001, limited)
    assert stored(env)["status"] == "ready"
    await env.jobs.step(9001, env.deliver)
    assert not env.delivered
    env.clock.now += timedelta(seconds=60)
    await env.jobs.step(9001, env.deliver)
    assert len(sends) == len(env.delivered) == len(posts(env)) == 1


@pytest.mark.asyncio
async def test_failed_image_notice_is_revoked_with_module_or_identity(env):
    from custom_components.family_assistant.telegram.reply_delivery import current

    async def denied(_host, _kwargs):
        return Response(403, {})

    env.session.overrides[("POST", "/v1/images")] = denied
    await enqueue(env)
    await env.jobs.step(9001, env.deliver)
    state = env.engine.snapshot()
    event = next(row for row in state["outbox"].values() if row["data"].get("image_job_id"))
    assert current(event, state, env.now)
    other = deepcopy(state)
    other["settings"]["modules"].remove("conversation")
    assert not current(event, other, env.now)
    other = deepcopy(state)
    other["members"]["parent"]["telegram_id"] = 303
    assert not current(event, other, env.now)
