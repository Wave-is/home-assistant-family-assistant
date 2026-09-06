"""One adopted profile, persisted effect intents and verified native timer guards."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from ..domain.validation import DomainError, timestamp
from . import kid_timer, kids


class KidExecutor:
    def __init__(self, client, plan, persist, authorized, protected_macs=(), *, clock=None):
        self.client, self.plan, self.persist, self.authorized = (
            client,
            deepcopy(plan),
            persist,
            authorized,
        )
        self.protected = tuple(protected_macs)
        self.progress = None
        self.hash = kids.digest(self.plan)
        self.clock = clock or (lambda: datetime.now(UTC))

    def deadline(self):
        if (
            self.plan.get("until")
            and self.progress["status"] == "applying"
            and self.clock() >= timestamp(self.plan["until"], "until") - timedelta(seconds=30)
        ):
            raise DomainError("proposal_expired")

    def authorize(self):
        if self.authorized() is not True:
            raise DomainError("forbidden")

    async def save(self):
        await self.persist(deepcopy(self.progress))

    async def current(self, now=None):
        tables = {key: await self.client.read(key) for key in ("kids", "kid_devices", "interfaces")}
        actual = kids.validate_binding(tables, self.plan["binding"], self.protected)
        if now:
            tables["clock"] = await self.client.read("clock")
            kids.router_clock(tables, now, self.plan["timezone"])
        return actual

    async def guards(self):
        for spec in kid_timer.specifications(self.plan):
            self.authorize()
            rows = await self.client.kid_timers(spec["name"])
            if not rows:
                self.progress["phase"] = "installing_timer"
                await self.save()
                try:
                    await self.client.install_kid_timer(self.plan, spec["name"])
                except DomainError:
                    pass
                rows = await self.client.kid_timers(spec["name"])
            if len(rows) != 1 or not kid_timer.matches(rows[0], spec):
                raise DomainError("network_timer_required")
        self.progress["timer_verified"] = True
        await self.save()

    async def remove_guards(self):
        if not self.plan.get("until"):
            return
        for spec in kid_timer.specifications(self.plan):
            self.authorize()
            rows = await self.client.kid_timers(spec["name"])
            if rows:
                if len(rows) != 1 or not kid_timer.matches(rows[0], spec):
                    raise DomainError("network_conflict")
                try:
                    await self.client.remove_kid_timer(rows[0][".id"], spec["name"])
                except DomainError:
                    pass
                if await self.client.kid_timers(spec["name"]):
                    raise DomainError("network_readback")

    async def set_profile(self, expected, desired):
        actual = await self.current()
        if actual == desired:
            return
        if actual != expected:
            raise DomainError("network_conflict")
        self.authorize()
        patch = {
            k: v for k, v in desired.items() if k not in {"name", "paused"} and expected[k] != v
        }
        intermediate = {**expected, **patch}
        if patch:
            self.progress["phase"] = "patching"
            self.progress["intermediate"] = intermediate
            await self.save()
            error = None
            self.deadline()
            try:
                await self.client.set_kid_profile(self.plan["binding"]["profile_id"], patch)
            except DomainError as err:
                error = err
            if await self.current() != intermediate:
                raise error or DomainError("network_readback")
        if intermediate["paused"] != desired["paused"]:
            self.authorize()
            self.progress["phase"] = "toggling"
            await self.save()
            error = None
            self.deadline()
            try:
                await self.client.pause_kid(
                    self.plan["binding"]["profile_id"], desired["paused"] == "true"
                )
            except DomainError as err:
                error = err
            if await self.current() != desired:
                raise error or DomainError("network_readback")

    async def run(self, now, progress=None):
        self.authorize()
        if progress is not None and (
            not isinstance(progress, dict)
            or progress.get("plan_hash") != self.hash
            or progress.get("phase")
            not in {"ready", "installing_timer", "patching", "toggling", "verified", "restored"}
            or progress.get("status")
            not in {"applying", "rolling_back", "applied", "rolled_back", "review_required"}
        ):
            raise DomainError("network_conflict")
        if progress and progress["status"] in {"applied", "rolled_back", "review_required"}:
            return deepcopy(progress)
        if progress is None and now >= timestamp(self.plan["expires_at"], "expires_at"):
            raise DomainError("proposal_expired")
        self.progress = (
            deepcopy(progress)
            if progress
            else {"plan_hash": self.hash, "status": "applying", "phase": "ready"}
        )
        await self.save()
        try:
            if self.progress["status"] == "rolling_back":
                await self.rollback()
                return deepcopy(self.progress)
            actual = await self.current(now)
            if self.progress["phase"] == "ready" and actual != self.plan["before"]:
                raise DomainError("network_conflict")
            if actual not in (
                self.plan["before"],
                self.plan["after"],
                self.progress.get("intermediate"),
            ):
                raise DomainError("network_conflict")
            if self.plan.get("until"):
                if now >= timestamp(self.plan["until"], "until") - timedelta(seconds=30):
                    raise DomainError("proposal_expired")
                version = await self.client.read("resource")
                parts = version[0].get("version", "").split(".") if version else []
                if (
                    len(parts) < 2
                    or parts[0] != "7"
                    or not parts[1].isdigit()
                    or int(parts[1]) < 16
                ):
                    raise DomainError("network_timer_required")
                await self.guards()
            # A pre-effect journal reconciles an accepted PATCH after an interrupted save.
            await self.set_profile(actual, self.plan["after"])
            self.progress.update(status="applied", phase="verified")
            await self.save()
        except DomainError as err:
            self.progress.update(status="rolling_back", failure=err.code)
            await self.save()
            await self.rollback()
        return deepcopy(self.progress)

    async def rollback(self):
        try:
            self.authorize()
            actual = await self.current()
            if actual not in (
                self.plan["before"],
                self.plan["after"],
                self.progress.get("intermediate"),
            ):
                raise DomainError("network_conflict")
            await self.set_profile(actual, self.plan["before"])
            await self.remove_guards()
            self.progress.update(status="rolled_back", phase="restored")
        except DomainError as err:
            self.progress.update(status="review_required", error=err.code)
        await self.save()
