"""Scoped dashboard chat with durable, content-free retry context."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ..domain.validation import DomainError
from ..telegram.context import result_refs
from ..telegram.router import route
from .service import Assistant

MAX_REFS = 20
MAX_CONTEXTS = 1000
CONTEXT_TTL = timedelta(minutes=15)
# Hash-only tombstones are retained for a finite window. Domain receipts and
# proposals remain independently recognizable after pruning; a transient-only
# model operation may be interpreted again only after this documented window.
CONTEXT_RETENTION = timedelta(days=30)
TRANSIENT_TTL = 300.0
REQUEST_TIMEOUT = 110
MAX_ACTIVE = 8
MAX_ACTIVE_PER_ACTOR = 2


def _hash(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def conversation_digest(value: Any) -> str:
    """Canonical public provenance marker for the complete provider options."""
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise DomainError("chat_unavailable") from None
    return hashlib.sha256(encoded).hexdigest()


def _valid_refs(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value[:MAX_REFS] if isinstance(item, str) and 0 < len(item) <= 180]


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
        return parsed if parsed is not None and parsed.tzinfo is not None else None
    except ValueError:
        return None


class ScopedEngine:
    """Pass every mutation through the request's synchronous locked guard."""

    def __init__(
        self,
        engine: Any,
        guard: Callable[[dict], None],
        on_commit: Callable[[], None] | None = None,
    ) -> None:
        self._engine = engine
        self._guard = guard
        self._on_commit = on_commit

    def snapshot(self) -> dict:
        return self._engine.snapshot()

    def view(self, actor: str, *, now: datetime | None = None) -> dict:
        return self._engine.view(actor, now=now)

    def actor_for_ha(self, user_id: str | None) -> str:
        return self._engine.actor_for_ha(user_id)

    async def execute(self, actor, action, payload, operation_id, now):
        before = self._engine.snapshot().get("revision")
        try:
            return await self._engine.execute(
                actor, action, payload, operation_id, now, guard=self._guard
            )
        finally:
            self._notify_if_changed(before)

    async def system_update(self, kind, now, change):
        before = self._engine.snapshot().get("revision")
        try:
            return await self._engine.system_update(kind, now, change, guard=self._guard)
        finally:
            self._notify_if_changed(before)

    def _notify_if_changed(self, before: Any) -> None:
        if self._on_commit is not None and self._engine.snapshot().get("revision") != before:
            self._on_commit()


