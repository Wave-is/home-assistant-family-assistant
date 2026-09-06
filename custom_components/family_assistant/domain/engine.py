"""Atomic local commands: authorize, mutate a copy, persist, then publish."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime

from ..const import DEFAULT_MODULES, LANGUAGES, MODULES, PRIVILEGED, SCHEMA_VERSION
from ..network import kid_plans
from ..network import plans as network_plans
from . import (
    alarms,
    court,
    court_weekly,
    delivery,
    dietary_profiles,
    family_calendar,
    household,
    members,
    pantry,
    proposals,
    rewards,
    routines,
    settings,
    shopping,
    shopping_series,
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
    "calendar": family_calendar.handle,
    "routines": routines.handle,
    "pantry": pantry.handle,
}
BUCKETS = (
    "members",
    "shopping",
    "shopping_series",
    "tasks",
    "task_series",
    "incidents",
    "court",
    "court_reports",
    "rewards",
    "reward_requests",
    "alarms",
    "alarm_runs",
    "routines",
    "routine_runs",
    "calendar",
    "pantry",
    "dietary_profiles",
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
            "pantry_expiry_reminders": False,
            "pantry_expiry_days": 3,
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
        self._state.setdefault("shopping_series", {})
        self._state.setdefault("incidents", {})
        self._state.setdefault("court_reports", {})
        self._state.setdefault("rewards", {})
        self._state.setdefault("reward_requests", {})
        self._state.setdefault("calendar", {})
        self._state.setdefault("routines", {})
        self._state.setdefault("routine_runs", {})
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

    def view(self, actor_id: str, *, now: datetime | None = None) -> dict:
        """Return an authorized projection; never expose channel IDs or credentials."""
        actor = self._actor(actor_id)
        parent = actor["role"] in PRIVILEGED
        data = {
            "revision": self._state["revision"],
            "settings": deepcopy(self._state["settings"]),
            "actor": actor_id,
            "role": actor["role"],
        }
        data["members"] = [
            {k: m[k] for k in ("id", "name", "role", "language", "active", "revision")}
            for m in self._state["members"].values()
        ]
        if not parent:
            data["settings"].pop("routines", None)
        data["shopping"] = [
            {**item, "merge_name": shopping.normalized_name(item["name"])}
            for item in self._state["shopping"].values()
        ]
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
        elif "court" in self._state["settings"]["modules"]:
            data["rewards"] = rewards.view(self._state, actor)
            data["court_summary"] = court_weekly.view(self._state, data["court"], now)
            if parent:
                data["court_config"] = court_weekly.configuration(self._state)
                data["court_reports"] = list(self._state["court_reports"].values())[-12:]
        data["shopping_series"] = (
            [
                {k: v for k, v in record.items() if k not in {"creator", "occurrences"}}
                for record in self._state["shopping_series"].values()
            ]
            if actor["role"] != "guest"
            else []
        )
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
        data["kid_control"] = kid_plans.view(self._state, actor_id, now)
        if actor["role"] != "guest" and "calendar" in self._state["settings"]["modules"]:
            data["calendar"] = family_calendar.view(self._state, actor, now)
        if actor["role"] != "guest" and "routines" in self._state["settings"]["modules"]:
            data["routines"] = routines.view(self._state, actor)
        if actor["role"] != "guest" and "pantry" in self._state["settings"]["modules"]:
            data["pantry"] = pantry.view(self._state, actor, now)
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
                self._replay_scope(actor_id, action, payload, prior["result"], now)
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
            routines.cancel_disabled(ctx)
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

    def _replay_scope(self, actor_id, action, payload, result, now):
        """A saved receipt never restores a disabled module or revoked scope."""
        if action == "batch":
            for command, item in zip(payload["commands"], result["items"], strict=True):
                self._replay_scope(actor_id, command["action"], command["payload"], item, now)
            return
        module = action.split(".", 1)[0]
        if (
            module not in {"members", "settings", "notifications"}
            and module not in self._state["settings"]["modules"]
        ):
            raise DomainError("module_disabled")
        if module == "routines":
            routines.check_replay(self._state, actor_id, action.split(".", 1)[1], result)
        elif action.startswith("pantry.dietary_"):
            dietary_profiles.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "dietary-replay"),
                action.split(".", 1)[1],
                payload,
            )
        elif action in {
            "pantry.suggestion_accept",
            "pantry.meal_shop_prepare",
            "pantry.meal_shop_accept",
        }:
            if "shopping" not in self._state["settings"]["modules"]:
                raise DomainError("module_disabled")
        elif module == "mikrotik":
            kid_control = action.startswith("mikrotik.kid_") and action not in {
                "mikrotik.kid_adopt",
                "mikrotik.kid_permission",
            }
            allowed = (
                kid_plans.can_manage(self._state, actor_id)
                if kid_control
                else self._state["members"][actor_id]["role"] == "owner"
            )
            if not allowed:
                raise DomainError("forbidden")

    async def tick(self, now: datetime, *, routine_observations: dict | None = None) -> bool:
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
            shopping_series.tick(ctx)
            pantry.tick(ctx)
            task_events.tick(ctx)
            court_weekly.tick(ctx)
            rewards.tick(ctx)
            family_calendar.tick(ctx)
            routines.tick(ctx, routine_observations)
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
