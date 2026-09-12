"""One-use Telegram enrollment, completed only by the owner in Home Assistant."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from hmac import compare_digest

from ..domain.validation import DomainError, text, timestamp


def owner(ctx, actor):
    member = ctx.state["members"].get(actor, {})
    if member.get("role") != "owner" or not member.get("active"):
        raise DomainError("forbidden")


class Enrollment:
    def __init__(self, engine):
        self.engine = engine

    async def issue(
        self, actor: str, kind: str, now: datetime, member_id=None, *, guard=None
    ) -> dict:
        code = secrets.token_urlsafe(12)
        digest = hashlib.sha256(code.encode()).hexdigest()

        def create(ctx):
            owner(ctx, actor)
            if kind not in {"group", "member"}:
                raise DomainError("invalid_field", "kind")
            if kind == "member":
                ctx.member(member_id)
            for item in ctx.state["enrollments"].values():
                if (
                    item["kind"] == kind
                    and item.get("member") == member_id
                    and item["state"] in {"issued", "captured"}
                ):
                    item["state"] = "superseded"
            record = {
                "id": digest[:24],
                "digest": digest,
                "kind": kind,
                "member": member_id,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=15)).isoformat(),
                "state": "issued",
                "issuer": actor,
            }
            ctx.state["enrollments"][record["id"]] = record
            return {"id": record["id"], "code": code, "expires_at": record["expires_at"]}

        if guard is None:
            return await self.engine.system_update("telegram_enroll_issue", now, create)
        return await self.engine.system_update("telegram_enroll_issue", now, create, guard=guard)

    async def capture(self, message: dict, username: str, now: datetime) -> bool:
        if message.get("forward_origin") or message.get("sender_chat"):
            return False
        sender = message.get("from", {})
        chat = message.get("chat", {})
        content = message.get("text", "")
        if not isinstance(content, str) or len(content) > 100 or sender.get("is_bot"):
            return False
        if type(sender.get("id")) is not int or type(chat.get("id")) is not int:
            return False
        parts = content.strip().split()
        if len(parts) != 2:
            return False
        command, code = parts
        base, _, suffix = command.partition("@")
        if suffix and suffix.casefold() != username.casefold():
            return False
        kind = "group" if base == "/family_setup" else "member" if base == "/start" else None
        if kind is None or len(code) != 16:
            return False
        if (kind == "group" and chat.get("type") not in {"group", "supergroup"}) or (
            kind == "member" and (chat.get("type") != "private" or chat["id"] != sender["id"])
        ):
            return False
        digest = hashlib.sha256(code.encode()).hexdigest()

        def accept(ctx):
            record = ctx.state["enrollments"].get(digest[:24])
            if (
                not record
                or not compare_digest(record["digest"], digest)
                or record["state"] != "issued"
            ):
                return False
            if now >= timestamp(record["expires_at"], "expires_at"):
                return False
            created = timestamp(record["created_at"], "created_at").timestamp()
            if not isinstance(message.get("date"), int) or message["date"] < int(created):
                return False
            if message["date"] > now.timestamp() + 60:
                return False
            if record["kind"] != kind:
                return False
            record.update(
                state="captured",
                candidate={
                    "chat_id": chat["id"],
                    "user_id": sender["id"],
                    "name": str(
                        chat.get("title") if kind == "group" else sender.get("first_name", "")
                    )[:200],
                    "username": str(sender.get("username", ""))[:80],
                },
            )
            return True

        return await self.engine.system_update("telegram_enroll_capture", now, accept)

    def status(self, actor: str, enrollment_id: str) -> dict:
        state = self.engine.snapshot()
        member = state["members"].get(actor, {})
        if member.get("role") != "owner" or not member.get("active"):
            raise DomainError("forbidden")
        record = state["enrollments"].get(enrollment_id)
        if not record:
            raise DomainError("not_found")
        return {
            key: record[key] for key in ("id", "state", "expires_at", "candidate") if key in record
        }

    async def confirm(self, actor: str, enrollment_id: str, now: datetime, *, guard=None) -> dict:
        text(enrollment_id, "enrollment", 24)

        def confirm(ctx):
            owner(ctx, actor)
            record = ctx.state["enrollments"].get(enrollment_id)
            if (
                not record
                or record["state"] != "captured"
                or now >= timestamp(record["expires_at"], "expires_at")
            ):
                raise DomainError("telegram_enrollment_expired")
            candidate = record["candidate"]
            if record["kind"] == "group":
                ctx.state["telegram"]["group_id"] = candidate["chat_id"]
                ctx.state["telegram"]["group_name"] = candidate["name"]
            else:
                member = ctx.member(record["member"])
                if any(
                    m.get("telegram_id") == candidate["user_id"] and m["id"] != member["id"]
                    for m in ctx.state["members"].values()
                ):
                    raise DomainError("duplicate_identity")
                member["telegram_id"] = candidate["user_id"]
                ctx.touch(member)
            record.update(state="confirmed", confirmed_at=now.isoformat(), confirmed_by=actor)
            ctx.state["audit"].append(
                {
                    "id": ctx.operation_id,
                    "actor": actor,
                    "action": "telegram.link",
                    "at": now.isoformat(),
                    "result": {"kind": record["kind"], "member": record["member"]},
                    "revision": ctx.state["revision"] + 1,
                }
            )
            return {"linked": True, "kind": record["kind"]}

        if guard is None:
            return await self.engine.system_update("telegram_enroll_confirm", now, confirm)
        return await self.engine.system_update("telegram_enroll_confirm", now, confirm, guard=guard)
