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

from .domain.engine import Engine
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


class Notifications:
    def __init__(
        self,
        engine: Engine,
        resolve: Callable[[dict, dict], list[dict]],
        send: Callable[[dict, dict], Awaitable[str]],
    ) -> None:
        self.engine, self.resolve, self.send = engine, resolve, send
        self._lock = asyncio.Lock()

    async def run(self, now: datetime, limit: int = 5) -> int:
        if self._lock.locked():
            return 0
        count = 0
        async with self._lock:
            for _ in range(min(max(limit, 0), 20)):
                claimed = await self.engine.system_update("outbox_claim", now, self._claim)
                if claimed is None:
                    break
                event, delivery = claimed
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

    def _claim(self, ctx):
        policy = ctx.state["settings"].get("notifications", {})
        for event in ctx.state["outbox"].values():
            if event["state"] in {"sent", "superseded", "failed", "uncertain", "resolved"}:
                continue
            if event["key"] == "alarm_challenge":
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
                if not any(
                    t["channel"] == delivery["target"]["channel"]
                    and t["id"] == delivery["target"]["id"]
                    and t.get("bot_id") == delivery["target"].get("bot_id")
                    for t in current_targets
                ):
                    delivery["state"] = "superseded"
                    self._aggregate(event)
                    continue  # Do not disclose family data to a revoked or unlinked recipient.
                if delivery.get("next_at") and ctx.now < timestamp(delivery["next_at"], "next_at"):
                    continue
                rate = ctx.state["notification_rates"].get(delivery["id"])
                if rate and ctx.now < timestamp(rate, "rate"):
                    continue
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
            event = ctx.state["outbox"][event_id]
            delivery = event["deliveries"][delivery_id]
            if error is None:
                delivery.update(state="sent", receipt=str(receipt), sent_at=now.isoformat())
            elif error.uncertain:
                delivery.update(state="uncertain", error=error.code)
            elif error.retryable and delivery["attempts"] < 5:
                delay = max(error.retry_after, min(300, 5 * 2 ** (delivery["attempts"] - 1)))
                delivery.update(
                    state="pending",
                    error=error.code,
                    next_at=(now + timedelta(seconds=delay)).isoformat(),
                )
            else:
                delivery.update(state="failed", error=error.code)
            self._aggregate(event)

        await self.engine.system_update("outbox_receipt", now, finish)
