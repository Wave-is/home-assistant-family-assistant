"""Durable notification delivery with explicit uncertain outcomes.

Telegram sendMessage has no idempotency key. A timeout after sending cannot be
honestly called either delivered or failed. Such messages are held for review,
not blindly retried. Failure before sending may be retried with bounded backoff.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .domain import notification_presence, presence_delivery
from .domain.engine import Engine
from .domain.pantry_expiry import current_event as current_pantry_expiry_event
from .domain.school_reminders import (
    KEY as SCHOOL_REMINDER_KEY,
)
from .domain.school_reminders import (
    delivery_allowed as school_reminder_delivery_allowed,
)
from .domain.task_delivery import TASK_EVENTS, current_task_event
from .domain.validation import timestamp

URGENT = {
    "alarm_challenge",
    "alarm_missed",
    "alarm_closed",
    "alarm_device_error",
    "alarm_device_recovered",
}


class DeliveryError(Exception):
    def __init__(self, code: str, *, retryable=False, uncertain=False, retry_after=0):
        self.code = code
        self.retryable = retryable
        self.uncertain = uncertain
        self.retry_after = min(max(retry_after, 0), 86400)
        super().__init__(code)


def quiet_until(now: datetime, policy: dict) -> datetime | None:
    if not policy.get("quiet_enabled"):
        return None
    zone = ZoneInfo(policy.get("timezone", "UTC"))
    local = now.astimezone(zone)
    start = time.fromisoformat(policy["quiet_start"])
    end = time.fromisoformat(policy["quiet_end"])
    if start == end:
        return None
    clock = local.time().replace(tzinfo=None)
    quiet = start <= clock < end if start < end else clock >= start or clock < end
    if not quiet:
        return None
    end_day = local.date() + timedelta(days=int(start > end and clock >= start))
    return datetime.combine(end_day, end, tzinfo=zone)


def _delivery_current(state: dict, event: dict, now: datetime) -> bool:
    if event.get("key") == "online_school_notice":
        from .online_school.delivery import current

        return current(state, event, now)
    """Recheck events whose private source can be revoked before transport."""
    if event.get("key") == "network_unreviewed_devices":
        from .network.watch import current

        return current(state, event, now)
    if event.get("key") == "family_digest":
        from .domain.digests import delivery_allowed

        return delivery_allowed(state, event, now)
    if event.get("key") == "telegram_reply":
        from .telegram.reply_delivery import current

        return current(event, state, now)
    if event.get("key") == "telegram_poll_reply":
        from .telegram.poll_delivery import current

        return current(event, state, now)
    if event.get("key") == "pantry_expiry":
        return current_pantry_expiry_event(state, event, now)
    if event.get("key") == SCHOOL_REMINDER_KEY:
        return school_reminder_delivery_allowed(state, event, now)
    if event.get("key") in TASK_EVENTS:
        return current_task_event(state, event)
    return True


class Notifications:
    def __init__(
        self,
        engine: Engine,
        resolve: Callable[[dict, dict], list[dict]],
        send: Callable[[dict, dict], Awaitable[str]],
        *,
        clock: Callable[[], datetime] | None = None,
        presence_prepare: Callable[[dict], Awaitable[Callable]] | None = None,
    ) -> None:
        self.engine, self.resolve, self.send = engine, resolve, send
        self.clock = clock
        self.presence_prepare = presence_prepare
        self._lock = asyncio.Lock()

    def _current_time(self, fallback: datetime) -> datetime:
        """Use a live adapter clock when supplied, or the caller's fixed test clock."""
        current = self.clock() if self.clock is not None else fallback
        return timestamp(current, "now")

    async def run(self, now: datetime, limit: int = 5) -> int:
        if self._lock.locked():
            return 0
        count = 0
        async with self._lock:
            for _ in range(min(max(limit, 0), 20)):
                observer = await self._presence_observer()
                claimed = await self.engine.background_update(
                    "outbox_claim", now, lambda ctx, observed=observer: self._claim(ctx, observed)
                )
                if claimed is None:
                    break
                event, delivery = claimed
                current = await self._authorize_dispatch(
                    event["id"], delivery["id"], now, await self._presence_observer()
                )
                if current is None:
                    continue
                if current[1].get("presence_recipient") is not None:
                    # The first authorization may persist a catch-up rate/hold
                    # change. Refresh HA account/ACL evidence after that await.
                    # An unchanged allow decision performs no second Store write.
                    current = await self._authorize_dispatch(
                        event["id"], delivery["id"], now, await self._presence_observer()
                    )
                    if current is None:
                        continue
                event, delivery = current
                try:
                    async with asyncio.timeout(15):
                        receipt = await self.send(event, delivery["target"])
                except DeliveryError as err:
                    await self._finish(event["id"], delivery["id"], now, error=err)
                except (TimeoutError, OSError):
                    await self._finish(
                        event["id"],
                        delivery["id"],
                        now,
                        error=DeliveryError("delivery_uncertain", uncertain=True),
                    )
                else:
                    await self._finish(event["id"], delivery["id"], now, receipt=receipt)
                count += 1
        return count

    async def _presence_observer(self):
        if self.presence_prepare is None:
            return None
        state = self.engine.snapshot()
        needed = False
        for event in state["outbox"].values():
            if event.get("state") not in {"pending", "awaiting_channel", "sending"}:
                continue
            if event.get("key") not in notification_presence.GATED_KEYS:
                continue
            for target in self.resolve(deepcopy(event), deepcopy(state)):
                member = notification_presence.recipient(state, event, target)
                if member and presence_delivery.effective_policy(state, member["id"]) is not None:
                    needed = True
                    break
            if needed:
                break
        if not needed:
            return None
        try:
            async with asyncio.timeout(2):
                return await self.presence_prepare(state)
        except (TimeoutError, OSError, ValueError, AttributeError, TypeError):
            # Missing identity/HA state cannot prove home. Existing reviewed policy
            # still defers; alarm/reply/group/closure lanes never call the observer.
            return None

    async def _authorize_dispatch(self, event_id, delivery_id, now, observer=None):
        """Recheck a persisted claim immediately before handing it to a transport.

        This closes the scheduling window between claim persistence and dispatch.
        It cannot recall a request after the transport has begun sending it.
        """

        def authorize(ctx):
            ctx.now = self._current_time(ctx.now)
            event = ctx.state["outbox"].get(event_id)
            if event is None or event["state"] != "sending":
                return None
            delivery = event.get("deliveries", {}).get(delivery_id)
            if delivery is None or delivery["state"] != "sending":
                return None

            def release_unstarted_watch():
                if event["key"] == "network_unreviewed_devices":
                    from .network.watch import release_undispatched

                    release_undispatched(ctx, event)

            if not _delivery_current(ctx.state, event, ctx.now):
                release_unstarted_watch()
                delivery["state"] = "superseded"
                self._aggregate(event)
                return None
            policy = ctx.state["settings"].get("notifications", {})
            if event["key"] not in URGENT and quiet_until(ctx.now, policy):
                release_unstarted_watch()
                delivery["state"] = "pending"
                delivery.pop("lease_until", None)
                self._aggregate(event)
                return None
            current_targets = self.resolve(deepcopy(event), deepcopy(ctx.state))
            if not self._target_current(delivery["target"], current_targets):
                release_unstarted_watch()
                delivery["state"] = "superseded"
                self._aggregate(event)
                return None
            decision = notification_presence.evaluate(ctx, event, delivery, observer, dispatch=True)
            if decision != "allow":
                release_unstarted_watch()
                if decision == "defer":
                    delivery["state"] = "pending"
                    delivery.pop("lease_until", None)
                self._aggregate(event)
                return None
            return deepcopy(event), deepcopy(delivery)

        return await self.engine.background_update("outbox_dispatch", now, authorize)

    @staticmethod
    def _target_current(target, current_targets):
        return any(
            current["channel"] == target["channel"]
            and current["id"] == target["id"]
            and current.get("bot_id") == target.get("bot_id")
            for current in current_targets
        )

    def _claim(self, ctx, observer=None):
        ctx.now = self._current_time(ctx.now)
        policy = ctx.state["settings"].get("notifications", {})
        for event in ctx.state["outbox"].values():
            if event["state"] in {"sent", "superseded", "failed", "uncertain", "resolved"}:
                continue
            if event["state"] != "sending" and not _delivery_current(ctx.state, event, ctx.now):
                if not event.get("deliveries"):
                    event["state"] = "superseded"
                else:
                    for delivery in event["deliveries"].values():
                        if delivery["state"] == "pending":
                            delivery["state"] = "superseded"
                    self._aggregate(event)
                continue
            if event["key"] in {"alarm_challenge", "calendar_reminder"}:
                if ctx.now >= timestamp(event["data"]["expires_at"], "expires_at"):
                    event["state"] = "superseded"
                    continue
            if event["key"] not in URGENT and quiet_until(ctx.now, policy):
                continue
            if not event.get("deliveries"):
                targets = self.resolve(deepcopy(event), deepcopy(ctx.state))
                if not targets:
                    event["state"] = "awaiting_channel"
                    continue
                event["deliveries"] = {}
                for target in targets:
                    target_id = hashlib.sha256(
                        f"{target['channel']}:{target['id']}".encode()
                    ).hexdigest()[:24]
                    event["deliveries"][target_id] = {
                        "id": target_id,
                        "target": target,
                        "state": "pending",
                        "attempts": 0,
                    }
                event["state"] = "pending"
            for delivery in event["deliveries"].values():
                if delivery["state"] == "sending":
                    if ctx.now >= timestamp(delivery["lease_until"], "lease_until"):
                        delivery.update(state="uncertain", error="delivery_uncertain")
                        self._aggregate(event)
                    continue
                if delivery["state"] != "pending":
                    continue
                current_targets = self.resolve(deepcopy(event), deepcopy(ctx.state))
                if not self._target_current(delivery["target"], current_targets):
                    delivery["state"] = "superseded"
                    self._aggregate(event)
                    continue  # Do not disclose family data to a revoked or unlinked recipient.
                if delivery.get("next_at") and ctx.now < timestamp(delivery["next_at"], "next_at"):
                    continue
                decision = notification_presence.evaluate(ctx, event, delivery, observer)
                if decision != "allow":
                    self._aggregate(event)
                    continue
                rate = ctx.state["notification_rates"].get(delivery["id"])
                if rate and ctx.now < timestamp(rate, "rate"):
                    continue
                if event["key"] == "network_unreviewed_devices":
                    from .network.watch import dispatch_ready, reserve_dispatch

                    if not dispatch_ready(ctx.state, event, ctx.now):
                        continue
                    reserve_dispatch(ctx, event)
                ctx.state["notification_rates"][delivery["id"]] = (
                    ctx.now + timedelta(seconds=1)
                ).isoformat()
                delivery.update(
                    state="sending",
                    lease_until=(ctx.now + timedelta(seconds=30)).isoformat(),
                    attempts=delivery["attempts"] + 1,
                )
                event["state"] = "sending"
                event["attempts"] += 1
                return deepcopy(event), deepcopy(delivery)
        return None

    @staticmethod
    def _aggregate(event):
        if event["state"] == "superseded":
            return
        statuses = {d["state"] for d in event["deliveries"].values()}
        if statuses == {"superseded"}:
            event["state"] = "superseded"
        elif statuses <= {"sent", "superseded"}:
            event["state"] = "sent"
        elif "pending" in statuses or "sending" in statuses:
            event["state"] = "pending"
        elif "uncertain" in statuses:
            event["state"] = "uncertain"
        else:
            event["state"] = "failed"

    async def _finish(self, event_id, delivery_id, now, *, receipt=None, error=None):
        def finish(ctx):
            ctx.now = self._current_time(ctx.now)
            event = ctx.state["outbox"][event_id]
            delivery = event["deliveries"][delivery_id]
            if error is None:
                delivery.update(state="sent", receipt=str(receipt), sent_at=ctx.now.isoformat())
            elif error.uncertain:
                delivery.update(state="uncertain", error=error.code)
            elif error.retryable and delivery["attempts"] < 5:
                delay = max(error.retry_after, min(300, 5 * 2 ** (delivery["attempts"] - 1)))
                delivery.update(
                    state="pending",
                    error=error.code,
                    next_at=(ctx.now + timedelta(seconds=delay)).isoformat(),
                )
            else:
                delivery.update(state="failed", error=error.code)
            self._aggregate(event)

        await self.engine.background_update("outbox_receipt", now, finish)