class ChatService:
    """Own dashboard chat work independently of optional model transport."""

    def __init__(self, *, clock=None) -> None:
        self._clock = clock or time.monotonic
        self._closed = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._task_actors: dict[str, str] = {}
        self._completed: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()
        self._active = 0
        self._actor_active: dict[str, int] = {}

    async def answer(
        self,
        *,
        runtime: Any,
        actor: str,
        actor_revision: int,
        content: str,
        operation_id: str,
        session_id: str,
        now: datetime,
        guard: Callable[[dict], None],
        scope_check: Callable[[], Any],
        on_commit: Callable[[], None] | None = None,
    ) -> str:
        """Route one request under immutable API and Engine scopes."""
        if (
            self._closed
            or self._active >= MAX_ACTIVE
            or self._actor_active.get(actor, 0) >= MAX_ACTIVE_PER_ACTOR
        ):
            raise DomainError("chat_busy" if not self._closed else "not_ready")
        # No await occurs before admission is reserved, so concurrent callers
        # cannot accumulate unbounded authority checks or provider workers.
        self._active += 1
        self._actor_active[actor] = self._actor_active.get(actor, 0) + 1
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await self._admitted_answer(
                    runtime=runtime,
                    actor=actor,
                    actor_revision=actor_revision,
                    content=content,
                    operation_id=operation_id,
                    session_id=session_id,
                    now=now,
                    guard=guard,
                    scope_check=scope_check,
                    on_commit=on_commit,
                )
        finally:
            self._active -= 1
            remaining = self._actor_active.get(actor, 1) - 1
            if remaining:
                self._actor_active[actor] = remaining
            else:
                self._actor_active.pop(actor, None)

    async def _admitted_answer(
        self,
        *,
        runtime,
        actor,
        actor_revision,
        content,
        operation_id,
        session_id,
        now,
        guard,
        scope_check,
        on_commit,
    ):
        await self._check(scope_check)
        input_hash = _hash(content)
        session_hash = _hash(actor, str(actor_revision), session_id)
        request_key = _hash(actor, str(actor_revision), session_hash, operation_id, input_hash)
        cached = None
        async with self._lock:
            if self._closed:
                raise DomainError("not_ready")
            cached = self._completed.get(request_key)
            task = self._tasks.get(request_key)
            if not (cached and cached[0] >= self._clock()) and task is None:
                actor_workers = sum(value == actor for value in self._task_actors.values())
                if len(self._tasks) >= MAX_ACTIVE or actor_workers >= MAX_ACTIVE_PER_ACTOR:
                    raise DomainError("chat_busy")
                assistant = getattr(runtime, "assistant", None)
                task = asyncio.create_task(
                    self._answer(
                        runtime,
                        assistant,
                        actor,
                        actor_revision,
                        content,
                        operation_id,
                        session_hash,
                        input_hash,
                        now,
                        guard,
                        scope_check,
                        on_commit,
                    )
                )
                self._tasks[request_key] = task
                self._task_actors[request_key] = actor
                task.add_done_callback(
                    lambda completed, key=request_key: self._task_done(key, completed)
                )
        if cached and cached[0] >= self._clock():
            await self._check(scope_check)
            return cached[1]
        reply = await asyncio.shield(task)
        await self._check(scope_check)
        return reply

    async def _answer(
        self,
        runtime,
        assistant,
        actor,
        actor_revision,
        content,
        operation_id,
        session_hash,
        input_hash,
        now,
        guard,
        scope_check,
        on_commit,
    ) -> str:
        engine = ScopedEngine(runtime.engine, guard, on_commit)
        context_free = self._context_free(content)
        refs = ()
        if not context_free:
            refs = await self._freeze_context(
                engine,
                actor,
                actor_revision,
                operation_id,
                session_hash,
                input_hash,
                now,
            )
        await self._check(scope_check)

        async def fallback(
            selected_actor,
            selected_content,
            selected_operation,
            selected_now,
            selected_refs,
        ):
            cascade = getattr(assistant, "cascade", None)
            if assistant is None or cascade is None:
                raise DomainError("provider_not_configured")
            scoped = Assistant(engine, cascade, getattr(assistant, "search", None))
            return await scoped.respond(
                selected_actor,
                selected_content,
                selected_operation,
                selected_now,
                selected_refs,
                scope_check=scope_check,
            )

        reply = await route(
            engine,
            actor,
            content,
            operation_id,
            now,
            refs,
            fallback=fallback,
        )
        await self._check(scope_check)
        if not context_free:
            await self._save_refs(engine, actor, actor_revision, session_hash, operation_id, now)
        await self._check(scope_check)
        return reply

    async def _freeze_context(
        self, engine, actor, actor_revision, operation_id, session_hash, input_hash, now
    ) -> tuple[str, ...]:
        operation_key = _hash(actor, str(actor_revision), operation_id)

        def freeze(ctx):
            memory = ctx.state.setdefault("memory", {})
            # Pre-scoped dashboard refs had no member epoch or operation snapshot.
            # Never adopt them into this stricter namespace.
            memory.pop("dashboard_refs", None)
            bucket = memory.setdefault("dashboard_chat", {})
            sessions = bucket.setdefault("sessions", {})
            operations = bucket.setdefault("operations", {})
            cutoff = now - CONTEXT_RETENTION
            for key, row in list(operations.items()):
                created = _timestamp(row.get("created_at")) if isinstance(row, dict) else None
                if created is None or created < cutoff:
                    operations.pop(key, None)
            for key, session in list(sessions.items()):
                updated = (
                    _timestamp(session.get("updated_at")) if isinstance(session, dict) else None
                )
                if updated is None or updated > now or now - updated > CONTEXT_TTL:
                    sessions.pop(key, None)
            row = operations.get(operation_key)
            if row is not None:
                if not isinstance(row, dict) or any(
                    (
                        row.get("actor") != actor,
                        row.get("actor_revision") != actor_revision,
                        row.get("session") != session_hash,
                        row.get("input_hash") != input_hash,
                    )
                ):
                    raise DomainError("idempotency_conflict")
                expires = _timestamp(row.get("expires_at"))
                if expires is None or now > expires:
                    row["refs"] = []
                    return {"error": "chat_context_expired"}
                return tuple(_valid_refs(row.get("refs")))
            known = operation_id in ctx.state.get("processed", {}) or operation_id in ctx.state.get(
                "telegram", {}
            ).get("plans", {})
            proposal_id = "P" + hashlib.sha256(operation_id.encode()).hexdigest()[:20]
            known = known or proposal_id in ctx.state.get("proposals", {})
            if known:
                raise DomainError("chat_context_expired")
            if len(operations) >= MAX_CONTEXTS:
                raise DomainError("chat_context_full")
            session = sessions.get(session_hash)
            refs = _valid_refs(session.get("refs")) if isinstance(session, dict) else []
            if session is None and len(sessions) >= MAX_CONTEXTS:
                raise DomainError("chat_context_full")
            sessions[session_hash] = {
                "actor": actor,
                "actor_revision": actor_revision,
                # This request keeps its frozen refs below, but a concurrent
                # follow-up cannot confirm an older preview while a new turn
                # is still running or after the new turn failed.
                "refs": [],
                "updated_at": now.isoformat(),
                "latest_operation": operation_key,
            }
            operations[operation_key] = {
                "actor": actor,
                "actor_revision": actor_revision,
                "session": session_hash,
                "input_hash": input_hash,
                "refs": refs,
                "created_at": now.isoformat(),
                "expires_at": (now + CONTEXT_TTL).isoformat(),
            }
            return tuple(refs)

        result = await engine.system_update("dashboard_chat_context", now, freeze)
        if isinstance(result, dict) and result.get("error") == "chat_context_expired":
            raise DomainError("chat_context_expired")
        return result

    async def _save_refs(self, engine, actor, actor_revision, session_hash, operation_id, now):
        def save(ctx):
            result = ctx.state.get("processed", {}).get(operation_id, {}).get("result")
            refs = _valid_refs(result_refs(result)) if isinstance(result, dict) else []
            if not isinstance(result, dict):
                proposal_id = "P" + hashlib.sha256(operation_id.encode()).hexdigest()[:20]
                proposal = ctx.state.get("proposals", {}).get(proposal_id, {})
                if (
                    proposal.get("actor") == actor
                    and proposal.get("actor_revision") == actor_revision
                    and proposal.get("status") == "pending"
                ):
                    refs = [proposal_id]
            bucket = ctx.state.setdefault("memory", {}).setdefault("dashboard_chat", {})
            session = bucket.setdefault("sessions", {}).get(session_hash)
            if (
                isinstance(session, dict)
                and session.get("actor") == actor
                and session.get("actor_revision") == actor_revision
                and session.get("latest_operation")
                == _hash(actor, str(actor_revision), operation_id)
            ):
                session["refs"] = refs
                session["updated_at"] = now.isoformat()

        await engine.system_update("dashboard_chat_refs", now, save)

    @staticmethod
    def _context_free(content: str) -> bool:
        normalized = content.casefold().strip(" .?!🙂")
        return bool(
            normalized
            in {
                "/ping",
                "ping",
                "alive",
                "here",
                "тут",
                "жив",
                "живой",
                "живий",
                "ты тут",
                "ти тут",
                "/start",
                "/help",
                "help",
                "помощь",
                "допомога",
            }
            or re.fullmatch(
                r"/(?:shopping|tasks|stats|week|alarms|rewards|wallet|calendar)", normalized
            )
        )

    async def _check(self, scope_check):
        if self._closed:
            raise DomainError("not_ready")
        result = scope_check()
        if inspect.isawaitable(result):
            await result
        if self._closed:
            raise DomainError("not_ready")

    def _trim_completed(self):
        current = self._clock()
        self._completed = {
            key: value for key, value in self._completed.items() if value[0] >= current
        }
        if len(self._completed) > 128:
            self._completed = dict(
                sorted(self._completed.items(), key=lambda item: item[1][0], reverse=True)[:128]
            )

    def _task_done(self, request_key: str, task: asyncio.Task) -> None:
        if self._tasks.get(request_key) is not task:
            return
        self._tasks.pop(request_key, None)
        self._task_actors.pop(request_key, None)
        if self._closed or task.cancelled():
            return
        try:
            reply = task.result()
        except Exception:
            return
        self._completed[request_key] = (self._clock() + TRANSIENT_TTL, reply)
        self._trim_completed()

    def close(self) -> None:
        self._closed = True
        self._completed.clear()
        for task in tuple(self._tasks.values()):
            task.cancel()

    async def async_stop(self) -> None:
        self.close()
        tasks = tuple(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._task_actors.clear()


__all__ = ["ChatService", "ScopedEngine", "conversation_digest"]
