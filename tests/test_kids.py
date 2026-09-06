"""Native schedules, adopted membership, parent authority and durable router effects."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network import kid_timer, kids
from custom_components.family_assistant.network.kid_executor import KidExecutor


class Router:
    def __init__(self, now):
        self.tables = {
            "kids": [
                {
                    ".id": "*1",
                    "name": "Child profile",
                    "disabled": "false",
                    "paused": "false",
                    **{d: "8h-22h" for d in kids.DAYS},
                }
            ],
            "kid_devices": [
                {
                    ".id": "*2",
                    "name": "Phone",
                    "mac-address": "02:11:22:33:44:55",
                    "user": "Child profile",
                    "dynamic": "false",
                }
            ],
            "interfaces": [],
            "clock": [
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S"),
                    "time-zone-name": "UTC",
                }
            ],
            "resource": [{"version": "7.20.1"}],
        }
        self.timers, self.calls = {}, []
        self.fail = None
        self.hook = None

    async def read(self, key):
        return deepcopy(self.tables[key])

    async def set_kid_profile(self, target, changes):
        assert target == "*1"
        self.calls.append(("patch", deepcopy(changes)))
        self.tables["kids"][0].update(changes)
        if self.hook:
            self.hook()
        if self.fail == "patch-reply":
            raise DomainError("network_timeout")

    async def pause_kid(self, target, paused):
        assert target == "*1"
        self.calls.append(("pause", paused))
        if self.fail == "pause-denied":
            raise DomainError("network_permission")
        self.tables["kids"][0]["paused"] = str(paused).lower()

    async def kid_timers(self, name):
        return [deepcopy(self.timers[name])] if name in self.timers else []

    async def install_kid_timer(self, plan, name):
        self.calls.append(("timer", name))
        if self.fail == "timer-denied":
            raise DomainError("network_permission")
        spec = next(s for s in kid_timer.specifications(plan) if s["name"] == name)
        self.timers[name] = {**spec, ".id": "*" + str(10 + len(self.timers))}
        if self.fail == "timer-reply":
            raise DomainError("network_timeout")

    async def remove_kid_timer(self, target, name):
        assert self.timers[name][".id"] == target
        self.calls.append(("remove-timer", name))
        del self.timers[name]


class Journal:
    def __init__(self):
        self.saved = None
        self.fail_phase = None

    async def save(self, value):
        if value.get("phase") == self.fail_phase:
            raise OSError("synthetic disk fault")
        self.saved = deepcopy(value)


def binding(router):
    return {**kids.bind(router.tables, "*1", ["*2"]), "member": "child", "backend": "synthetic"}


def plan(router, now, mode="pause", **kwargs):
    result = kids.prepare(
        router.tables, binding(router), {"member": "child", "mode": mode, **kwargs}, now, "UTC"
    )
    return {**result, "id": "K000001", "backend": "synthetic"}


@pytest.mark.parametrize(
    "source,expected",
    [
        ("8h-22h", "08:00-22:00"),
        ("08:00:00-10:00:00,09:00-12:00", "08:00-12:00"),
        ("0h-24h", "00:00-24:00"),
        ("7h30m-1d", "07:30-24:00"),
        ("0s-1d00:00:00", "00:00-24:00"),
        ("510m-22h15m0s", "08:30-22:15"),
        ("", ""),
    ],
)
def test_normalized_native_windows(source, expected):
    assert kids.windows(source) == expected


def test_scheduler_uses_native_yes_no_not_rest_boolean_assignments(now):
    router = Router(now)
    for disabled, native in (("true", "yes"), ("false", "no")):
        router.tables["kids"][0]["disabled"] = disabled
        item = plan(router, now, "timed_pause", minutes=1)
        for spec in kid_timer.specifications(item):
            assert f"set $p disabled={native};" in spec["on-event"]
            assert "disabled=true;" not in spec["on-event"]
            assert "disabled=false;" not in spec["on-event"]


@pytest.mark.parametrize(
    "source",
    ["22:00-08:00", "24:01-24h", "8h; reboot", "08:60-22h", "08:00-08:00", ["08:00-22:00"]],
)
def test_invalid_windows_fail_closed(source):
    with pytest.raises(DomainError):
        kids.windows(source)


def test_membership_all_devices_protection_and_clock(now):
    router = Router(now)
    b = binding(router)
    with pytest.raises(DomainError, match="network_protected"):
        kids.bind(router.tables, "*1", ["*2"], ["02:11:22:33:44:55"])
    router.tables["kid_devices"].append(
        {**router.tables["kid_devices"][0], ".id": "*3", "mac-address": "02:11:22:33:44:66"}
    )
    with pytest.raises(DomainError, match="network_kid_membership"):
        kids.validate_binding(router.tables, b)
    with pytest.raises(DomainError, match="network_clock"):
        kids.router_clock(router.tables, now + timedelta(minutes=3), "UTC")
    with pytest.raises(DomainError, match="network_clock"):
        kids.router_clock(router.tables, now, "Europe/London")


@pytest.mark.asyncio
async def test_native_resume_keeps_schedule_and_pause_is_read_back(now):
    router, journal = Router(now), Journal()
    result = await KidExecutor(router, plan(router, now), journal.save, lambda: True).run(now)
    assert result["status"] == "applied" and router.calls == [("pause", True)]
    assert router.tables["kids"][0]["mon"] == "8h-22h"
    resume = plan(router, now, "resume")
    assert resume["diff"] == {"paused": {"before": "true", "after": "false"}}
    await KidExecutor(router, resume, journal.save, lambda: True).run(now)
    assert router.calls[-1] == ("pause", False)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "timer-reply", "patch-reply"])
async def test_temporary_grant_registers_both_guards_before_effect(now, failure):
    router, journal = Router(now), Journal()
    router.fail = failure
    p = plan(router, now, "grant", minutes=30)
    result = await KidExecutor(router, p, journal.save, lambda: True, clock=lambda: now).run(now)
    assert result["status"] == "applied" and result["timer_verified"]
    assert [c[0] for c in router.calls] == ["timer", "timer", "patch"]
    assert router.tables["kids"][0]["disabled"] == "true"
    assert len(router.timers) == 2
    assert (
        await KidExecutor(router, p, journal.save, lambda: True).run(now, journal.saved) == result
    )
    assert len(router.calls) == 3


@pytest.mark.asyncio
async def test_no_grant_when_timer_permission_or_clock_fails(now):
    router, journal = Router(now), Journal()
    router.fail = "timer-denied"
    result = await KidExecutor(
        router,
        plan(router, now, "grant", minutes=30),
        journal.save,
        lambda: True,
        clock=lambda: now,
    ).run(now)
    assert result["status"] == "rolled_back" and not any(c[0] == "patch" for c in router.calls)
    assert router.tables["kids"][0]["disabled"] == "false"


@pytest.mark.asyncio
async def test_partial_patch_rollback_and_storage_recovery(now):
    router, journal = Router(now), Journal()
    router.tables["kids"][0]["disabled"] = "true"
    router.fail = "pause-denied"
    result = await KidExecutor(router, plan(router, now), journal.save, lambda: True).run(now)
    assert result["status"] == "rolled_back" and router.tables["kids"][0]["disabled"] == "true"
    router.fail = None
    journal.fail_phase = "toggling"
    p = plan(router, now)
    with pytest.raises(OSError):
        await KidExecutor(router, p, journal.save, lambda: True).run(now)
    assert journal.saved["phase"] == "patching"
    journal.fail_phase = None
    result = await KidExecutor(router, p, journal.save, lambda: True).run(now, journal.saved)
    assert result["status"] == "applied"


@pytest.mark.asyncio
async def test_external_edit_never_restored_over_and_role_revoked(now):
    router, journal = Router(now), Journal()
    p = plan(router, now, "schedule", schedule={"mon": "09:00-21:00"})
    router.tables["kids"][0]["mon"] = "09:00-20:00"
    result = await KidExecutor(router, p, journal.save, lambda: True).run(now)
    assert result["status"] == "review_required" and not router.calls
    with pytest.raises(DomainError, match="forbidden"):
        await KidExecutor(router, p, journal.save, lambda: False).run(now)


@pytest.mark.asyncio
async def test_expiry_recovery_returns_previous_mode_and_removes_only_scoped_guards(now):
    router, journal = Router(now), Journal()
    p = plan(router, now, "grant", minutes=30)
    await KidExecutor(router, p, journal.save, lambda: True, clock=lambda: now).run(now)
    router.timers["unrelated"] = {".id": "*99", "name": "unrelated"}
    progress = {**journal.saved, "status": "rolling_back"}
    result = await KidExecutor(router, p, journal.save, lambda: True).run(
        now + timedelta(hours=1), progress
    )
    assert result["status"] == "rolled_back" and router.tables["kids"][0]["disabled"] == "false"
    assert set(router.timers) == {"unrelated"}


def test_timer_has_fixed_scope_and_no_raw_profile_code(now):
    router = Router(now)
    dangerous = 'Child"; /system reboot; "$x'
    router.tables["kids"][0]["name"] = dangerous
    router.tables["kid_devices"][0]["user"] = dangerous
    p = plan(router, now, "grant", minutes=30)
    specs = kid_timer.specifications(p)
    assert {s["start-time"] for s in specs} == {"08:30:00", "startup"}
    assert all("/system reboot" not in s["on-event"] and s["policy"] == "read,write" for s in specs)
    assert all(kid_timer.matches(s, s) for s in specs)
    assert not kid_timer.matches({**specs[0], "policy": "read,write,policy"}, specs[0])


async def prepare_engine(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "mikrotik"]},
        "enable-kids",
        now,
    )
    router = Router(now)

    def save(ctx):
        ctx.state["network"].update(
            backend="synthetic",
            kid_writable=True,
            inventory={"observed_at": now.isoformat()},
            tables=router.tables,
        )

    await engine.system_update("inventory", now, save)
    await engine.execute(
        "owner",
        "mikrotik.kid_adopt",
        {"member": "child", "profile_id": "*1", "devices": ["*2"], "confirmed": True},
        "adopt",
        now,
    )


@pytest.mark.asyncio
async def test_owner_adoption_parent_commands_child_visibility_and_explicit_adult_grant(
    engine, now
):
    await prepare_engine(engine, now)
    assert engine.view("child")["kid_control"]["profiles"][0]["devices"] == []
    assert not engine.view("sibling")["kid_control"]["profiles"]
    for actor in ("child", "adult", "guest"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                actor,
                "mikrotik.kid_plan",
                {"member": "child", "mode": "pause"},
                "deny-" + actor,
                now,
            )
    p = await engine.execute(
        "parent", "mikrotik.kid_plan", {"member": "child", "mode": "pause"}, "preview", now
    )
    assert p["status"] == "preview"
    with pytest.raises(DomainError, match="network_confirmation"):
        await engine.execute("parent", "mikrotik.kid_apply", {"id": p["id"]}, "no-confirm", now)
    payload = {"id": p["id"], "confirmed": True}
    result = await engine.execute("parent", "mikrotik.kid_apply", payload, "apply", now)
    assert result["status"] == "queued"
    assert await engine.execute("parent", "mikrotik.kid_apply", payload, "apply", now) == result
    await engine.execute(
        "owner", "mikrotik.kid_permission", {"member": "adult", "enabled": True}, "grant", now
    )
    assert engine.view("adult")["kid_control"]["can_manage"]


@pytest.mark.asyncio
async def test_delegation_revocation_rejects_exact_replay_without_role_change(engine, now):
    await prepare_engine(engine, now)
    await engine.execute(
        "owner", "mikrotik.kid_permission", {"member": "adult", "enabled": True}, "grant", now
    )
    payload = {"member": "child", "mode": "pause"}
    await engine.execute("adult", "mikrotik.kid_plan", payload, "adult-preview", now)
    await engine.execute(
        "owner", "mikrotik.kid_permission", {"member": "adult", "enabled": False}, "revoke", now
    )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("adult", "mikrotik.kid_plan", payload, "adult-preview", now)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase,mode,options",
    [
        ("installing_timer", "grant", {"minutes": 30}),
        ("patching", "schedule", {"schedule": {"mon": "09:00-20:00"}}),
        ("toggling", "pause", {}),
    ],
)
async def test_revocation_during_store_await_prevents_next_effect(now, phase, mode, options):
    router, journal = Router(now), Journal()
    allowed = True

    async def persist(progress):
        nonlocal allowed
        await journal.save(progress)
        if progress.get("phase") == phase:
            allowed = False

    result = await KidExecutor(
        router, plan(router, now, mode, **options), persist, lambda: allowed, clock=lambda: now
    ).run(now)
    assert result["status"] == "review_required" and not router.calls


@pytest.mark.asyncio
async def test_expired_during_timer_install_never_opens_access(now):
    router, journal = Router(now), Journal()
    current = now

    async def persist(progress):
        nonlocal current
        await journal.save(progress)
        if progress.get("timer_verified"):
            current = now + timedelta(minutes=2)

    result = await KidExecutor(
        router, plan(router, now, "grant", minutes=1), persist, lambda: True, clock=lambda: current
    ).run(now)
    assert result["status"] == "rolled_back" and result["failure"] == "proposal_expired"
    assert all(call[0] in {"timer", "remove-timer"} for call in router.calls)
    assert not router.timers
