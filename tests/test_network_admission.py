"""Actual Engine transactions for explicitly reviewed local approvals, not firewall changes."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.admission_inventory import observation_token
from custom_components.family_assistant.network.inventory import build

CLIENT = "02:11:22:33:44:55"
PROTECTED = "02:11:22:33:44:66"


async def setup(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "mikrotik"]},
        "enable-network-admission",
        now,
    )

    def seed(ctx):
        tables = {
            "leases": [
                {
                    "mac-address": value,
                    "active-address": f"198.51.100.{index + 10}",
                    "status": "bound",
                    "host-name": "Named but not approved",
                }
                for index, value in enumerate((CLIENT, PROTECTED))
            ],
            "interfaces": [{"mac-address": PROTECTED}],
        }
        ctx.state["network"].update(
            backend="a" * 64,
            inventory=build(tables, [], now),
            tables=tables,
            protected_macs=[PROTECTED],
            writable=False,
            kid_writable=False,
        )

    await engine.system_update("synthetic-audit-network", now, seed)
    return engine


@pytest.mark.asyncio
async def test_preview_replay_and_projection_revoke_after_another_policy_commit(engine, now):
    e = await setup(engine, now)
    first_payload = request(e, now)
    other_payload = request(
        e, now, changes=[{"mac": CLIENT, "approved": True, "label": "Other label"}]
    )
    first = await e.execute(
        "owner", "mikrotik.admission_preview", first_payload, "first-preview", now
    )
    other = await e.execute(
        "owner", "mikrotik.admission_preview", other_payload, "other-preview", now
    )
    await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": other["id"], "actor_revision": 1, "confirmed": True},
        "other-apply",
        now,
    )
    before = e.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("owner", "mikrotik.admission_preview", first_payload, "first-preview", now)
    assert e.snapshot() == before
    plans = e.view("owner", now=now)["network"]["admission"]["plans"]
    assert next(plan for plan in plans if plan["id"] == first["id"])["applicable"] is False


def request(e, now, **changes):
    return {
        "actor_revision": e.snapshot()["members"]["owner"]["revision"],
        "observation_token": observation_token(e.snapshot()["network"], now),
        "policy_revision": e.snapshot()["network"].get("admission", {}).get("revision"),
        "changes": [{"mac": CLIENT, "approved": True, "label": "Reviewed test device"}],
        **changes,
    }


@pytest.mark.asyncio
async def test_exact_local_preview_apply_replay_restore_without_any_router_effect(
    engine, store, now
):
    e = await setup(engine, now)
    before = e.snapshot()
    payload = request(e, now)
    plan = await e.execute("owner", "mikrotik.admission_preview", payload, "preview", now)
    assert plan["status"] == "preview"
    assert "admission" not in e.snapshot()["network"]
    snapshot = e.snapshot()
    assert await e.execute("owner", "mikrotik.admission_preview", payload, "preview", now) == plan
    assert e.snapshot() == snapshot
    applied_payload = {
        "id": plan["id"],
        "actor_revision": payload["actor_revision"],
        "confirmed": True,
    }
    result = await e.execute("owner", "mikrotik.admission_apply", applied_payload, "apply", now)
    assert result == {"id": plan["id"], "status": "applied", "revision": 1}
    current = e.snapshot()
    assert current["network"]["admission"]["entries"] == {CLIENT: {"label": "Reviewed test device"}}
    for key in ("tables", "inventory", "plans", "kid_plans"):
        assert current["network"].get(key) == before["network"].get(key)
    for key in ("outbox", "tasks", "alarms", "court", "shopping"):
        assert current[key] == before[key]
    restored = Engine(deepcopy(store.value), store.save)
    assert (
        await restored.execute("owner", "mikrotik.admission_apply", applied_payload, "apply", now)
        == result
    )
    assert restored.snapshot() == current
    projection = restored.view("owner", now=now)["network"]["admission"]
    assert projection["mode"] == "audit_only" and projection["enforcement"] is False
    assert (
        next(row for row in projection["devices"] if row["mac"] == CLIENT)["status"] == "approved"
    )
    assert restored.view("parent", now=now)["network"]["admission"]["can_edit"] is False
    assert "network" not in restored.view("child", now=now)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["parent", "adult", "child", "guest"])
async def test_nonowner_cannot_approve_device(engine, now, actor):
    e = await setup(engine, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(actor, "mikrotik.admission_preview", request(e, now), "denied", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["expired", "future", "backend", "protected", "actor"])
async def test_changed_evidence_or_actor_cannot_apply_old_plan(engine, store, now, drift):
    e = await setup(engine, now)
    plan = await e.execute("owner", "mikrotik.admission_preview", request(e, now), "preview", now)
    state = e.snapshot()
    at = now
    if drift == "expired":
        at += timedelta(minutes=2)
    if drift == "future":
        state["network"]["inventory"]["observed_at"] = (now + timedelta(seconds=1)).isoformat()
    if drift == "backend":
        state["network"]["backend"] = "b" * 64
    if drift == "protected":
        state["network"]["protected_macs"].append(CLIENT)
    if drift == "actor":
        state["members"]["owner"]["revision"] += 1
    restored = Engine(state, store.save)
    before = restored.snapshot()
    with pytest.raises(DomainError):
        await restored.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan["id"], "actor_revision": 1, "confirmed": True},
            "stale-apply",
            at,
        )
    assert restored.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad", ["protected", "boolean_revision", "truthy", "duplicate", "router_action"]
)
async def test_invalid_or_protected_selection_is_atomic(engine, now, bad):
    e = await setup(engine, now)
    payload = request(e, now)
    if bad == "protected":
        payload["changes"][0]["mac"] = PROTECTED
    if bad == "boolean_revision":
        payload["actor_revision"] = True
    if bad == "truthy":
        payload["changes"][0]["approved"] = 1
    if bad == "duplicate":
        payload["changes"] *= 2
    if bad == "router_action":
        payload["mode"] = "quarantine"
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute("owner", "mikrotik.admission_preview", payload, "invalid", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_disk_failure_rolls_back_apply_and_retry_keeps_same_plan(engine, store, now):
    e = await setup(engine, now)
    plan = await e.execute("owner", "mikrotik.admission_preview", request(e, now), "preview", now)
    payload = {"id": plan["id"], "actor_revision": 1, "confirmed": True}
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("owner", "mikrotik.admission_apply", payload, "apply", now)
    assert e.snapshot() == before
    store.fail = False
    assert (await e.execute("owner", "mikrotik.admission_apply", payload, "apply", now))[
        "revision"
    ] == 1


@pytest.mark.asyncio
async def test_backend_replacement_requires_review_and_archives_previous_approvals(
    engine, store, now
):
    e = await setup(engine, now)
    plan = await e.execute(
        "owner", "mikrotik.admission_preview", request(e, now), "first-preview", now
    )
    await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan["id"], "actor_revision": 1, "confirmed": True},
        "first-apply",
        now,
    )
    state = e.snapshot()
    original_policy = deepcopy(state["network"]["admission"])
    state["network"]["backend"] = "b" * 64
    other = Engine(state, store.save)
    assert other.view("owner", now=now)["network"]["admission"]["backend_changed"] is True
    with pytest.raises(DomainError, match="network_confirmation"):
        await other.execute(
            "owner", "mikrotik.admission_preview", request(other, now), "unreviewed-source", now
        )
    plan = await other.execute(
        "owner",
        "mikrotik.admission_preview",
        request(other, now, replace_backend=True),
        "new-source-preview",
        now,
    )
    assert plan["backend_changed"] is True
    result = await other.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan["id"], "actor_revision": 1, "confirmed": True},
        "new-source-apply",
        now,
    )
    assert result["revision"] == 2
    current = other.snapshot()["network"]
    assert current["admission"]["backend"] == "b" * 64
    assert current["admission_archives"][0]["policy"] == original_policy
    assert current["tables"] == state["network"]["tables"]


@pytest.mark.asyncio
async def test_unobserved_protected_mac_cannot_be_removed_from_local_approvals(engine, store, now):
    e = await setup(engine, now)
    state = e.snapshot()
    state["network"]["admission"] = {
        "revision": 1,
        "backend": "a" * 64,
        "entries": {CLIENT: {"label": "Protected offline"}},
        "updated_at": now.isoformat(),
    }
    state["network"]["inventory"]["devices"] = []
    state["network"]["protected_macs"].append(CLIENT.lower())
    restored = Engine(state, store.save)
    before = restored.snapshot()
    with pytest.raises(DomainError, match="network_protected"):
        await restored.execute(
            "owner",
            "mikrotik.admission_preview",
            request(restored, now, changes=[{"mac": CLIENT, "approved": False}]),
            "offline-protected",
            now,
        )
    assert restored.snapshot() == before
