"""Durable slow-command inbox; independent of ping, polling and alarm answers."""

from datetime import timedelta

from ..domain.validation import DomainError, timestamp
from ..telegram.context import result_refs
from .language import COPY


class Jobs:
    def __init__(self, engine):
        self.engine = engine

    async def enqueue(
        self, actor, content, operation_id, now, refs, *, bot_id, chat_id, reply_to, quoted_text=""
    ):
        view = self.engine.view(actor)
        telegram_id = self.engine.snapshot()["members"][actor].get("telegram_id")
        if type(telegram_id) is not int:
            raise DomainError("forbidden")
        if "conversation" not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        language = next(m["language"] for m in view["members"] if m["id"] == actor)

        def save(ctx):
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
                return
            pending = [
                j
                for j in jobs.values()
                if j["status"] == "pending" and timestamp(j["expires_at"], "expires_at") > now
            ]
            if len(pending) >= 20 or sum(j["actor"] == actor for j in pending) >= 3:
                raise DomainError("assistant_busy")
            jobs[operation_id] = {
                "id": operation_id,
                "actor": actor,
                "role": view["role"],
                "telegram_id": telegram_id,
                "language": language,
                "content": content,
                "quoted_text": quoted_text[:2000] if isinstance(quoted_text, str) else "",
                "refs": list(refs),
                "bot_id": bot_id,
                "chat_id": chat_id,
                "reply_to": reply_to,
                "status": "pending",
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
            }

        await self.engine.system_update("assistant_queued", now, save)
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
        actor = self.engine.actor_for_telegram(
            job["telegram_id"],
            job["chat_id"],
            private=job["chat_id"] > 0,
        )
        if actor != job["actor"] or self.engine.view(actor)["role"] != job["role"]:
            raise DomainError("forbidden")
        if now >= timestamp(job["expires_at"], "expires_at"):
            raise DomainError("assistant_job_expired")
        return actor

    async def finish(self, job, response, now, *, cancelled=False):
        def save(ctx):
            stored = ctx.state["assistant_jobs"][job["id"]]
            if stored["status"] != "pending":
                return
            stored.update(
                status="cancelled" if cancelled else "complete", finished_at=now.isoformat()
            )
            if not cancelled:
                ctx.operation_id = job["id"] + ":model-result"
                ctx.notify(
                    job["actor"],
                    "telegram_reply",
                    {
                        "text": response,
                        "actor": job["actor"],
                        "bot_id": job["bot_id"],
                        "chat_id": job["chat_id"],
                        "reply_to": job["reply_to"],
                        "proposal_id": next(
                            (
                                p["id"]
                                for p in ctx.state["proposals"].values()
                                if p.get("operation_id") == job["id"]
                            ),
                            None,
                        ),
                        "refs": result_refs(
                            ctx.state["processed"].get(job["id"], {}).get("result", {})
                        ),
                    },
                )

        await self.engine.system_update("assistant_finished", now, save)
