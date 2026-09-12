"""One poller per configured bot, isolated from the deterministic HA clock."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from contextlib import suppress
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from ..assistant.chat_service import conversation_digest
from ..assistant.service import Assistant
from ..const import DOMAIN
from ..domain.validation import DomainError
from ..notifications import DeliveryError, Notifications
from .admission import AdmissionReply
from .context import PersonalReply, reply_quote, reply_refs, result_refs
from .enrollment import Enrollment
from .errors import ERRORS
from .messages import render, targets
from .polls import route as route_polls
from .router import COPY, addressed, route


def _digest(value):
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise DomainError("forbidden") from None
    return hashlib.sha256(encoded).hexdigest()


class _ScopedEngine:
    """Delegate trusted reads while guarding every locked mutation."""

    def __init__(self, engine, guard):
        self._engine, self._guard = engine, guard

    def snapshot(self):
        return self._engine.snapshot()

    def view(self, actor, *, now=None):
        return self._engine.view(actor, now=now)

    async def execute(self, actor, action, payload, operation_id, now):
        return await self._engine.execute(
            actor, action, payload, operation_id, now, guard=self._guard
        )

    async def system_update(self, kind, now, change):
        return await self._engine.system_update(kind, now, change, guard=self._guard)

    async def background_update(self, kind, now, change):
        while True:
            await self._engine.async_wait_writable()
            try:
                return await self.system_update(kind, now, change)
            except DomainError as error:
                if error.code != "backup_in_progress":
                    raise


class TelegramManager:
    def __init__(self, hass, entry, runtime, client, bot):
        self.hass, self.entry, self.runtime = hass, entry, runtime
        self.client, self.bot = client, bot
        self._client_identity = client
        self._bot_digest = _digest(bot)
        self._telegram_options_digest = _digest(dict(entry.options).get("telegram"))
        self.enrollment = Enrollment(runtime.engine)
        self.notifications = Notifications(
            runtime.engine,
            self._targets,
            self._send_notification,
            clock=dt_util.utcnow,
            presence_prepare=self._prepare_presence_notifications,
        )
        self._tasks = []
        self._stopped = False
        from ..assistant.jobs import Jobs

        self.jobs = Jobs(
            runtime.engine,
            clock=dt_util.utcnow,
            provider_scope=self._provider_scope,
        )
        from .photo_reports import PhotoReports

        self.photo_reports = PhotoReports(self)

    def _manager_guard(self, _state=None, *, starting=False):
        entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
        entries = self.hass.data.get(DOMAIN, {}).get("entries", {})
        if (
            self._stopped
            or entry is not self.entry
            or (not starting and self.entry.state is not ConfigEntryState.LOADED)
            or entries.get(self.entry.entry_id) is not self.runtime
            or self.entry.runtime_data is not self.runtime
            or self.runtime.engine is not getattr(self.enrollment, "engine", None)
            or self.runtime.telegram is not self
            or self.client is not self._client_identity
            or _digest(self.bot) != self._bot_digest
            or _digest(dict(self.entry.options).get("telegram")) != self._telegram_options_digest
        ):
            raise DomainError("forbidden")

    def _provider_scope(self):
        self._manager_guard()
        assistant = self.runtime.assistant
        digest = self.runtime.assistant_config_digest
        if (
            assistant is None
            or getattr(assistant, "cascade", None) is None
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or digest != conversation_digest(dict(self.entry.options).get("conversation"))
        ):
            raise DomainError("forbidden")
        return digest

    def _command_guard(
        self,
        *,
        actor,
        actor_revision,
        role,
        language,
        telegram_id,
        chat_id,
        private,
    ):
        def guard(state):
            self._manager_guard(state)
            member = state.get("members", {}).get(actor)
            group_id = state.get("telegram", {}).get("group_id")
            if (
                not isinstance(member, dict)
                or member.get("active") is not True
                or member.get("revision") != actor_revision
                or member.get("role") != role
                or member.get("language") != language
                or member.get("telegram_id") != telegram_id
                or (private and (chat_id != telegram_id or chat_id <= 0))
                or (not private and group_id != chat_id)
            ):
                raise DomainError("forbidden")

        return guard

    def _conversation_guard(self, job, assistant, cascade, search, source_revision):
        """Pin one queued inference to this manager, provider and sender epoch."""
        from ..assistant.jobs import Jobs

        provider_marker = self._provider_scope()
        if not isinstance(source_revision, str) or not re.fullmatch(
            r"[0-9a-f]{32}", source_revision
        ):
            raise DomainError("forbidden")

        def guard(state):
            self._manager_guard(state)
            stored = state.get("assistant_jobs", {}).get(job.get("id"))
            current_assistant = self.runtime.assistant
            if (
                not isinstance(stored, dict)
                or stored.get("status") != "pending"
                or not Jobs._same_job(job, stored)
                or self._provider_scope() != provider_marker
                or self.runtime.assistant_revision != source_revision
                or current_assistant is not assistant
                or getattr(current_assistant, "cascade", None) is not cascade
                or getattr(current_assistant, "search", None) is not search
                or Jobs._authority_error(state, stored, dt_util.utcnow()) is not None
            ):
                raise DomainError("forbidden")

        return guard

    async def _prepare_presence_notifications(self, state):
        from ..presence_notification_adapter import prepare

        return await prepare(self.hass, self.entry, self.runtime, state, self._manager_guard)

    def _targets(self, event, state):
        if (
            event["key"] in {"telegram_reply", "telegram_poll_reply"}
            and event["data"].get("bot_id") != self.bot["id"]
        ):
            return []
        return [{**target, "bot_id": self.bot["id"]} for target in targets(event, state)]

    def start(self):
        # Setup calls start before HA marks the entry LOADED. The complete
        # instance/config checks still prevent an old manager changing health.
        self._manager_guard(starting=True)
        if self._tasks:
            return
        self.runtime.health.pop("telegram", None)
        self._tasks = [
            self.hass.async_create_background_task(
                self._install_menu(), "Family Assistant Telegram command menu"
            ),
            self.hass.async_create_background_task(
                self._poll(), "Family Assistant Telegram polling"
            ),
            self.hass.async_create_background_task(
                self._outbox(), "Family Assistant Telegram outbox"
            ),
            self.hass.async_create_background_task(
                self._conversations(), "Family Assistant conversation inbox"
            ),
            self.hass.async_create_background_task(
                self.photo_reports.run(), "Family Assistant photo report inbox"
            ),
        ]

    async def stop(self):
        self._stopped = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task

    def _issue(self, code):
        self.runtime.health["telegram"] = code
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"telegram_{self.entry.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="telegram_attention",
        )

    async def _install_menu(self):
        from .menu import command_menu

        try:
            # An eagerly scheduled startup task may run before setup completes.
            async with asyncio.timeout(30):
                while self.entry.state is not ConfigEntryState.LOADED:
                    self._manager_guard(starting=True)
                    await asyncio.sleep(0.1)
            for language in ("", "en", "ru", "uk"):
                state = self.runtime.engine.snapshot()
                self._manager_guard(state)
                payload = {
                    "scope": {"type": "default"},
                    "language_code": language,
                    "commands": command_menu(language or state["settings"]["language"]),
                }
                result = await self.client.call("setMyCommands", payload)
                self._manager_guard(self.runtime.engine.snapshot())
                if result is not True:
                    raise DeliveryError("telegram_bad_response")
            self.runtime.health.pop("telegram_menu", None)
        except DeliveryError as error:
            with suppress(DomainError):
                self._manager_guard(self.runtime.engine.snapshot())
                self.runtime.health["telegram_menu"] = error.code
        except DomainError:
            return
        except TimeoutError:
            with suppress(DomainError):
                self._manager_guard(starting=True)
                self.runtime.health["telegram_menu"] = "telegram_timeout"

    async def _poll(self):
        backoff = 5
        while not self._stopped:
            try:
                await self.runtime.engine.async_wait_writable()
                if self.runtime.health.get("telegram") != "connected":
                    await self.client.inspect()
                state = self.runtime.engine.snapshot()
                updates = await self.client.updates(
                    state["telegram"].get("offsets", {}).get(str(self.bot["id"]))
                )
                for update in updates:
                    await self.process(update)
                self.runtime.health["telegram"] = "connected"
                ir.async_delete_issue(self.hass, DOMAIN, f"telegram_{self.entry.entry_id}")
                backoff = 5
            except DeliveryError as err:
                self._issue(err.code)
                if err.code in {
                    "telegram_invalid_token",
                    "telegram_webhook_conflict",
                    "telegram_polling_conflict",
                }:
                    return  # Do not fight another consumer or change its webhook.
                await asyncio.sleep(max(backoff, err.retry_after))
                backoff = min(120, backoff * 2)
            except DomainError as error:
                if error.code != "backup_in_progress":
                    raise
                await self.runtime.engine.async_wait_writable()
            except OSError:
                self._issue("storage_error")
                await asyncio.sleep(5)

    async def _outbox(self):
        while not self._stopped:
            try:
                await self.notifications.run(dt_util.utcnow())
                outbox = self.runtime.engine.snapshot()["outbox"]
                troubled = any(
                    event["state"] in {"uncertain", "failed"} for event in outbox.values()
                )
                if troubled:
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        f"delivery_{self.entry.entry_id}",
                        is_fixable=False,
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="delivery_attention",
                    )
                    self.runtime.health["notifications"] = "delivery_attention"
                else:
                    ir.async_delete_issue(self.hass, DOMAIN, f"delivery_{self.entry.entry_id}")
                    self.runtime.health.pop("notifications", None)
            except OSError:
                self.runtime.health["notifications"] = "storage_error"
            await asyncio.sleep(1)

    async def _send_notification(self, event, target):
        result = await self.client.call(
            "sendMessage",
            render(event, target, self.runtime.engine.snapshot(), now=dt_util.utcnow()),
        )
        return str(result["message_id"])

    async def _conversation_activity_call(self, job, guard, *, reaction=None):
        """Optional UI hints share the job's current identity and short timeout."""
        try:
            guard(self.runtime.engine.snapshot())
            if reaction is not None:
                if not job.get("reply_to"):
                    return
                method = "setMessageReaction"
                payload = {
                    "chat_id": job["chat_id"],
                    "message_id": job["reply_to"],
                    "reaction": reaction,
                }
            else:
                method = "sendChatAction"
                payload = {"chat_id": job["chat_id"], "action": "typing"}
            async with asyncio.timeout(2):
                await self.client.call(method, payload)
            guard(self.runtime.engine.snapshot())
        except (DomainError, DeliveryError, TimeoutError):
            return

    async def _conversation_activity(self, job, guard):
        await self._conversation_activity_call(
            job, guard, reaction=[{"type": "emoji", "emoji": "🤔"}]
        )
        while True:
            try:
                guard(self.runtime.engine.snapshot())
            except DomainError:
                return
            await self._conversation_activity_call(job, guard)
            await asyncio.sleep(4)

    async def _conversations(self):
        # Keep an already computed answer through a transient Store failure.
        # This is process-local, not an exactly-once promise across a crash.
        completion = None
        while not self._stopped:
            try:
                if completion is None and (job := self.jobs.next(self.bot["id"])) is not None:
                    cancelled = False
                    diagnostic_code = None
                    from ..assistant.jobs import Jobs

                    finish_jobs = Jobs(
                        _ScopedEngine(self.runtime.engine, self._manager_guard),
                        clock=dt_util.utcnow,
                        provider_scope=self._provider_scope,
                    )
                    typing_task = None
                    try:
                        actor = self.jobs.authorize(job, dt_util.utcnow())
                        assistant = self.runtime.assistant
                        if not assistant:
                            raise DomainError("provider_not_configured")
                        cascade = assistant.cascade
                        search = assistant.search
                        guard = self._conversation_guard(
                            job,
                            assistant,
                            cascade,
                            search,
                            self.runtime.assistant_revision,
                        )
                        scoped_engine = _ScopedEngine(self.runtime.engine, guard)
                        guard(self.runtime.engine.snapshot())
                        typing_task = asyncio.create_task(self._conversation_activity(job, guard))
                        images = None
                        if job.get("image_file_id"):
                            try:
                                data = await self.client.download_file(job["image_file_id"])
                            except (DeliveryError, DomainError) as error:
                                guard(self.runtime.engine.snapshot())
                                if (
                                    isinstance(error, DomainError)
                                    and error.code == "file_too_large"
                                ):
                                    raise
                                raise DomainError("photo_unavailable") from None
                            guard(self.runtime.engine.snapshot())
                            if not data:
                                raise DomainError("photo_unavailable")
                            images = [base64.b64encode(data).decode("ascii")]
                        response = await Assistant(scoped_engine, cascade, search).respond(
                            actor,
                            job["content"],
                            job["id"],
                            dt_util.parse_datetime(job["created_at"]),
                            job["refs"],
                            quoted_text=job.get("quoted_text", ""),
                            images=images,
                            scope_check=lambda guard=guard: guard(self.runtime.engine.snapshot()),
                        )

                        guard(self.runtime.engine.snapshot())
                    except (DomainError, TimeoutError) as err:
                        code = err.code if isinstance(err, DomainError) else "provider_timeout"
                        if code == "backup_in_progress":
                            raise
                        cancelled = code == "forbidden"
                        diagnostic_code = code
                        response = COPY[job["language"]]["error"].format(
                            error=ERRORS[job["language"]].get(code, code)
                        )
                    finally:
                        if typing_task is not None:
                            typing_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await typing_task
                            await self._conversation_activity_call(job, guard, reaction=[])
                    completion = (job, response, cancelled, finish_jobs, diagnostic_code)
                if completion is not None:
                    job, response, cancelled, finish_jobs, diagnostic_code = completion
                    await finish_jobs.finish(
                        job,
                        response,
                        dt_util.utcnow(),
                        cancelled=cancelled,
                        diagnostic_code=diagnostic_code,
                    )
                    completion = None
                    self.runtime.health.pop("conversation_storage", None)
                    self.runtime.updated()
            except DomainError as error:
                if error.code != "backup_in_progress":
                    raise
                await self.runtime.engine.async_wait_writable()
            except OSError:
                self.runtime.health["conversation_storage"] = "storage_error"
            await asyncio.sleep(1)

    async def process(self, update):
        if not isinstance(update, dict):
            return
        update_id = update.get("update_id")
        if type(update_id) is not int:
            return
        engine = self.runtime.engine
        self._manager_guard(engine.snapshot())
        bot_id = self.bot["id"]
        offset = engine.snapshot()["telegram"].get("offsets", {}).get(str(self.bot["id"]), -1)
        if update_id < offset:
            return
        now = dt_util.utcnow()
        message = update.get("message")
        callback = update.get("callback_query")
        manager_engine = _ScopedEngine(engine, self._manager_guard)
        captured = message and await Enrollment(manager_engine).capture(
            message, self.bot["username"], now
        )
        self._manager_guard(engine.snapshot())
        command_guard = None
        observation_key = None
        if not captured and (message or callback):
            sender = (message or callback).get("from", {})
            envelope = message or callback.get("message", {})
            chat = envelope.get("chat", {})
            try:
                if sender.get("is_bot") or envelope.get("sender_chat"):
                    raise DomainError("forbidden")
                actor = engine.actor_for_telegram(
                    sender.get("id"), chat.get("id"), private=chat.get("type") == "private"
                )
            except DomainError:
                actor = None
            if actor:
                state = engine.snapshot()
                member = state["members"][actor]
                actor_revision = member["revision"]
                language = member["language"]
                private = chat.get("type") == "private"
                command_guard = self._command_guard(
                    actor=actor,
                    actor_revision=actor_revision,
                    role=member["role"],
                    language=language,
                    telegram_id=sender.get("id"),
                    chat_id=chat.get("id"),
                    private=private,
                )
                command_guard(state)
                scoped_engine = _ScopedEngine(engine, command_guard)
                t = COPY.get(language, COPY["en"])
                response = None
                try:
                    if callback:
                        content = callback.get("data", "")
                        if not isinstance(content, str) or len(content.encode()) > 64:
                            raise DomainError("invalid_field")
                        parts = content.rsplit(":", 2)
                        if content.startswith(("ps:", "pr:")):
                            response = await route_polls(
                                scoped_engine,
                                actor,
                                content,
                                f"tg:{self.bot['id']}:{update_id}:action",
                                now,
                                private=chat.get("type") == "private",
                            )
                            parts = None
                        elif content.startswith("fr:"):
                            from . import routines

                            if chat.get("type") != "private":
                                raise DomainError("forbidden")
                            result = await scoped_engine.execute(
                                actor,
                                "routines.confirm",
                                routines.callback(content),
                                f"tg:{self.bot['id']}:{update_id}:action",
                                now,
                            )
                            response = routines.summary(result, language, True)
                            parts = None
                        if (
                            parts is not None
                            and len(parts) == 3
                            and parts[0] in {"fp", "fn"}
                            and parts[1] in {"confirm", "cancel"}
                        ):
                            response = await route(
                                scoped_engine,
                                actor,
                                f"/{'net' if parts[0] == 'fn' else ''}{parts[1]} {parts[2]}",
                                f"tg:{self.bot['id']}:{update_id}:action",
                                now,
                            )
                            parts = None
                        if parts is not None and (
                            len(parts) != 3 or not parts[0].startswith("fa:")
                        ):
                            raise DomainError("unknown_action")
                        if parts is not None:
                            result = await scoped_engine.execute(
                                actor,
                                "alarms.answer",
                                {
                                    "id": parts[0][3:],
                                    "nonce": parts[1],
                                    "answer": int(parts[2]),
                                },
                                f"tg:{self.bot['id']}:{update_id}:action",
                                now,
                            )
                            response = (
                                t["accepted"].format(stage=t[result["run"]["stage"]])
                                if result["accepted"]
                                else t["wrong"]
                            )
                    elif (content := addressed(message, self.bot, language=language)) is not None:
                        if message.get("text") or message.get("caption"):
                            observation_key = (
                                "command_received_at"
                                if content.startswith("/")
                                else "text_received_at"
                            )

                        async def slow(actor, content, operation_id, received, refs):
                            command_guard(engine.snapshot())
                            if not self.runtime.assistant:
                                return t["unknown"]
                            from ..assistant.jobs import Jobs
                            from .router import image_file_id

                            # Persist only Telegram's bounded file reference. Fetching bytes
                            # belongs to the worker so /ping and wake-up replies stay responsive.
                            attachment = image_file_id(message)

                            scoped_jobs = Jobs(
                                scoped_engine,
                                clock=dt_util.utcnow,
                                provider_scope=self._provider_scope,
                            )
                            msg_id = envelope.get("message_id") or message.get("message_id")
                            result = await scoped_jobs.enqueue(
                                actor,
                                content,
                                operation_id,
                                received,
                                refs,
                                bot_id=bot_id,
                                chat_id=chat["id"],
                                reply_to=msg_id,
                                quoted_text=reply_quote(
                                    scoped_engine.snapshot(), message, self.bot
                                ),
                                image_file_id=attachment,
                            )
                            command_guard(engine.snapshot())
                            return result

                        response = await self.photo_reports.enqueue(
                            scoped_engine,
                            actor,
                            message,
                            content,
                            f"tg:{bot_id}:{update_id}:action",
                            now,
                        )
                        if response is None:
                            response = await route_polls(
                                scoped_engine,
                                actor,
                                content,
                                f"tg:{bot_id}:{update_id}:action",
                                now,
                                private=chat.get("type") == "private",
                            )
                        if response is None:
                            response = await route(
                                scoped_engine,
                                actor,
                                content,
                                f"tg:{bot_id}:{update_id}:action",
                                now,
                                reply_refs(scoped_engine.snapshot(), message, self.bot),
                                fallback=slow,
                                private=chat.get("type") == "private",
                            )
                    command_guard(engine.snapshot())
                except (DomainError, ValueError) as err:
                    code = err.code if isinstance(err, DomainError) else "invalid_field"
                    if code == "backup_in_progress":
                        raise
                    # Codes are bounded and translatable; never echo raw provider errors.
                    response = t["error"].format(
                        error=ERRORS.get(language, ERRORS["en"]).get(code, code)
                    )
                if response:
                    command_guard(engine.snapshot())

                    def reply(ctx):
                        ctx.operation_id = f"tg:{bot_id}:{update_id}:reply"
                        # The reply is deduplicated by input update, even if a status
                        # report would render differently after an offset-save failure.
                        if any(
                            event["id"].startswith(ctx.operation_id + ":")
                            for event in ctx.state["outbox"].values()
                        ):
                            return
                        if isinstance(response, dict):
                            ctx.notify(
                                actor,
                                "telegram_poll_reply",
                                {
                                    "descriptor": response,
                                    "actor": actor,
                                    "actor_revision": actor_revision,
                                    "bot_id": bot_id,
                                    "chat_id": chat["id"],
                                    "reply_to": envelope.get("message_id"),
                                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                                },
                            )
                            return
                        processed = (
                            ctx.state["processed"]
                            .get(f"tg:{bot_id}:{update_id}:action", {})
                            .get("result", {})
                        )
                        ctx.notify(
                            actor,
                            "telegram_reply",
                            {
                                "text": response,
                                "private_context": isinstance(response, PersonalReply),
                                **(
                                    {"school_context": response.school_scope}
                                    if hasattr(response, "school_scope")
                                    else {}
                                ),
                                **(
                                    {"admission_context": response.scope}
                                    if isinstance(response, AdmissionReply)
                                    else {}
                                ),
                                "actor": actor,
                                "actor_revision": actor_revision,
                                "bot_id": bot_id,
                                "chat_id": chat["id"],
                                "reply_to": envelope.get("message_id"),
                                "network_plan_id": processed.get("id")
                                if "mode" in processed and processed.get("status") == "preview"
                                else None,
                                "refs": result_refs(
                                    ctx.state["processed"]
                                    .get(f"tg:{bot_id}:{update_id}:action", {})
                                    .get("result", {})
                                ),
                            },
                        )

                    await scoped_engine.background_update("telegram_reply", now, reply)
                    command_guard(engine.snapshot())
                    self.runtime.updated()
                if callback:
                    with suppress(DeliveryError):
                        command_guard(engine.snapshot())
                        await self.client.call(
                            "answerCallbackQuery", {"callback_query_id": callback["id"]}
                        )
                        command_guard(engine.snapshot())

        def advance(ctx):
            offsets = ctx.state["telegram"].setdefault("offsets", {})
            offsets[str(self.bot["id"])] = max(offsets.get(str(self.bot["id"]), -1), update_id + 1)
            if observation_key is not None:
                observations = ctx.state["telegram"].setdefault("observations", {})
                observed = observations.setdefault(str(bot_id), {})
                if observed.get("config_digest") != self._telegram_options_digest:
                    observed.clear()
                observed[observation_key] = now.isoformat()
                observed["config_digest"] = self._telegram_options_digest
                # Bot replacements must not grow this transport evidence forever.
                while len(observations) > 16:
                    oldest = next(key for key in observations if key != str(bot_id))
                    observations.pop(oldest)

        offset_engine = _ScopedEngine(engine, command_guard or self._manager_guard)
        await offset_engine.background_update("telegram_offset", now, advance)
