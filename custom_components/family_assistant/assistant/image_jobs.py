"""Durable image requests and conservative provider/delivery recovery.

Only prompts explicitly supplied to /draw reach a provider. No family view,
quote, file, credential, or untrusted URL enters this protocol. Binary results
are private files, not Engine state or frontend resources.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from ..domain.validation import DomainError, text, timestamp
from ..notifications import DeliveryError
from .image_providers import MAX_BYTES, ImageError, ImageProvider, normalize_config

ACTIVE = {"queued", "submitting", "polling", "ready", "delivering"}
MAX_JOBS = 1000  # Durable dedup tombstones are never silently dropped.
MAX_PENDING = 20
MAX_RETAINED = 10  # At most 60 MB, including a reservation for every active job.


def digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()


def project(state, actor):
    member = state.get("members", {}).get(actor, {})
    if member.get("active") is not True:
        return []
    return [
        {
            key: row[key]
            for key in ("id", "status", "created_at", "expires_at", "error")
            if key in row
        }
        for row in list(state.get("image_jobs", {}).values())[::-1]
        if row.get("actor") == actor and row.get("actor_revision") == member.get("revision")
    ][:20]


class ImageJobs:
    def __init__(
        self,
        engine,
        session,
        files,
        config,
        *,
        clock,
        scope_check,
        scope_id,
        provider_factory=ImageProvider,
    ):
        self.engine, self.files = engine, files
        self.config, self.marker = normalize_config(config), digest(config)
        self.clock, self.scope_check = clock, scope_check
        self.scope_id = text(scope_id, "scope_id", 180)
        self.providers = [
            provider_factory(session, row) for row in self.config["providers"] if row["enabled"]
        ]
        self._busy = False
        self._closed = False

    def _guard(self, job=None, state=None):
        if self._closed:
            raise DomainError("forbidden")
        self.scope_check()
        self.engine._require_writable()
        state = self.engine.snapshot() if state is None else state
        if not self.config["enabled"] or "conversation" not in state["settings"]["modules"]:
            raise DomainError("module_disabled")
        if job is None:
            return
        row = state.get("image_jobs", {}).get(job["id"])
        member = state["members"].get(job["actor"], {})
        if (
            row != job
            or job["provider_scope"] != self.marker
            or member.get("active") is not True
            or member.get("role") != job["role"]
            or member.get("revision") != job["actor_revision"]
            or member.get("telegram_id") != job["chat_id"]
            or timestamp(self.clock(), "now") >= timestamp(job["expires_at"], "expires_at")
        ):
            raise DomainError("forbidden")

    async def enqueue(
        self, actor, prompt, operation_id, *, bot_id, chat_id, reply_to, command_guard
    ):
        self._guard()
        prompt, operation_id = text(prompt, "prompt", 2000), text(operation_id, "operation_id", 180)
        identifier = str(uuid5(NAMESPACE_URL, self.scope_id + ":" + operation_id))
        now = timestamp(self.clock(), "now")

        def save(ctx):
            self._guard(state=ctx.state)
            command_guard(ctx.state)
            member = ctx.state["members"].get(actor, {})
            if (
                member.get("active") is not True
                or member.get("role") == "guest"
                or type(chat_id) is not int
                or chat_id <= 0
                or member.get("telegram_id") != chat_id
            ):
                raise DomainError("forbidden")
            jobs = ctx.state.setdefault("image_jobs", {})
            prior = jobs.get(identifier)
            signature = digest([actor, prompt, bot_id, chat_id, reply_to])
            if prior:
                if prior["signature"] != signature:
                    raise DomainError("idempotency_conflict")
                if (
                    prior["actor_revision"] != member["revision"]
                    or prior["provider_scope"] != self.marker
                ):
                    raise DomainError("forbidden")
                return prior
            active = [row for row in jobs.values() if row["status"] in ACTIVE]
            retained = [row for row in jobs.values() if row.get("blob_reserved")]
            if (
                len(jobs) >= MAX_JOBS
                or len(active) >= MAX_PENDING
                or sum(row["actor"] == actor for row in active) >= 3
                or len(retained) >= MAX_RETAINED
            ):
                raise DomainError("image_busy")
            row = {
                "id": identifier,
                "actor": actor,
                "actor_revision": member["revision"],
                "role": member["role"],
                "language": member["language"],
                "chat_id": chat_id,
                "bot_id": bot_id,
                "reply_to": reply_to,
                "signature": signature,
                "prompt": prompt,
                "status": "queued",
                "provider_scope": self.marker,
                "provider_index": 0,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "retain_until": (now + timedelta(hours=24)).isoformat(),
                "blob_key": hashlib.sha256(identifier.encode()).hexdigest(),
                "blob_reserved": True,
                "revision": 1,
            }
            jobs[identifier] = row
            return row

        return await self.engine.system_update("image_queued", now, save)

    async def _change(self, job, *, guarded=True, **changes):
        def save(ctx):
            if self._closed:
                raise DomainError("forbidden")
            self.scope_check()
            self.engine._require_writable()
            if guarded:
                self._guard(job, ctx.state)
            stored = ctx.state.get("image_jobs", {}).get(job["id"])
            if stored != job:
                raise DomainError("conflict")
            stored.update(changes, revision=stored["revision"] + 1)
            if changes.get("status") in {"failed", "uncertain"}:
                member = ctx.state["members"].get(stored["actor"], {})
                if (
                    member.get("active") is True
                    and member.get("revision") == stored["actor_revision"]
                    and member.get("telegram_id") == stored["chat_id"]
                    and "conversation" in ctx.state["settings"]["modules"]
                ):
                    from ..telegram.image_generation import COPY, status

                    words = COPY[stored["language"]]
                    ctx.operation_id = stored["id"] + ":image-result"
                    ctx.notify(
                        stored["actor"],
                        "telegram_reply",
                        {
                            "text": words["queued"].format(
                                id=stored["id"], status=status(stored, words)
                            ),
                            "private_context": True,
                            "actor": stored["actor"],
                            "actor_revision": stored["actor_revision"],
                            "chat_id": stored["chat_id"],
                            "bot_id": stored["bot_id"],
                            "expires_at": (ctx.now + timedelta(minutes=10)).isoformat(),
                            "image_job_id": stored["id"],
                            "image_provider_scope": stored["provider_scope"],
                        },
                    )
            return stored

        return await self.engine.system_update("image_progress", self.clock(), save)

    async def _failed(self, job, code, *, uncertain=False):
        return await self._change(
            job, guarded=False, status="uncertain" if uncertain else "failed", error=code, prompt=""
        )

    async def step(self, bot_id, deliver):
        """One bounded pass; caller schedules polling, never a blocking wait loop."""
        if self._busy or self._closed:
            return
        self._busy = True
        try:
            if await self._collect():
                return
            jobs = list(self.engine.snapshot().get("image_jobs", {}).values())
            job = next(
                (row for row in jobs if row["bot_id"] == bot_id and row["status"] in ACTIVE), None
            )
            if job is None:
                return
            if job.get("next_attempt_at") and self.clock() < timestamp(
                job["next_attempt_at"], "next_attempt_at"
            ):
                return
            try:
                self._guard(job)
            except DomainError:
                await self._change(job, guarded=False, status="cancelled", prompt="")
                return
            provider = self.providers[job["provider_index"]]
            try:
                if job["status"] == "queued":
                    catalog = await provider.inspect()
                    self._guard(job)
                    if (
                        provider.config["model"] not in catalog["models"]
                        or provider.config.get("workflow") == "z_image_turbo"
                        and provider.config["type"] == "comfyui"
                        and (
                            provider.config["encoder"] not in catalog.get("encoders", [])
                            or provider.config["vae"] not in catalog.get("vaes", [])
                        )
                    ):
                        raise ImageError("image_model_unavailable")
                    # Persist before any POST. A crash may forfeit this attempt, never duplicate it.
                    job = await self._change(job, status="submitting")
                    self._guard(job)
                    remote_id = await provider.submit(job["prompt"], job["id"], self.config)
                    self._guard(job)
                    job = await self._change(job, status="polling", remote_id=remote_id)
                elif job["status"] == "submitting":
                    if provider.config["type"] != "agy_gateway":
                        await self._failed(job, "image_submission_uncertain", uncertain=True)
                        return
                    # Gateway identity is the durable request ID: recover by GET, never POST.
                    job = await self._change(job, status="polling", remote_id=job["id"])
                if job["status"] == "polling":
                    output = await provider.poll(job["remote_id"])
                    self._guard(job)
                    if output is None:
                        return
                    data, mime = await provider.content(job["remote_id"], output)
                    self._guard(job)
                    artifact = await self.files.put(
                        job["blob_key"], data, mime, guard=lambda: self._guard(job)
                    )
                    self._guard(job)
                    job = await self._change(job, status="ready", artifact=artifact, prompt="")
                if job["status"] == "delivering":
                    await self._failed(job, "image_delivery_uncertain", uncertain=True)
                    return
                if job["status"] == "ready":
                    data = await self.files.get(job["blob_key"])
                    self._guard(job)
                    artifact = job["artifact"]
                    if (
                        len(data) > MAX_BYTES
                        or len(data) != artifact["size_bytes"]
                        or hashlib.sha256(data).hexdigest() != artifact["sha256"]
                    ):
                        raise ImageError("image_invalid")
                    job = await self._change(job, status="delivering")
                    self._guard(job)
                    receipt = await deliver(
                        job, data, artifact["mime_type"], lambda: self._guard(job)
                    )
                    self._guard(job)
                    await self._change(
                        job, status="complete", message_id=text(str(receipt), "message_id", 80)
                    )
            except ImageError as error:
                self._guard(job)
                if error.uncertain:
                    if provider.config["type"] == "agy_gateway" and job["status"] == "submitting":
                        await self._change(
                            job,
                            status="polling",
                            remote_id=job["id"],
                            error="image_submission_uncertain",
                        )
                    else:
                        await self._failed(job, "image_submission_uncertain", uncertain=True)
                elif (
                    error.fallback
                    and job["status"] in {"submitting", "polling"}
                    or job["status"] == "queued"
                    and error.code
                    in {"provider_timeout", "provider_unreachable", "provider_quota_exceeded"}
                ) and job["provider_index"] + 1 < len(self.providers):
                    await self._change(
                        job,
                        status="queued",
                        provider_index=job["provider_index"] + 1,
                        error=error.code,
                        remote_id=None,
                    )
                elif job["status"] == "polling" and error.code in {
                    "provider_timeout",
                    "provider_unreachable",
                }:
                    return  # Safe GET retry; no fallback after accepted generation.
                else:
                    await self._failed(job, error.code)
            except DeliveryError as error:
                self._guard(job)
                if error.retryable and not error.uncertain:
                    await self._change(
                        job,
                        status="ready",
                        error=error.code,
                        next_attempt_at=(
                            self.clock() + timedelta(seconds=max(5, error.retry_after))
                        ).isoformat(),
                    )
                else:
                    await self._failed(
                        job,
                        "image_delivery_uncertain" if error.uncertain else error.code,
                        uncertain=error.uncertain,
                    )
            except DomainError as error:
                if error.code in {"backup_in_progress", "conflict"}:
                    raise
                if error.code in {"forbidden", "module_disabled"}:
                    await self._change(
                        job, guarded=False, status="cancelled", error="forbidden", prompt=""
                    )
                else:
                    await self._failed(
                        job,
                        "image_too_large" if error.code == "media_too_large" else "image_invalid",
                    )
        finally:
            self._busy = False

    async def _collect(self):
        self.scope_check()
        self.engine._require_writable()
        state = self.engine.snapshot()
        for row in state.get("image_jobs", {}).values():
            member = state["members"].get(row["actor"], {})
            if row["status"] in ACTIVE and (
                self.clock() >= timestamp(row["expires_at"], "expires_at")
                or row["provider_scope"] != self.marker
                or not self.config["enabled"]
                or "conversation" not in state["settings"]["modules"]
                or member.get("active") is not True
                or member.get("revision") != row["actor_revision"]
                or member.get("role") != row["role"]
                or member.get("telegram_id") != row["chat_id"]
            ):
                await self._change(row, guarded=False, status="cancelled", prompt="")
                return True
            if row.get("blob_reserved") and (
                self.clock() >= timestamp(row["retain_until"], "retain_until")
                or row["status"] not in ACTIVE
                and not row.get("artifact")
            ):
                await self.files.remove(row["blob_key"])
                await self._change(
                    row, guarded=False, artifact=None, prompt="", blob_reserved=False
                )
                return True
        return False

    async def collect(self):
        """Cleanup-only HA lifecycle hook, independent of Telegram being enabled."""
        if self._busy or self._closed:
            return False
        self._busy = True
        try:
            return await self._collect()
        finally:
            self._busy = False

    def close(self):
        self._closed = True
