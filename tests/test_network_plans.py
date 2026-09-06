"""Network side effects require an owner, a fresh preview and separate confirmation."""

import pytest

from custom_components.family_assistant.domain.validation import DomainError


async def prepare(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "mikrotik"]},
        "enable-network",
        now,
    )

    def save(ctx):
        ctx.state["network"].update(
            backend="synthetic-backend",
            writable=True,
            inventory={"observed_at": now.isoformat()},
            tables={
                "leases": [
                    {
                        ".id": "*1",
                        "address": "198.51.100.10",
                        "mac-address": "02:11:22:33:44:55",
                        "server": "lan",
                        "dynamic": "true",
                        "status": "bound",
                        "comment": "Original",
                    }
                ],
                "networks": [{"address": "198.51.100.0/24"}],
                "servers": [{"name": "lan", "interface": "lan"}],
                "addresses": [{"address": "198.51.100.1/24", "interface": "lan"}],
            },
        )

    await engine.system_update("network", now, save)


@pytest.mark.asyncio
async def test_owner_preview_and_explicit_dhcp_recovery_consent(engine, now):
    await prepare(engine, now)
    for actor in ("child", "parent", "adult", "guest"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                actor, "mikrotik.lease_plan", {"leases": [{"id": "*1"}]}, "denied-" + actor, now
            )
    plan = await engine.execute(
        "owner", "mikrotik.lease_plan", {"leases": [{"id": "*1"}]}, "preview", now
    )
    assert plan["status"] == "preview" and "before" not in plan["targets"][0]
    with pytest.raises(DomainError, match="network_confirmation"):
        await engine.execute(
            "owner", "mikrotik.lease_apply", {"id": plan["id"]}, "apply-no-confirm", now
        )
    with pytest.raises(DomainError, match="network_recovery_consent"):
        await engine.execute(
            "owner",
            "mikrotik.lease_apply",
            {"id": plan["id"], "confirmed": True},
            "apply-no-consent",
            now,
        )
    payload = {"id": plan["id"], "confirmed": True, "dhcp_recovery": True}
    queued = await engine.execute("owner", "mikrotik.lease_apply", payload, "apply", now)
    assert queued["status"] == "queued"
    assert await engine.execute("owner", "mikrotik.lease_apply", payload, "apply", now) == queued
    assert engine.snapshot()["network"]["tables"]["leases"][0]["dynamic"] == "true"
    assert "network" not in engine.view("child")


@pytest.mark.asyncio
async def test_old_backend_or_readonly_does_not_queue(engine, now):
    await prepare(engine, now)
    plan = await engine.execute(
        "owner", "mikrotik.lease_plan", {"leases": [{"id": "*1"}]}, "preview", now
    )

    def change(ctx):
        ctx.state["network"]["backend"] = "another-backend"

    await engine.system_update("replace-router", now, change)
    with pytest.raises(DomainError, match="network_conflict"):
        await engine.execute(
            "owner",
            "mikrotik.lease_apply",
            {"id": plan["id"], "confirmed": True, "dhcp_recovery": True},
            "apply",
            now,
        )

    def readonly(ctx):
        ctx.state["network"]["writable"] = False

    await engine.system_update("disable-writes", now, readonly)
    with pytest.raises(DomainError, match="network_readonly"):
        await engine.execute(
            "owner", "mikrotik.lease_apply", {"id": plan["id"]}, "apply-readonly", now
        )
    assert engine.snapshot()["network"]["plans"][plan["id"]]["status"] == "preview"
