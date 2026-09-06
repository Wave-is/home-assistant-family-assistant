"""Optional model inference yields a read, a reply, or an expiring command preview."""

import asyncio
import hashlib
import json
import re
from datetime import timedelta

from ..domain.engine import Engine
from ..domain.validation import DomainError
from ..telegram.presentation import summary
from . import plans
from .language import COPY


class Assistant:
    def __init__(self, engine, cascade, search=None):
        self.engine, self.cascade, self.search = engine, cascade, search

    async def respond(self, actor, content, operation_id, now, refs=(), *, quoted_text=""):
        view = self.engine.view(actor)
        if "conversation" not in view["settings"]["modules"]:
            raise DomainError("module_disabled")
        language = next(m["language"] for m in view["members"] if m["id"] == actor)
        t = COPY[language]
        proposal_id = "P" + hashlib.sha256(operation_id.encode()).hexdigest()[:20]
        existing = self.engine.snapshot()["proposals"].get(proposal_id)
        if existing:
            if existing["actor"] != actor:
                raise DomainError("forbidden")
            if existing.get("source_hash") != hashlib.sha256(content.encode()).hexdigest():
                raise DomainError("idempotency_conflict")
            return t["preview"].format(preview=existing["preview"], id=proposal_id)
        async with asyncio.timeout(100):
            value = await self.cascade.generate(
                plans.messages(view, content, refs, now, quoted_text=quoted_text),
                plans.SCHEMA,
                plans.validate,
            )
            # A role or identity can be revoked while the provider was answering.
            current = self.engine.view(actor)
            if current["role"] != view["role"]:
                raise DomainError("forbidden")
            if value["kind"] == "commands":
                return await self._propose(
                    actor, content, operation_id, proposal_id, value, view, now, t
                )
            if value["kind"] == "read":
                from ..telegram.router import route

                command = {
                    "court": "/stats",
                    "tasks": "/tasks",
                    "shopping": "/shopping",
                    "alarms": "/alarms",
                }[value["topic"]]
                return await route(self.engine, actor, command, operation_id, now)
            if value["kind"] == "search":
                return await self._search(current, content, value, language, now, t)
            # Do not forward invented model links as verified sources.
            reply = re.sub(r"https?://\S+", "[unverified link]", value["text"])
            return t["model"].format(text=reply)

    async def _search(self, view, content, value, language, now, t):
        if self.search is None:
            raise DomainError("search_not_configured")
        query = value["query"]
        # The model may not exfiltrate anything from its family context into a query.
        if query.casefold() not in content.casefold():
            raise DomainError("search_query_not_grounded")
        for member in view["members"]:
            if re.search(rf"(?<!\w){re.escape(member['name'])}(?!\w)", query, re.I):
                raise DomainError("search_query_not_grounded")
        if re.search(r"(?:[TSACP]\d{4,}|https?://|@|\b\d{1,3}(?:\.\d{1,3}){3}\b)", query, re.I):
            raise DomainError("search_query_not_grounded")
        results = await self.search.query(query, language, child=view["role"] in {"child", "guest"})
        if not results:
            return t["no_sources"]
        # Search is terminal/read-only. Retrieved instructions cannot reach a mutation path.
        empty_view = {**view, **{bucket: [] for bucket in plans.READS}}
        value = await self.cascade.generate(
            plans.messages(empty_view, content, (), now, evidence=results),
            {
                "type": "object",
                "properties": {"kind": {"const": "answer"}, "text": {"type": "string"}},
                "required": ["kind", "text"],
                "additionalProperties": False,
            },
            self._answer_only,
        )
        reply = re.sub(r"https?://\S+", "", value["text"])
        sources = "\n".join(
            f"{index}. {r['title']}\n{r['url']}" for index, r in enumerate(results, 1)
        )
        return f"{reply[:2200]}\n\n{t['sources']}\n{sources}"[:3900]

    @staticmethod
    def _answer_only(value):
        result = plans.validate(value)
        if result["kind"] != "answer":
            raise DomainError("provider_bad_response")
        return result

    async def _propose(self, actor, content, operation_id, proposal_id, value, view, now, t):
        commands = plans.materialize(value, view, content, now)
        signature = hashlib.sha256(
            json.dumps([actor, content, commands], sort_keys=True).encode()
        ).hexdigest()

        async def discard(_state):
            pass

        preview_engine = Engine(self.engine.snapshot(), discard)
        result = await preview_engine.execute(
            actor, "batch", {"commands": commands}, operation_id, now
        )
        language = next(m["language"] for m in view["members"] if m["id"] == actor)
        preview = "\n".join(summary(item, view, language) for item in result["items"])[:2200]

        def save(ctx):
            member = ctx.state["members"].get(actor, {})
            if not member.get("active") or member.get("role") != view["role"]:
                raise DomainError("forbidden")
            prior = ctx.state["proposals"].get(proposal_id)
            if prior and prior.get("signature") != signature:
                raise DomainError("idempotency_conflict")
            ctx.state["proposals"].setdefault(
                proposal_id,
                {
                    "id": proposal_id,
                    "operation_id": operation_id,
                    "source_hash": hashlib.sha256(content.encode()).hexdigest(),
                    "signature": signature,
                    "actor": actor,
                    "role": view["role"],
                    "commands": commands,
                    "preview": preview,
                    "status": "pending",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                    "revision": 1,
                },
            )

        await self.engine.system_update("model_proposal", now, save)
        return t["preview"].format(preview=preview, id=proposal_id)
