"""Durable slow-command inbox; independent of ping, polling and alarm answers."""

from collections.abc import Callable
from datetime import datetime, timedelta

from ..domain.validation import DomainError, timestamp
from ..telegram.context import result_refs
from .language import COPY


class Jobs:
    def __init__(self, engine, *, clock: Callable[[], datetime] | None = None):
        self.engine = engine
        self.clock = clock

    def _now(self, fallback):
        return timestamp(self.clock() if self.clock is not None else fallback, "now")

    @staticmethod
    def _binding(state, actor, telegram_id, chat_id):
        if not isinstance(actor, str) or type(telegram_id) is not int or type(chat_id) is not int:
            return None
        if (chat_id > 0 and chat_id != telegram_id) or (
            chat_id <= 0 and state["telegram"].get("group_id") != chat_id
        ):
            return None
        member = state["members"].get(actor)
        if (
            not isinstance(member, dict)
            or member.get("active") is not True
            or member.get("telegram_id") != telegram_id
        ):
            return None
        return member

    @classmethod
    def _authority_error(cls, state, job, now):
        if "conversation" not in state["settings"]["modules"]:
            return "module_disabled"
        if not isinstance(job, dict):
            return "forbidden"
        revision = job.get("member_revision")
        member = cls._binding(state, job.get("actor"), job.get("telegram_id"), job.get("chat_id"))
        if (
            member is None
            or type(revision) is not int
            or revision < 1
            or member.get("revision") != revision
            or member.get("role") != job.get("role")
        ):
            # Jobs written before member_revision was introduced fail closed.
            return "forbidden"
        if now >= timestamp(job.get("expires_at"), "expires_at"):
            return "assistant_job_expired"
        return None

    @staticmethod
    def _same_job(selected, stored):
        if not isinstance(selected, dict):
            return False
        return all(
            selected.get(key) == stored.get(key)
            for key in (
                "id",
                "actor",
                "member_revision",
                "role",
                "telegram_id",
                "language",
                "content",
                "quoted_text",
                "refs",
                "bot_id",
                "chat_id",
                "reply_to",
                "created_at",
                "expires_at",
            )
        )

    async def enqueue(
        self, actor, content, operation_id, now, refs, *, bot_id, chat_id, reply_to, quoted_text=""
    ):
        before = self.engine.snapshot()
        selected = before["members"].get(actor) if isinstance(actor, str) else None
        telegram_id = selected.get("telegram_id") if isinstance(selected, dict) else None
        member_revision = selected.get("revision") if isinstance(selected, dict) else None
        role = selected.get("role") if isinstance(selected, dict) else None

        def save(ctx):
            if "conversation" not in ctx.state["settings"]["modules"]:
                raise DomainError("module_disabled")
            member = self._binding(ctx.state, actor, telegram_id, chat_id)
            if (
                member is None
                or type(member_revision) is not int
                or member_revision < 1
                or member.get("revision") != member_revision
                or member.get("role") != role
            ):
                raise DomainError("forbidden")
            jobs = ctx.state["assistant_jobs"]
            if operation_id in jobs:
                prior = jobs[operation_id]
                if (prior["actor"], prior["content"], prior["chat_id"], prior["bot_id"]) != (
                    actor,
                    content,
                    chat_id,
                    bot_id,
                ):
                    raise DomainError("idempotency_conflict")
                return member["language"]
            pending = [
                j
                for j in jobs.values()
                if j["status"] == "pending" and timestamp(j["expires_at"], "expires_at") > ctx.now
            ]
            if len(pending) >= 20 or sum(j["actor"] == actor for j in pending) >= 3:
                raise DomainError("assistant_busy")
            jobs[operation_id] = {
                "id": operation_id,
                "actor": actor,
                "member_revision": member_revision,
                "role": role,
                "telegram_id": telegram_id,
                "language": member["language"],
                "content": content,
                "quoted_text": quoted_text[:2000] if isinstance(quoted_text, str) else "",
                "refs": list(refs),
                "bot_id": bot_id,
                "chat_id": chat_id,
                "reply_to": reply_to,
                "status": "pending",
                "created_at": ctx.now.isoformat(),
                "expires_at": (ctx.now + timedelta(minutes=5)).isoformat(),
            }
            return member["language"]

        language = await self.engine.system_update("assistant_queued", now, save)
        return COPY[language]["queued"]

    def next(self, bot_id):
        return next(
            (
                j
                for j in self.engine.snapshot()["assistant_jobs"].values()
                if j["status"] == "pending" and j["bot_id"] == bot_id
            ),
            None,
        )

    def authorize(self, job, now):
        current = self.engine.snapshot()
        stored = current["assistant_jobs"].get(job.get("id")) if isinstance(job, dict) else None
        if stored is None or stored.get("status") != "pending" or not self._same_job(job, stored):
            raise DomainError("forbidden")
        if error := self._authority_error(current, stored, self._now(now)):
            raise DomainError(error)
        return stored["actor"]

    async def finish(self, job, response, now, *, cancelled=False):
        def save(ctx):
            ctx.now = self._now(ctx.now)
            stored = (
                ctx.state["assistant_jobs"].get(job.get("id")) if isinstance(job, dict) else None
            )
            if stored is None:
                return
            if stored["status"] != "pending":
                return
            stale = (
                cancelled
                or not self._same_job(job, stored)
                or self._authority_error(ctx.state, stored, ctx.now) is not None
            )
            stored.update(
                status="cancelled" if stale else "complete", finished_at=ctx.now.isoformat()
            )
            if not stale:
                ctx.operation_id = stored["id"] + ":model-result"
                ctx.notify(
                    stored["actor"],
                    "telegram_reply",
                    {
                        "text": response,
                        "actor": stored["actor"],
                        "actor_revision": stored["member_revision"],
                        "bot_id": stored["bot_id"],
                        "chat_id": stored["chat_id"],
                        "reply_to": stored["reply_to"],
                        "expires_at": stored["expires_at"],
                        "proposal_id": next(
                            (
                                p["id"]
                                for p in ctx.state["proposals"].values()
                                if p.get("operation_id") == stored["id"]
                            ),
                            None,
                        ),
                        "refs": result_refs(
                            ctx.state["processed"].get(stored["id"], {}).get("result", {})
                        ),
                    },
                )

        await self.engine.background_update("assistant_finished", now, save)
