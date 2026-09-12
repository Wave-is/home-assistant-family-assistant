"""Bounded, durable photo evidence inbox; no model or direct filesystem access."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta

from ..domain import media
from ..domain.task_access import private_task
from ..domain.task_delivery import current_task_event
from ..domain.validation import DomainError, timestamp
from ..notifications import DeliveryError
from .errors import ERRORS
from .router import COPY, image_file_id

COPY_REPORT = {
    "en": {
        "queued": "Photo report for {id} queued for verification; not submitted yet.",
        "done": "Photo report for {id} saved and submitted for review.",
    },
    "ru": {
        "queued": "Фотоотчёт {id} в очереди на проверку файла; "
        "ещё не отправлен на проверку задачи.",
        "done": "Фотоотчёт {id} сохранён и отправлен на проверку.",
    },
    "uk": {
        "queued": "Фотозвіт {id} у черзі на перевірку файлу; ще не поданий на перевірку завдання.",
        "done": "Фотозвіт {id} збережено та подано на перевірку.",
    },
}
_REPORT = re.compile(r"^/(?:report|фотоотчет|фотоотчёт|фотозвіт)(?:\s|$)", re.IGNORECASE)
_TARGET = re.compile(r"^/(?:report|фотоотчет|фотоотчёт|фотозвіт)\s+(T[0-9]{6,})$", re.IGNORECASE)


def _reply_target(state, message, bot):
    """Only a uniquely receipted, still-current task prompt grants a reference."""
    quoted = message.get("reply_to_message", {})
    if not isinstance(quoted, dict) or quoted.get("from", {}).get("id") != bot["id"]:
        return None
    receipt, chat_id = quoted.get("message_id"), message.get("chat", {}).get("id")
    if type(receipt) is not int or type(chat_id) is not int:
        raise DomainError("photo_target_required")
    matches = []
    for event in state.get("outbox", {}).values():
        for delivery in event.get("deliveries", {}).values():
            target = delivery.get("target", {})
            if (
                delivery.get("state") == "sent"
                and delivery.get("receipt") == str(receipt)
                and target.get("channel") == "telegram"
                and target.get("bot_id") == bot["id"]
                and str(target.get("id")) == str(chat_id)
            ):
                matches.append(event)
    if (
        len(matches) != 1
        or matches[0].get("key") not in {"task_assigned", "task_reminder"}
        or not current_task_event(state, matches[0])
    ):
        raise DomainError("photo_target_required")
    return matches[0]["data"]["id"]


class PhotoReports:
    def __init__(self, manager):
        self.manager = manager

    @property
    def engine(self):
        return self.manager.runtime.engine

    def _binding(self, job, state):
        manager = self.manager
        if (
            job.get("config_digest") != manager._telegram_options_digest
            or job.get("bot_id") != manager.bot["id"]
        ):
            raise DomainError("forbidden")
        manager._command_guard(
            actor=job["actor"],
            actor_revision=job["member_revision"],
            role=job["role"],
            language=job["language"],
            telegram_id=job["telegram_id"],
            chat_id=job["chat_id"],
            private=job["chat_id"] > 0,
        )(state)

    def _guard(self, job, storage):
        def guard(state):
            self._binding(job, state)
            if (
                self.manager.runtime.media is not storage
                or storage.engine is not self.engine
                or state["telegram"].get("photo_jobs", {}).get(job["id"]) != job
                or job["status"] != "pending"
            ):
                raise DomainError("forbidden")
            if self.now() >= timestamp(job["expires_at"], "expires_at"):
                raise DomainError("photo_report_expired")

        return guard

    @staticmethod
    def now():
        from homeassistant.util import dt as dt_util

        return dt_util.utcnow()

    async def enqueue(self, engine, actor, message, content, operation_id, now):
        explicit = bool(_REPORT.match(content))
        has_image = bool(message.get("photo") or message.get("document"))
        if not explicit and not has_image:
            return None
        state = engine.snapshot()
        if explicit:
            match = _TARGET.fullmatch(content.strip())
            if match is None:
                raise DomainError("photo_caption_unsupported")
            task_id = match[1].upper()
        else:
            task_id = _reply_target(state, message, self.manager.bot)
            if task_id is None:
                return None
            if message.get("caption") or message.get("text"):
                raise DomainError("photo_caption_unsupported")
        if message.get("media_group_id"):
            raise DomainError("photo_single_required")
        # Never re-use a quoted photo as new evidence supplied by this sender.
        file_id = image_file_id(
            {key: message[key] for key in ("photo", "document") if key in message}
        )
        if file_id is None:
            raise DomainError("photo_required")
        member = state["members"][actor]
        chat_id = message["chat"]["id"]
        job = {
            "id": operation_id,
            "actor": actor,
            "member_revision": member["revision"],
            "role": member["role"],
            "language": member["language"],
            "telegram_id": member["telegram_id"],
            "chat_id": chat_id,
            "bot_id": self.manager.bot["id"],
            "reply_to": message["message_id"],
            "config_digest": self.manager._telegram_options_digest,
            "task_id": task_id,
            "image_file_id": file_id,
        }
        previous = state["telegram"].get("photo_jobs", {}).get(operation_id)
        if previous is not None:
            if any(previous.get(key) != value for key, value in job.items()):
                raise DomainError("idempotency_conflict")
            self._binding(previous, state)
            if previous.get("status") not in {"complete", "pending"}:
                raise DomainError("photo_unavailable")
            key = "done" if previous.get("status") == "complete" else "queued"
            return COPY_REPORT[member["language"]][key].format(id=task_id)
        visible = {task["id"]: task for task in engine.view(actor, now=now)["tasks"]}
        task = visible.get(task_id)
        if task is None:
            raise DomainError("forbidden")
        if chat_id <= 0 and private_task(state["tasks"][task_id]):
            raise DomainError("forbidden")
        job["task_revision"] = task["revision"]
        job.update(
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        )
        pending = [
            row
            for row in state["telegram"].get("photo_jobs", {}).values()
            if row.get("status") == "pending"
        ]
        if len(pending) >= 20 or sum(row["actor"] == actor for row in pending) >= 3:
            raise DomainError("assistant_busy")
        reserved = await engine.execute(
            actor,
            "media.reserve",
            {
                "purpose": media.PURPOSE,
                "uploader_revision": member["revision"],
                "task_id": task_id,
                "task_revision": task["revision"],
            },
            operation_id + ":reserve",
            now,
        )
        job["media_id"] = reserved["id"]
        job["media_revision"] = reserved["revision"]

        def save(ctx):
            self._binding(job, ctx.state)
            media.authorize_blob(ctx.state, ctx.state["members"][actor], reserved["id"], ctx.now)
            jobs = ctx.state["telegram"].setdefault("photo_jobs", {})
            existing = jobs.get(operation_id)
            if existing is not None:
                if existing != job:
                    raise DomainError("idempotency_conflict")
                return
            pending = [row for row in jobs.values() if row.get("status") == "pending"]
            if len(pending) >= 20 or sum(row["actor"] == actor for row in pending) >= 3:
                raise DomainError("assistant_busy")
            while len(jobs) >= 100:
                oldest = next(
                    (key for key, row in jobs.items() if row["status"] != "pending"), None
                )
                if oldest is None:
                    raise DomainError("assistant_busy")
                jobs.pop(oldest)
            jobs[operation_id] = job

        await engine.system_update("telegram_photo_queued", now, save)
        return COPY_REPORT[member["language"]]["queued"].format(id=task_id)

    async def run_one(self):
        manager = self.manager
        manager._manager_guard(self.engine.snapshot())
        job = next(
            (
                row
                for row in self.engine.snapshot()["telegram"].get("photo_jobs", {}).values()
                if row["status"] == "pending"
            ),
            None,
        )
        if job is None:
            return False
        storage = getattr(manager.runtime, "media", None)
        code = None
        try:
            self._binding(job, self.engine.snapshot())
            submit_id = job["id"] + ":submit"
            # A crash after canonical submission but before queue completion is
            # recovered from its persisted receipt, never by submitting twice.
            result = self.engine.snapshot()["processed"].get(submit_id, {}).get("result")
            if result is None:
                if storage is None:
                    raise DomainError("media_unavailable")
                guard = self._guard(job, storage)
                guard(self.engine.snapshot())
                record = media.authorize_blob(
                    self.engine.snapshot(),
                    self.engine.snapshot()["members"][job["actor"]],
                    job["media_id"],
                    self.now(),
                )
                if record["status"] == "reserved":
                    content = await manager.client.download_file(job["image_file_id"])
                    guard(self.engine.snapshot())

                    async def chunks():
                        from ..media_storage import MAX_CHUNK

                        for offset in range(0, len(content), MAX_CHUNK):
                            yield content[offset : offset + MAX_CHUNK]

                    async def async_guard():
                        guard(self.engine.snapshot())

                    record = await storage.put_for_actor(
                        job["actor"],
                        job["member_revision"],
                        job["media_id"],
                        job["media_revision"],
                        chunks(),
                        guard=async_guard,
                        state_guard=guard,
                    )
                guard(self.engine.snapshot())
                result = await self.engine.execute(
                    job["actor"],
                    "tasks.submit",
                    {
                        "id": job["task_id"],
                        "revision": job["task_revision"],
                        "media": {"id": record["id"], "revision": record["revision"]},
                    },
                    submit_id,
                    self.now(),
                    guard=guard,
                )
            if result.get("id") != job["task_id"] or result.get("status") != "submitted":
                raise DomainError("conflict")
        except DomainError as error:
            if error.code == "backup_in_progress":
                raise
            code = error.code
        except (DeliveryError, TimeoutError):
            code = "photo_unavailable"

        def finish(ctx):
            stored = ctx.state["telegram"].get("photo_jobs", {}).get(job["id"])
            if stored != job:
                raise DomainError("forbidden")
            try:
                self._binding(job, ctx.state)
            except DomainError:
                stored.update(status="cancelled", finished_at=ctx.now.isoformat())
                return
            stored.update(status="failed" if code else "complete", finished_at=ctx.now.isoformat())
            text = (
                COPY[job["language"]]["error"].format(error=ERRORS[job["language"]].get(code, code))
                if code
                else COPY_REPORT[job["language"]]["done"].format(id=job["task_id"])
            )
            ctx.operation_id = job["id"] + ":photo-result"
            ctx.notify(
                job["actor"],
                "telegram_reply",
                {
                    "text": text,
                    "actor": job["actor"],
                    "actor_revision": job["member_revision"],
                    "bot_id": job["bot_id"],
                    "chat_id": job["chat_id"],
                    "reply_to": job["reply_to"],
                    "refs": [job["task_id"]],
                },
            )

        await self.engine.system_update(
            "telegram_photo_finished", self.now(), finish, guard=manager._manager_guard
        )
        manager.runtime.updated()
        return True

    async def run(self):
        from homeassistant.config_entries import ConfigEntryState

        try:
            async with asyncio.timeout(30):
                while self.manager.entry.state is not ConfigEntryState.LOADED:
                    self.manager._manager_guard(starting=True)
                    await asyncio.sleep(0.1)
        except (DomainError, TimeoutError):
            return
        while not self.manager._stopped:
            try:
                await self.run_one()
                self.manager.runtime.health.pop("telegram_photo_storage", None)
            except DomainError as error:
                if error.code != "backup_in_progress":
                    return
                await self.engine.async_wait_writable()
            except OSError:
                self.manager.runtime.health["telegram_photo_storage"] = "storage_error"
            await asyncio.sleep(1)
