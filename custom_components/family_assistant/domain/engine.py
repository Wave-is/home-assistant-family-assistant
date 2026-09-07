"""Atomic local commands: authorize, mutate a copy, persist, then publish."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
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
    digest_settings,
    digests,
    family_calendar,
    household,
    maintenance,
    media,
    members,
    pantry,
    poll_reviews,
    polls,
    presence,
    proposals,
    rewards,
    routines,
    school,
    school_preparation,
    school_reminders,
    school_work,
    settings,
    shopping,
    shopping_series,
    task_access,
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
    "school": school.handle,
    "maintenance": maintenance.handle,
    "media": media.handle,
    "polls": polls.handle,
    "presence": presence.handle,
    "digests": digests.handle,
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
    "media",
    "polls",
    "poll_ballots",
    "poll_reviews",
    "presence",
    "digest_subscriptions",
    "digest_markers",
    "digest_retired",
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

_NO_BACKUP = object()


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
            "school_preparation_reminders": False,
            "school_preparation_days_before": 1,
            "school_preparation_time": "20:00",
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
        self._state.setdefault("media", {})
        self._state.setdefault("polls", {})
        self._state.setdefault("poll_ballots", {})
        self._state.setdefault("poll_reviews", {})
        self._state.setdefault("presence", {"bindings": {}, "subscriptions": {}})
        self._state.setdefault("digest_subscriptions", {})
        self._state.setdefault("digest_markers", {})
        self._state.setdefault("digest_retired", {})
        self._persist = persist
        self._lock = asyncio.Lock()
        # This process-local lease is deliberately absent from persisted state.
        # A restarted Engine is writable and cannot accept a token from its predecessor.
        self._backup_owner = _NO_BACKUP
        self._ended_backup_owner = _NO_BACKUP
        self._closed = False
        self._writable = asyncio.Event()
        self._writable.set()

    def _require_writable(self) -> None:
        if self._closed:
            raise DomainError("not_ready")
        if self._backup_owner is not _NO_BACKUP:
            raise DomainError("backup_in_progress")

    def _guard(self, guard: Callable[[dict], None] | None) -> None:
        """Run a synchronous guard against the latest state without exposing it to mutation."""
        if guard is None:
            return
        if not callable(guard):
            raise DomainError("invalid_field", "guard")
        result = guard(deepcopy(self._state))
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise DomainError("invalid_field", "guard")

    async def _commit(self, working: dict) -> None:
        """Settle persistence under cancellation, then publish exactly what reached disk."""
        task = asyncio.ensure_future(self._persist(deepcopy(working)))
        cancellation: asyncio.CancelledError | None = None
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError as error:
                if cancellation is None:
                    cancellation = error
                if task.done():
                    break
            except BaseException:
                # A persistence failure and caller cancellation may become ready
                # in the same loop turn. Cancellation remains the caller-visible
                # outcome, while task.exception() below consumes the store error.
                current = asyncio.current_task()
                if cancellation is not None or (current is not None and current.cancelling()):
                    cancellation = cancellation or asyncio.CancelledError()
                    break
                raise

        if task.cancelled():
            if cancellation is not None:
                raise cancellation
            await task

        failure = task.exception()
        if failure is None:
            self._state = working
        if cancellation is not None:
            raise cancellation
        if failure is not None:
            raise failure

    async def async_begin_backup(self) -> object:
        """Drain current persistence, then freeze new mutations under one opaque lease."""
        if self._closed:
            raise DomainError("not_ready")
        if self._backup_owner is not _NO_BACKUP:
            raise DomainError("conflict")
        async with self._lock:
            if self._closed:
                raise DomainError("not_ready")
            if self._backup_owner is not _NO_BACKUP:
                raise DomainError("conflict")
            token = object()
            self._backup_owner = token
            self._writable.clear()
            return token

    async def async_end_backup(self, token: object) -> None:
        """Release only the matching lease; repeating its release is harmless."""
        async with self._lock:
            if self._backup_owner is token:
                self._backup_owner = _NO_BACKUP
                self._ended_backup_owner = token
                self._writable.set()
                return
            if self._backup_owner is _NO_BACKUP and self._ended_backup_owner is token:
                return
            raise DomainError("conflict")

    async def async_wait_writable(self) -> None:
        """Let owned background work wait for backup without spinning or thawing it."""
        if self._closed:
            raise DomainError("not_ready")
        await self._writable.wait()
        if self._closed:
            raise DomainError("not_ready")

    async def async_close(self) -> None:
        """Permanently reject writes and wait for the current transaction to settle."""
        self._closed = True
        # A background update may be waiting for a backup lease that will never
        # make this Engine writable again. Wake it so it can fail with not_ready.
        self._writable.set()

        async def drain() -> None:
            async with self._lock:
                return

        task = asyncio.create_task(drain())
        cancellation: asyncio.CancelledError | None = None
        while True:
            try:
                await asyncio.shield(task)
                break
            except asyncio.CancelledError as error:
                if cancellation is None:
                    cancellation = error
                if task.done():
                    break
        if cancellation is not None:
            raise cancellation

    async def background_update(self, kind: str, now: datetime, change: Callable) -> dict:
        """Persist the same in-flight effect/receipt after backup, without redoing I/O.

        Only trusted adapters use this. User commands still reject immediately
        through execute/system_update; cancellation never releases a backup lease.
        The synchronous change callback runs against fresh state under its lock.
        """
        while True:
            await self.async_wait_writable()
            try:
                return await self.system_update(kind, now, change)
            except DomainError as error:
                if error.code != "backup_in_progress":
                    raise

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
                alarms.public_run(record)
                if bucket == "alarm_runs"
                else (
                    task_access.public_task(
                        record, parent=parent, state=self._state, actor=actor, now=now
                    )
                    if bucket == "tasks"
                    else record
                )
                for record in self._state[bucket].values()
                if parent or record.get(owner_field) == actor_id
                if bucket != "tasks"
                or not task_access.private_task(record)
                or task_access.may_view(self._state, actor, record)
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
            task_series.public_record(self._state, record, parent=parent)
            for record in self._state["task_series"].values()
            if parent
            or (
                actor_id in record["assignees"]
                and isinstance(record.get("assignee_revisions"), dict)
                and type(record["assignee_revisions"].get(actor_id)) is int
                and record.get("assignee_revisions", {}).get(actor_id) == actor["revision"]
            )
            if not maintenance.is_managed_series(record)
        ]
        data["proposals"] = (
            [
                projected
                for record in self._state["proposals"].values()
                if (projected := proposals.project(record, actor)) is not None
            ]
            if "conversation" in self._state["settings"]["modules"]
            else []
        )
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
        if (
            actor["role"] in {"owner", "parent", "child"}
            and "school" in self._state["settings"]["modules"]
        ):
            data["school"] = school.view(self._state, actor, now)
            data["school"].update(school_preparation.view(self._state, actor))
            data["school"].update(school_reminders.view(self._state, actor))
            data["school"]["homework"] = (
                [
                    task_access.public_task(
                        task, parent=parent, state=self._state, actor=actor, now=now
                    )
                    for task in self._state["tasks"].values()
                    if school_work.is_homework_task(task)
                    and task_access.may_view(self._state, actor, task)
                ]
                if "tasks" in self._state["settings"]["modules"]
                else []
            )
        if actor["role"] != "guest" and "maintenance" in self._state["settings"]["modules"]:
            data["maintenance"] = maintenance.view(self._state, actor)
        if actor["role"] != "guest" and "polls" in self._state["settings"]["modules"]:
            data["polls"] = polls.view(self._state, actor, now)
        if actor["role"] != "guest" and "digests" in self._state["settings"]["modules"]:
            data["digests"] = digests.view(self._state, actor)
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
        self,
        actor_id: str,
        action: str,
        payload: dict,
        operation_id: str,
        now: datetime,
        *,
        guard: Callable[[dict], None] | None = None,
    ) -> dict:
        self._require_writable()
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
            self._require_writable()
            self._guard(guard)
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
            await self._commit(working)
            return deepcopy(result)

    def _replay_scope(self, actor_id, action, payload, result, now):
        """A saved receipt never restores a disabled module or revoked scope."""
        if action == "batch":
            for command, item in zip(payload["commands"], result["items"], strict=True):
                self._replay_scope(actor_id, command["action"], command["payload"], item, now)
            return
        module = action.split(".", 1)[0]
        if (
            module not in {"members", "settings", "notifications", "media"}
            and module not in self._state["settings"]["modules"]
        ):
            raise DomainError("module_disabled")
        if action == "settings.digest_policy":
            digest_settings.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "digest-policy-replay"),
                payload,
                result,
            )
        elif action in {"conversation.confirm", "conversation.reject"}:
            proposals.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "proposal-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif module == "maintenance":
            maintenance.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "maintenance-replay"),
                action.split(".", 1)[1],
                payload,
            )
        elif module == "digests":
            digests.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "digest-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif module == "presence":
            presence.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "presence-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif module == "polls":
            polls.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "polls-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif module == "media":
            media.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "media-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif action == "school.preparation_reminder_access_set":
            school_reminders.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "school-reminder-replay"),
                "preparation_reminder_access_set",
                payload,
                result,
            )
        elif action.startswith("school.homework_"):
            school_work.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "school-work-replay"),
                action.split(".", 1)[1],
                payload,
            )
        elif action == "school.backpack_start":
            school_preparation.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "school-preparation-replay"),
                "backpack_start",
                payload,
                result,
            )
        elif action in {"tasks.series_save", "tasks.series_enable"}:
            task_series.authorize_replay(
                Context(self._state, self._actor(actor_id), now, "task-series-replay"),
                action.split(".", 1)[1],
                payload,
                result,
            )
        elif module == "tasks":
            task_access.authorize_replay(self._state, self._actor(actor_id), result)
        elif module == "routines":
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
        self._require_writable()
        timestamp(now, "now")
        async with self._lock:
            self._require_writable()
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
            school_reminders.tick(ctx)
            polls.tick(ctx)
            poll_reviews.prune(ctx)
            digests.tick(ctx)
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
            await self._commit(working)
            return True

    async def system_update(
        self,
        kind: str,
        now: datetime,
        change: Callable,
        *,
        guard: Callable[[dict], None] | None = None,
    ) -> object:
        """Internal adapters may persist bounded state; channels cannot call this.

        The callback is synchronous and cannot perform network I/O inside the lock.
        This is used for durable effect intents and notification delivery receipts.
        """
        self._require_writable()
        timestamp(now, "now")
        async with self._lock:
            self._require_writable()
            self._guard(guard)
            working = deepcopy(self._state)
            ctx = Context(
                working, {"id": "system", "role": "system"}, now, f"{kind}:{now.isoformat()}"
            )
            result = change(ctx)
            if working != self._state:
                working["revision"] += 1
                await self._commit(working)
            return deepcopy(result)

    @staticmethod
    def _dispatch(ctx: Context, action: str, payload: dict) -> dict:
        if not isinstance(action, str) or "." not in action or not isinstance(payload, dict):
            raise DomainError("unknown_action")
        module, command = action.split(".", 1)
        if module not in HANDLERS:
            raise DomainError("unknown_action")
        if (
            module not in {"members", "settings", "notifications", "media"}
            and module not in ctx.state["settings"]["modules"]
        ):
            raise DomainError("module_disabled")
        if action == "tasks.revise":
            task_id = payload.get("id")
            task = ctx.state["tasks"].get(task_id) if isinstance(task_id, str) else None
            if school_work.is_homework_task(task):
                raise DomainError("forbidden")
        return HANDLERS[module](ctx, command, payload)
