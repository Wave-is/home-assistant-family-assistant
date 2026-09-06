"""One poller per configured bot, isolated from the deterministic HA clock."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..domain.validation import DomainError
from ..notifications import DeliveryError, Notifications
from .context import reply_refs, result_refs
from .enrollment import Enrollment
from .errors import ERRORS
from .messages import render, targets
from .router import COPY, addressed, route


class TelegramManager:
    def __init__(self, hass, entry, runtime, client, bot):
        self.hass, self.entry, self.runtime = hass, entry, runtime
        self.client, self.bot = client, bot
        self.enrollment = Enrollment(runtime.engine)
        self.notifications = Notifications(runtime.engine, self._targets, self._send_notification)
        self._tasks = []
        self._stopped = False
        from ..assistant.jobs import Jobs

        self.jobs = Jobs(runtime.engine)

    def _targets(self, event, state):
        if event["key"] == "telegram_reply" and event["data"].get("bot_id") != self.bot["id"]:
            return []
        return [{**target, "bot_id": self.bot["id"]} for target in targets(event, state)]

    def start(self):
        self._tasks = [
            self.hass.async_create_background_task(
                self._poll(), "Family Assistant Telegram polling"
            ),
            self.hass.async_create_background_task(
                self._outbox(), "Family Assistant Telegram outbox"
            ),
            self.hass.async_create_background_task(
                self._conversations(), "Family Assistant conversation inbox"
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

    async def _poll(self):
        backoff = 5
        while not self._stopped:
            try:
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
            "sendMessage", render(event, target, self.runtime.engine.snapshot())
        )
        return str(result["message_id"])

    async def _conversations(self):
        while not self._stopped:
            try:
                if (job := self.jobs.next(self.bot["id"])) is not None:
                    cancelled = False
                    try:
                        actor = self.jobs.authorize(job, dt_util.utcnow())
                        if not self.runtime.assistant:
                            raise DomainError("provider_not_configured")
                        response = await self.runtime.assistant.respond(
                            actor,
                            job["content"],
                            job["id"],
                            dt_util.parse_datetime(job["created_at"]),
                            job["refs"],
                            quoted_text=job.get("quoted_text", ""),
                        )
                        self.jobs.authorize(job, dt_util.utcnow())
                    except (DomainError, TimeoutError) as err:
                        code = err.code if isinstance(err, DomainError) else "provider_timeout"
                        cancelled = code == "forbidden"
                        response = COPY[job["language"]]["error"].format(
                            error=ERRORS[job["language"]].get(code, code)
                        )
                    await self.jobs.finish(job, response, dt_util.utcnow(), cancelled=cancelled)
                    self.runtime.updated()
            except OSError:
                self.runtime.health["conversation"] = "storage_error"
            await asyncio.sleep(1)

    async def process(self, update):
        if not isinstance(update, dict):
            return
        update_id = update.get("update_id")
        if type(update_id) is not int:
            return
        engine = self.runtime.engine
        offset = engine.snapshot()["telegram"].get("offsets", {}).get(str(self.bot["id"]), -1)
        if update_id < offset:
            return
        now = dt_util.utcnow()
        message = update.get("message")
        callback = update.get("callback_query")
        captured = message and await self.enrollment.capture(message, self.bot["username"], now)
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
                language = next(
                    m["language"] for m in engine.view(actor)["members"] if m["id"] == actor
                )
                t = COPY.get(language, COPY["en"])
                response = None
                try:
                    if callback:
                        content = callback.get("data", "")
                        if not isinstance(content, str) or len(content.encode()) > 64:
                            raise DomainError("invalid_field")
                        parts = content.rsplit(":", 2)
                        if content.startswith("fr:"):
                            from . import routines

                            if chat.get("type") != "private":
                                raise DomainError("forbidden")
                            result = await engine.execute(
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
                                engine,
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
                            result = await engine.execute(
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
                    elif (content := addressed(message, self.bot)) is not None:

                        async def slow(actor, content, operation_id, received, refs):
                            if not self.runtime.assistant:
                                return t["unknown"]
                            return await self.jobs.enqueue(
                                actor,
                                content,
                                operation_id,
                                received,
                                refs,
                                bot_id=self.bot["id"],
                                chat_id=chat["id"],
                                reply_to=envelope.get("message_id"),
                                quoted_text=message.get("reply_to_message", {}).get("text", ""),
                            )

                        response = await route(
                            engine,
                            actor,
                            content,
                            f"tg:{self.bot['id']}:{update_id}:action",
                            now,
                            reply_refs(engine.snapshot(), message, self.bot),
                            fallback=slow,
                            private=chat.get("type") == "private",
                        )
                except (DomainError, ValueError) as err:
                    code = err.code if isinstance(err, DomainError) else "invalid_field"
                    # Codes are bounded and translatable; never echo raw provider errors.
                    response = t["error"].format(
                        error=ERRORS.get(language, ERRORS["en"]).get(code, code)
                    )
                if response:

                    def reply(ctx):
                        ctx.operation_id = f"tg:{self.bot['id']}:{update_id}:reply"
                        # The reply is deduplicated by input update, even if a status
                        # report would render differently after an offset-save failure.
                        if any(
                            event["id"].startswith(ctx.operation_id + ":")
                            for event in ctx.state["outbox"].values()
                        ):
                            return
                        processed = (
                            ctx.state["processed"]
                            .get(f"tg:{self.bot['id']}:{update_id}:action", {})
                            .get("result", {})
                        )
                        ctx.notify(
                            actor,
                            "telegram_reply",
                            {
                                "text": response,
                                "actor": actor,
                                "bot_id": self.bot["id"],
                                "chat_id": chat["id"],
                                "reply_to": envelope.get("message_id"),
                                "network_plan_id": processed.get("id")
                                if "mode" in processed and processed.get("status") == "preview"
                                else None,
                                "refs": result_refs(
                                    ctx.state["processed"]
                                    .get(f"tg:{self.bot['id']}:{update_id}:action", {})
                                    .get("result", {})
                                ),
                            },
                        )

                    await engine.system_update("telegram_reply", now, reply)
                    self.runtime.updated()
                if callback:
                    with suppress(DeliveryError):
                        await self.client.call(
                            "answerCallbackQuery", {"callback_query_id": callback["id"]}
                        )

        def advance(ctx):
            offsets = ctx.state["telegram"].setdefault("offsets", {})
            offsets[str(self.bot["id"])] = max(offsets.get(str(self.bot["id"]), -1), update_id + 1)

        await engine.system_update("telegram_offset", now, advance)
