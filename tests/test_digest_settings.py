"""Owner digest policy is strict, narrowly scoped, and safe across ABA/retry."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain import digest_settings as policy
from custom_components.family_assistant.domain.validation import DomainError


def request(engine, **changes):
    state = engine.snapshot()
    return {
        "actor_revision": state["members"]["owner"]["revision"],
        "policy_fingerprint": policy.fingerprint(state),
        **policy.values(state),
        **changes,
    }


async def general(engine, now, operation, **changes):
    settings = engine.snapshot()["settings"]
    return await engine.execute(
        "owner",
        "settings.save",
        {key: changes.get(key, settings[key]) for key in ("name", "language", "modules")}
        | {
            key: value
            for key, value in changes.items()
            if key not in {"name", "language", "modules"}
        },
        operation,
        now,
    )


@pytest.mark.asyncio
async def test_policy_changes_only_its_fields_and_exact_retry_is_nonmutating(engine, now, store):
    before = engine.snapshot()
    payload = request(engine, digest_morning_enabled=True, digest_morning_time="08:15")
    receipt = await engine.execute("owner", "settings.digest_policy", payload, "policy", now)
    after = engine.snapshot()
    assert receipt == {"policy_fingerprint": policy.fingerprint(after)}
    assert after["settings"]["digest_policy_revision"] == 2
    for key in before:
        if key not in {"settings", "revision", "audit", "processed"}:
            assert after[key] == before[key]
    assert after["settings"]["name"] == before["settings"]["name"]
    calls = store.calls
    assert (
        await engine.execute("owner", "settings.digest_policy", payload, "policy", now) == receipt
    )
    assert store.calls == calls and engine.snapshot() == after
    # An unrelated household rename does not stale the reviewed digest policy.
    await general(engine, now, "rename", name="Another synthetic name")
    assert policy.fingerprint(engine.snapshot()) == receipt["policy_fingerprint"]
    assert (
        await engine.execute("owner", "settings.digest_policy", payload, "policy", now) == receipt
    )


@pytest.mark.asyncio
async def test_stale_policy_and_member_epoch_reject_without_writes(engine, now):
    stale = request(engine, digest_evening_time="20:00")
    await engine.execute(
        "owner", "settings.digest_policy", request(engine, digest_weekly_enabled=True), "newer", now
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("owner", "settings.digest_policy", stale, "stale", now)
    assert engine.snapshot() == before
    payload = request(engine, digest_evening_time="20:00")
    await engine.execute("owner", "settings.digest_policy", payload, "current", now)
    owner = engine.snapshot()["members"]["owner"]
    await engine.execute(
        "owner",
        "members.save",
        {"id": "owner", "revision": owner["revision"], "name": "Renamed owner", "role": "owner"},
        "member",
        now,
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("owner", "settings.digest_policy", payload, "current", now)
    assert engine.snapshot() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("digest_morning_enabled", 1),
        ("digest_evening_enabled", "true"),
        ("digest_weekly_weekday", True),
        ("digest_weekly_weekday", 7),
        ("digest_morning_time", "7:00"),
        ("digest_weekly_time", "24:00"),
        ("digest_evening_time", None),
        ("digest_morning_time", "07:00:00"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_policy_is_atomic_for_both_entrypoints(engine, now, field, value):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner", "settings.digest_policy", request(engine, **{field: value}), "invalid", now
        )
    assert engine.snapshot() == before
    with pytest.raises(DomainError, match="invalid_field"):
        await general(engine, now, "invalid-general", **{field: value})
    assert engine.snapshot() == before


@pytest.mark.parametrize("actor", ["parent", "adult", "child", "guest"])
@pytest.mark.asyncio
async def test_nonowner_cannot_change_policy(engine, now, actor):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor,
            "settings.digest_policy",
            request(engine, digest_morning_enabled=True),
            "wrong-role",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_timezone_module_and_policy_roundtrip_never_reuse_fingerprint(engine, now):
    original = policy.fingerprint(engine.snapshot())
    await general(engine, now, "zone", timezone="Europe/London")
    await general(engine, now, "zone-back", timezone="UTC")
    assert policy.fingerprint(engine.snapshot()) != original
    before = policy.fingerprint(engine.snapshot())
    modules = engine.snapshot()["settings"]["modules"]
    await general(engine, now, "enable-module", modules=[*modules, "digests"])
    await general(engine, now, "disable-module", modules=modules)
    assert policy.fingerprint(engine.snapshot()) != before
    before = policy.fingerprint(engine.snapshot())
    await general(engine, now, "enable-policy", digest_morning_enabled=True)
    await general(engine, now, "disable-policy", digest_morning_enabled=False)
    assert policy.fingerprint(engine.snapshot()) != before


@pytest.mark.asyncio
async def test_storage_failure_and_omission_preserve_policy(engine, now, store):
    payload = request(engine, digest_evening_enabled=True)
    before = deepcopy(engine.snapshot())
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("owner", "settings.digest_policy", payload, "disk", now)
    assert engine.snapshot() == before
    store.fail = False
    await engine.execute("owner", "settings.digest_policy", payload, "disk", now)
    saved = policy.values(engine.snapshot())
    await general(engine, now, "ordinary-save")
    assert policy.values(engine.snapshot()) == saved
