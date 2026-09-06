"""Atomic local commands: authorize, mutate a copy, persist, then publish."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime

from ..const import DEFAULT_MODULES, LANGUAGES, MODULES, PRIVILEGED, SCHEMA_VERSION
from ..network import plans as network_plans
from . import (
    alarms,
    court,
    delivery,
    household,
    members,
    proposals,
    settings,
    shopping,
    task_events,
    task_series,
    tasks,
)
from .context import Context
from .validation import DomainError, enum, fields, text, timestamp

HANDLERS = {
    "settings": settings.handle,
    "members": members.handle,
    "shopping": shopping.handle,
    "tasks": tasks.handle,
    "court": court.handle,
    "alarms": alarms.handle,
    "notifications": delivery.handle,
    "conversation": proposals.handle,
    "mikrotik": network_plans.handle,
}
BUCKETS = (
    "members",
    "shopping",
    "tasks",
    "task_series",
    "incidents",
    "court",
    "alarms",
    "alarm_runs",
    "routines",
    "calendar",
    "pantry",
    "school",
    "maintenance",
    "polls",
    "outbox",
    "processed",
    "sequences",
    "memory",
    "network",
    "alarm_outputs",
    "notification_rates",
    "enrollments",
    "telegram",
    "proposals",
    "assistant_jobs",
)


def new_state(
    owner_user_id: str,
    name: str,
    language: str = "en",
    modules: list[str] | None = None,
    *,
    timezone: str = "UTC",
    template: str = "manual",
) -> dict:
    owner_user_id = text(owner_user_id, "ha_user_id", 128)
    enum(language, LANGUAGES, "language")
    enabled = list(DEFAULT_MODULES) if modules is None else list(modules)
    if set(enabled) - set(MODULES):
        raise DomainError("invalid_field", "modules")
    state = {
        **{bucket: {} for bucket in BUCKETS},
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "audit": [],
        "settings": {
            "name": text(name, "name", 80),
            "language": language,
            "modules": enabled,
            "automatic_penalties": False,
            "daily_penalty_cap": 1,
            "timezone": household.timezone(timezone),
        },
        "members": {
            "owner": {
                "id": "owner",
                "name": household.NAMES[language]["owner"],
                "role": "owner",
                "language": language,
                "ha_user_id": owner_user_id,
                "aliases": [],
                "active": True,
                "revision": 1,
            }
        },
    }
    household.apply_template(state, template)
    return state


class Engine:
    """All state writes are serialized and survive a storage failure unchanged."""

    def __init__(self, state: dict, persist: Callable[[dict], Awaitable[None]]) -> None:
        if state.get("schema_version") != SCHEMA_VERSION:
            raise DomainError("unsupported_schema")
        self._state = deepcopy(state)
        self._state.setdefault("task_series", {})
        self._state.setdefault("incidents", {})
        self._state.setdefault("proposals", {})
        self._state.setdefault("assistant_jobs", {})
        self._persist = persist
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict:
        """Trusted persistence/migration access, never return directly to a channel."""
        return deepcopy(self._state)

    def actor_for_ha(self, user_id: str | None) -> str:
        if not user_id:
            raise DomainError("forbidden")
        for member in self._state["members"].values():
            if member.get("ha_user_id") == user_id and member.get("active", True):
                return member["id"]
        raise DomainError("forbidden")

    def actor_for_telegram(self, user_id: int, chat_id: int, *, private: bool) -> str:
        if type(user_id) is not int or type(chat_id) is not int:
            raise DomainError("forbidden")
        if private:
            if chat_id != user_id:
                raise DomainError("forbidden")
        elif self._state["telegram"].get("group_id") != chat_id:
            raise DomainError("forbidden")
        for member in self._state["members"].values():
            if member.get("telegram_id") == user_id and member.get("active", True):
                return member["id"]
        raise DomainError("forbidden")

    def view(self, actor_id: str) -> dict:
        """Return an authorized projection; never expose channel IDs or credentials."""
        actor = self._actor(actor_id)
        parent = actor["role"] in PRIVILEGED
        data = {
            "revision": self._state["revision"],
            "settings": self._state["settings"],
            "actor": actor_id,
            "role": actor["role"],
        }
        data["members"] = [
            {k: m[k] for k in ("id", "name", "role", "language", "active", "revision")}
            for m in self._state["members"].values()
        ]
        data["shopping"] = list(self._state["shopping"].values())
        for bucket, owner_field in (
            ("tasks", "assignee"),
            ("court", "member"),
            ("alarms", "member"),
            ("alarm_runs", "member"),
        ):
            data[bucket] = [
                alarms.public_run(record) if bucket == "alarm_runs" else record
                for record in self._state[bucket].values()
                if parent or record.get(owner_field) == actor_id
            ]
        if actor["role"] == "guest":
            data["shopping"] = []
        data["task_series"] = [
            record
            if parent
            else {
                key: value
                for key, value in record.items()
                if key not in {"occurrences", "cursor", "creator"}
            }
            for record in self._state["task_series"].values()
            if parent or actor_id in record["assignees"]
        ]
        data["proposals"] = [
            {k: record[k] for k in ("id", "status", "preview", "expires_at")}
            for record in self._state["proposals"].values()
            if record["actor"] == actor_id and record["status"] == "pending"
        ]
        data["learned_phrases"] = [
            {key: record[key] for key in ("id", "source", "canonical", "active", "revision")}
            for record in self._state["memory"].get("phrases", {}).values()
            if record["actor"] == actor_id
        ]
        if parent:
            data["network"] = {
                "inventory": self._state["network"].get("inventory"),
                "writable": self._state["network"].get("writable", False),
                "plans": [
                    network_plans.public(p)
                    for p in self._state["network"].get("plans", {}).values()
                ][-20:],
            }
            data["delivery_issues"] = [
                {k: event[k] for k in ("id", "recipient", "key", "state", "attempts", "created_at")}
                for event in self._state["outbox"].values()
                if event["state"] in {"uncertain", "failed", "awaiting_channel"}
            ][-100:]
            data["audit"] = [
                {
                    **event,
                    "result": {
                        k: v
                        for k, v in event["result"].items()
                        if k not in {"ha_user_id", "telegram_id", "aliases"}
                    },
                }
                for event in self._state["audit"][-100:]
            ]
        return deepcopy(data)

    def _actor(self, actor_id: str) -> dict:
        member = self._state["members"].get(actor_id)
        if member is None or not member.get("active", True):
            raise DomainError("forbidden")
        return member

    async def execute(
        self, actor_id: str, action: str, payload: dict, operation_id: str, now: datetime
    ) -> dict:
        text(operation_id, "operation_id", 180)
        timestamp(now, "now")
        if not isinstance(payload, dict):
            raise DomainError("invalid_field", "payload")
        # Enforce finite JSON and a bounded command before hashing or copying.
        try:
            encoded = json.dumps(
                [actor_id, action, payload], sort_keys=True, ensure_ascii=False, allow_nan=False
            )
        except (TypeError, ValueError):
            raise DomainError("invalid_field", "payload") from None
        if len(encoded) > 20000:
            raise DomainError("command_too_large")
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        async with self._lock:
            actor = self._actor(actor_id)
            prior = self._state["processed"].get(operation_id)
            if prior:
                if prior.get("role", actor["role"]) != actor["role"]:
                    raise DomainError("forbidden")
                if prior["fingerprint"] != fingerprint:
                    raise DomainError("idempotency_conflict")
                return deepcopy(prior["result"])
            working = deepcopy(self._state)
            ctx = Context(working, actor, now, operation_id)
            if action == "batch":
                fields(payload, {"commands"}, {"commands"})
                commands = payload["commands"]
                if not isinstance(commands, list) or not 1 <= len(commands) <= 20:
                    raise DomainError("invalid_field", "commands")
                result = {"items": []}
                for command in commands:
                    if not isinstance(command, dict):
                        raise DomainError("invalid_field", "commands")
                    fields(command, {"action", "payload"}, {"action", "payload"})
                    if not isinstance(command["action"], str) or command["action"].split(".")[
                        0
                    ] in {"members", "settings"}:
                        raise DomainError("invalid_field", "action")
                    result["items"].append(
                        self._dispatch(ctx, command["action"], command["payload"])
                    )
            else:
                result = self._dispatch(ctx, action, payload)
            alarms.cancel_disabled(ctx)
            # Freeze results: the journal must not alias later state mutations.
            result = deepcopy(result)
            working["revision"] += 1
            working["audit"].append(
                {
                    "id": operation_id,
                    "actor": actor_id,
                    "action": action,
                    "at": now.isoformat(),
                    "result": result,
                    "revision": working["revision"],
                }
            )
            working["processed"][operation_id] = {
                "fingerprint": fingerprint,
                "result": result,
                "role": actor["role"],
            }
            await self._persist(deepcopy(working))
            self._state = working
            return deepcopy(result)

    async def tick(self, now: datetime) -> bool:
        """Internal clock, not an exposed action or a forged privileged user.

        Persist the complete transition and outbox before any device operation.
        A tick with no transitions produces no write or ever-growing journal.
        """
        timestamp(now, "now")
        async with self._lock:
            working = deepcopy(self._state)
            ctx = Context(
                working, {"id": "system", "role": "system"}, now, f"clock:{now.isoformat()}"
            )
            alarms.tick(ctx)
            task_series.tick(ctx)
            task_events.tick(ctx)
            if working == self._state:
                return False
            working["revision"] += 1
            working["audit"].append(
                {
                    "id": ctx.operation_id,
                    "actor": "system",
                    "action": "clock",
                    "at": now.isoformat(),
                    "result": {"changed": True},
                    "revision": working["revision"],
                }
            )
            await self._persist(deepcopy(working))
            self._state = working
            return True

    async def system_update(self, kind: str, now: datetime, change: Callable) -> object:
        """Internal adapters may persist bounded state; channels cannot call this.

        The callback is synchronous and cannot perform network I/O inside the lock.
        This is used for durable effect intents and notification delivery receipts.
        """
        timestamp(now, "now")
        async with self._lock:
            working = deepcopy(self._state)
            ctx = Context(
                working, {"id": "system", "role": "system"}, now, f"{kind}:{now.isoformat()}"
            )
            result = change(ctx)
            if working != self._state:
                working["revision"] += 1
                await self._persist(deepcopy(working))
                self._state = working
            return deepcopy(result)

    @staticmethod
    def _dispatch(ctx: Context, action: str, payload: dict) -> dict:
        if not isinstance(action, str) or "." not in action or not isinstance(payload, dict):
            raise DomainError("unknown_action")
        module, command = action.split(".", 1)
        if module not in HANDLERS:
            raise DomainError("unknown_action")
        if (
            module not in {"members", "settings", "notifications"}
            and module not in ctx.state["settings"]["modules"]
        ):
            raise DomainError("module_disabled")
        return HANDLERS[module](ctx, command, payload)
