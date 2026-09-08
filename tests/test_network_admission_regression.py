"""Synthetic actual Engine API regression tests for local network admission.

Covers:
- approve, rename, remove, no-op, cancel lifecycle
- policy CAS with concurrent previews
- operation replay after later policy revision
- stale actor revision on preview, apply, and cancel
- corrupt inventory and bounded input validation
"""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network import admission
from custom_components.family_assistant.network.admission_inventory import (
    classify,
    observation_token,
)
from custom_components.family_assistant.network.inventory import build

DEV_1 = "02:11:22:33:44:01"
DEV_2 = "02:11:22:33:44:02"
DEV_3 = "02:11:22:33:44:03"
PROTECTED = "02:11:22:33:44:66"


async def setup_network(engine, now, client_macs=(DEV_1, DEV_2, DEV_3)):
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
                    "mac-address": m,
                    "active-address": f"198.51.100.{i + 10}",
                    "status": "bound",
                    "host-name": f"Host-{i}",
                }
                for i, m in enumerate((*client_macs, PROTECTED))
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


def preview_payload(e, now, changes=None, **kwargs):
    net = e.snapshot()["network"]
    adm = net.get("admission")
    policy_rev = adm["revision"] if adm else None
    actor_rev = e.snapshot()["members"]["owner"]["revision"]
    token = observation_token(net, now)
    if changes is None:
        changes = [{"mac": DEV_1, "approved": True, "label": "Device One"}]
    return {
        "actor_revision": actor_rev,
        "observation_token": token,
        "policy_revision": policy_rev,
        "changes": changes,
        **kwargs,
    }


@pytest.mark.asyncio
async def test_admission_lifecycle_approve_rename_remove_noop_cancel(engine, now):
    e = await setup_network(engine, now)

    # 1. Approve DEV_1
    req_approve = preview_payload(
        e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Alpha Device"}]
    )
    plan_1 = await e.execute("owner", "mikrotik.admission_preview", req_approve, "prev-1", now)
    assert plan_1["status"] == "preview"
    assert plan_1["policy_revision"] is None
    assert plan_1["backend_changed"] is False
    assert plan_1["changes"] == [{"mac": DEV_1, "before": None, "after": {"label": "Alpha Device"}}]

    apply_1 = await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_1["id"], "actor_revision": 1, "confirmed": True},
        "apply-1",
        now,
    )
    assert apply_1 == {"id": plan_1["id"], "status": "applied", "revision": 1}

    state = e.snapshot()
    assert state["network"]["admission"]["revision"] == 1
    assert state["network"]["admission"]["entries"] == {DEV_1: {"label": "Alpha Device"}}

    view_data = e.view("owner", now=now)["network"]["admission"]
    dev_1_view = next(d for d in view_data["devices"] if d["mac"] == DEV_1)
    assert dev_1_view["status"] == "approved"
    assert dev_1_view["label"] == "Alpha Device"

    # 2. Rename DEV_1
    req_rename = preview_payload(
        e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Alpha Device Renamed"}]
    )
    plan_2 = await e.execute("owner", "mikrotik.admission_preview", req_rename, "prev-2", now)
    assert plan_2["policy_revision"] == 1
    assert plan_2["changes"] == [
        {
            "mac": DEV_1,
            "before": {"label": "Alpha Device"},
            "after": {"label": "Alpha Device Renamed"},
        }
    ]

    apply_2 = await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_2["id"], "actor_revision": 1, "confirmed": True},
        "apply-2",
        now,
    )
    assert apply_2 == {"id": plan_2["id"], "status": "applied", "revision": 2}
    assert e.snapshot()["network"]["admission"]["entries"][DEV_1] == {
        "label": "Alpha Device Renamed"
    }

    # 3. No-op transitions reject at preview time
    # (a) Approving with identical label
    req_noop_rename = preview_payload(
        e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Alpha Device Renamed"}]
    )
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute("owner", "mikrotik.admission_preview", req_noop_rename, "noop-approve", now)

    # (b) Removing a device that is not currently in admission
    req_noop_remove = preview_payload(e, now, changes=[{"mac": DEV_2, "approved": False}])
    with pytest.raises(DomainError, match="not_found"):
        await e.execute("owner", "mikrotik.admission_preview", req_noop_remove, "noop-remove", now)

    # 4. Cancel a preview plan
    req_cancel = preview_payload(
        e, now, changes=[{"mac": DEV_2, "approved": True, "label": "Beta Device"}]
    )
    plan_cancel = await e.execute(
        "owner", "mikrotik.admission_preview", req_cancel, "prev-cancel", now
    )
    assert plan_cancel["status"] == "preview"

    cancel_res = await e.execute(
        "owner",
        "mikrotik.admission_cancel",
        {"id": plan_cancel["id"], "actor_revision": 1},
        "cancel-op",
        now,
    )
    assert cancel_res == {"id": plan_cancel["id"], "status": "cancelled"}
    assert e.snapshot()["network"]["admission_plans"][plan_cancel["id"]]["status"] == "cancelled"

    # Attempting to cancel already-cancelled plan raises invalid_transition
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute(
            "owner",
            "mikrotik.admission_cancel",
            {"id": plan_cancel["id"], "actor_revision": 1},
            "cancel-again",
            now,
        )

    # Attempting to apply a cancelled plan raises invalid_transition
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan_cancel["id"], "actor_revision": 1, "confirmed": True},
            "apply-cancelled",
            now,
        )

    # Policy remains at revision 2 with DEV_1 only
    assert e.snapshot()["network"]["admission"]["revision"] == 2
    assert DEV_2 not in e.snapshot()["network"]["admission"]["entries"]

    # 5. Remove DEV_1
    req_remove = preview_payload(e, now, changes=[{"mac": DEV_1, "approved": False}])
    plan_3 = await e.execute("owner", "mikrotik.admission_preview", req_remove, "prev-3", now)
    assert plan_3["changes"] == [
        {"mac": DEV_1, "before": {"label": "Alpha Device Renamed"}, "after": None}
    ]

    apply_3 = await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_3["id"], "actor_revision": 1, "confirmed": True},
        "apply-3",
        now,
    )
    assert apply_3 == {"id": plan_3["id"], "status": "applied", "revision": 3}
    assert e.snapshot()["network"]["admission"]["entries"] == {}

    dev_1_view_removed = next(
        d for d in e.view("owner", now=now)["network"]["admission"]["devices"] if d["mac"] == DEV_1
    )
    assert dev_1_view_removed["status"] == "unreviewed"
    assert dev_1_view_removed["label"] is None


@pytest.mark.asyncio
async def test_admission_policy_cas_concurrent_previews(engine, now):
    e = await setup_network(engine, now)

    # Both preview A and preview B are generated against initial state (policy_revision is None)
    req_a = preview_payload(e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Dev 1"}])
    req_b = preview_payload(e, now, changes=[{"mac": DEV_2, "approved": True, "label": "Dev 2"}])
    assert req_a["policy_revision"] is None
    assert req_b["policy_revision"] is None

    plan_a = await e.execute("owner", "mikrotik.admission_preview", req_a, "prev-a", now)
    plan_b = await e.execute("owner", "mikrotik.admission_preview", req_b, "prev-b", now)

    assert plan_a["policy_revision"] is None
    assert plan_b["policy_revision"] is None

    # Apply plan A first -> policy revision advances to 1
    res_a = await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_a["id"], "actor_revision": 1, "confirmed": True},
        "apply-a",
        now,
    )
    assert res_a["revision"] == 1
    assert e.snapshot()["network"]["admission"]["revision"] == 1

    # Attempt to apply plan B (which expects policy_revision None) must fail with conflict
    before_b = e.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan_b["id"], "actor_revision": 1, "confirmed": True},
            "apply-b",
            now,
        )
    assert e.snapshot() == before_b

    # A new preview using stale policy_revision None also fails with conflict
    with pytest.raises(DomainError, match="conflict"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            {**req_b, "policy_revision": None},
            "stale-prev",
            now,
        )

    # Fresh preview with current policy_revision 1 succeeds
    req_c = preview_payload(
        e, now, changes=[{"mac": DEV_2, "approved": True, "label": "Dev 2"}], policy_revision=1
    )
    plan_c = await e.execute("owner", "mikrotik.admission_preview", req_c, "prev-c", now)
    assert plan_c["policy_revision"] == 1

    res_c = await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_c["id"], "actor_revision": 1, "confirmed": True},
        "apply-c",
        now,
    )
    assert res_c["revision"] == 2
    entries = e.snapshot()["network"]["admission"]["entries"]
    assert DEV_1 in entries and DEV_2 in entries

    # Concurrent previews modifying the SAME device at revision 2
    req_d = preview_payload(
        e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Dev 1 Variant D"}]
    )
    req_e = preview_payload(
        e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Dev 1 Variant E"}]
    )
    plan_d = await e.execute("owner", "mikrotik.admission_preview", req_d, "prev-d", now)
    plan_e = await e.execute("owner", "mikrotik.admission_preview", req_e, "prev-e", now)

    await e.execute(
        "owner",
        "mikrotik.admission_apply",
        {"id": plan_d["id"], "actor_revision": 1, "confirmed": True},
        "apply-d",
        now,
    )
    assert e.snapshot()["network"]["admission"]["revision"] == 3

    # Applying plan_e must fail because policy revision moved from 2 to 3
    with pytest.raises(DomainError, match="conflict"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan_e["id"], "actor_revision": 1, "confirmed": True},
            "apply-e",
            now,
        )


@pytest.mark.asyncio
async def test_admission_operation_replay_after_later_policy_revision(engine, now):
    e = await setup_network(engine, now)

    # Preview and apply op 1
    req_1 = preview_payload(e, now, changes=[{"mac": DEV_1, "approved": True, "label": "Dev 1"}])
    plan_1 = await e.execute("owner", "mikrotik.admission_preview", req_1, "op-prev-1", now)

    payload_apply_1 = {"id": plan_1["id"], "actor_revision": 1, "confirmed": True}
    res_apply_1 = await e.execute(
        "owner", "mikrotik.admission_apply", payload_apply_1, "op-apply-1", now
    )
    assert res_apply_1 == {"id": plan_1["id"], "status": "applied", "revision": 1}

    # Immediate replay of op-apply-1 returns saved receipt
    replay_1 = await e.execute(
        "owner", "mikrotik.admission_apply", payload_apply_1, "op-apply-1", now
    )
    assert replay_1 == res_apply_1

    # Apply a subsequent operation that advances the policy revision to 2
    req_2 = preview_payload(e, now, changes=[{"mac": DEV_2, "approved": True, "label": "Dev 2"}])
    plan_2 = await e.execute("owner", "mikrotik.admission_preview", req_2, "op-prev-2", now)
    payload_apply_2 = {"id": plan_2["id"], "actor_revision": 1, "confirmed": True}
    res_apply_2 = await e.execute(
        "owner", "mikrotik.admission_apply", payload_apply_2, "op-apply-2", now
    )
    assert res_apply_2["revision"] == 2
    assert e.snapshot()["network"]["admission"]["revision"] == 2

    # Now replay op-apply-1 after later policy revision:
    # authorize_replay rejects because saved revision (1) != current policy revision (2)
    state_before = e.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("owner", "mikrotik.admission_apply", payload_apply_1, "op-apply-1", now)
    assert e.snapshot() == state_before

    # Replay preview after plan is applied rejects with conflict
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("owner", "mikrotik.admission_preview", req_1, "op-prev-1", now)

    # Replay preview after expiry rejects with proposal_expired
    req_3 = preview_payload(e, now, changes=[{"mac": DEV_3, "approved": True, "label": "Dev 3"}])
    await e.execute("owner", "mikrotik.admission_preview", req_3, "op-prev-3", now)
    with pytest.raises(DomainError, match="proposal_expired"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            req_3,
            "op-prev-3",
            now + timedelta(minutes=3),
        )


@pytest.mark.asyncio
async def test_admission_stale_actor_revision(engine, now):
    e = await setup_network(engine, now)

    # Preview with stale or mismatched actor revision rejects with conflict
    req_stale = preview_payload(e, now, actor_revision=99)
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("owner", "mikrotik.admission_preview", req_stale, "prev-stale-actor", now)

    # Valid preview at actor revision 1
    req_valid = preview_payload(e, now)
    plan = await e.execute("owner", "mikrotik.admission_preview", req_valid, "prev-ok", now)
    assert e.snapshot()["network"]["admission_plans"][plan["id"]]["actor_revision"] == 1

    # Bump owner revision to 2
    def bump_actor(ctx):
        ctx.state["members"]["owner"]["revision"] += 1

    await e.system_update("bump-actor-rev", now, bump_actor)
    assert e.snapshot()["members"]["owner"]["revision"] == 2

    # Case A: Apply with old actor_revision 1 -> _actor rejects with conflict
    with pytest.raises(DomainError, match="conflict"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan["id"], "actor_revision": 1, "confirmed": True},
            "apply-old-actor-rev",
            now,
        )

    # Case B: Apply with new actor_revision 2 -> _current_plan rejects with forbidden
    # because plan was locked to actor revision 1
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan["id"], "actor_revision": 2, "confirmed": True},
            "apply-mismatched-plan-actor-rev",
            now,
        )

    # Case C: Cancel with old actor_revision 1 -> _actor rejects with conflict
    with pytest.raises(DomainError, match="conflict"):
        await e.execute(
            "owner",
            "mikrotik.admission_cancel",
            {"id": plan["id"], "actor_revision": 1},
            "cancel-old-actor-rev",
            now,
        )

    # Case D: Cancel with new actor_revision 2 -> _current_plan rejects with forbidden
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "owner",
            "mikrotik.admission_cancel",
            {"id": plan["id"], "actor_revision": 2},
            "cancel-mismatched-plan-actor-rev",
            now,
        )


@pytest.mark.asyncio
async def test_admission_corrupt_inventory_and_bounded_inputs(engine, now):
    e = await setup_network(engine, now)

    # 1. Bounded preview payload checks
    # (a) Empty changes list
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(e, now, changes=[]),
            "bad-empty-changes",
            now,
        )

    # (b) Oversized changes list (> 100)
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(
                e,
                now,
                changes=[{"mac": DEV_1, "approved": True, "label": "X"}] * 101,
            ),
            "bad-oversized-changes",
            now,
        )

    # (c) Duplicate MAC in changes list
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(
                e,
                now,
                changes=[
                    {"mac": DEV_1, "approved": True, "label": "X"},
                    {"mac": DEV_1, "approved": True, "label": "Y"},
                ],
            ),
            "bad-duplicate-mac",
            now,
        )

    # (d) Invalid MAC format
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(
                e,
                now,
                changes=[{"mac": "invalid:mac:address", "approved": True, "label": "X"}],
            ),
            "bad-mac-format",
            now,
        )

    # (e) Non-boolean approved (truthy integer or string)
    for bad_approved in (1, "true", None):
        with pytest.raises(DomainError, match="invalid_field"):
            await e.execute(
                "owner",
                "mikrotik.admission_preview",
                preview_payload(
                    e,
                    now,
                    changes=[{"mac": DEV_1, "approved": bad_approved, "label": "X"}],
                ),
                f"bad-approved-{bad_approved}",
                now,
            )

    # (f) Label provided when approved is False
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(
                e,
                now,
                changes=[{"mac": DEV_1, "approved": False, "label": "Label Not Allowed"}],
            ),
            "bad-label-on-disapprove",
            now,
        )

    # (g) Empty or whitespace label
    for bad_label in ("", "   ", "\t\n"):
        with pytest.raises(DomainError, match="invalid_field"):
            await e.execute(
                "owner",
                "mikrotik.admission_preview",
                preview_payload(
                    e,
                    now,
                    changes=[{"mac": DEV_1, "approved": True, "label": bad_label}],
                ),
                f"bad-label-empty-{hash(bad_label)}",
                now,
            )

    # (h) Oversized label (> 160 chars)
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(
                e,
                now,
                changes=[{"mac": DEV_1, "approved": True, "label": "A" * 161}],
            ),
            "bad-oversized-label",
            now,
        )

    # (i) Non-boolean replace_backend
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(e, now, replace_backend="yes"),
            "bad-replace-backend",
            now,
        )

    # (j) Extra unknown field in preview payload
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "owner",
            "mikrotik.admission_preview",
            preview_payload(e, now, unexpected_field="malicious"),
            "bad-unknown-field",
            now,
        )

    # 2. Corrupt inventory bounded handling
    # (a) Corrupt backend (not 64-character sha256)
    bad_net_backend = deepcopy(e.snapshot()["network"])
    bad_net_backend["backend"] = "not-a-sha256-hash"
    assert classify(bad_net_backend, now)["status"] == "unavailable"
    with pytest.raises(DomainError, match="network_response"):
        observation_token(bad_net_backend, now)

    # (b) Corrupt observed_at timestamp
    bad_net_time = deepcopy(e.snapshot()["network"])
    bad_net_time["inventory"]["observed_at"] = "invalid-date-string"
    assert classify(bad_net_time, now)["status"] == "unavailable"
    with pytest.raises(DomainError, match="network_response"):
        observation_token(bad_net_time, now)

    # (c) Stale observed_at (> 180 seconds old)
    bad_net_stale = deepcopy(e.snapshot()["network"])
    bad_net_stale["inventory"]["observed_at"] = (now - timedelta(seconds=181)).isoformat()
    assert classify(bad_net_stale, now)["status"] == "stale"
    with pytest.raises(DomainError, match="network_stale"):
        observation_token(bad_net_stale, now)

    # (d) Oversized devices list in inventory (> 1000 items)
    bad_net_devices = deepcopy(e.snapshot()["network"])
    bad_net_devices["inventory"]["devices"] = [
        {"mac": f"02:00:00:00:{i // 256:02x}:{i % 256:02x}"} for i in range(1001)
    ]
    assert classify(bad_net_devices, now)["status"] == "unavailable"

    # (e) Corrupt device structure in inventory
    for bad_dev in (
        "not-a-dict",
        {"mac": "invalid-mac"},
        {"mac": DEV_1, "addresses": ["999.999.999.999"]},
        {"mac": DEV_1, "addresses": [f"198.51.100.{i}" for i in range(17)]},
        {"mac": DEV_1, "candidate_name": "N" * 161},
        {"mac": DEV_1, "warnings": ["w"] * 17},
        {"mac": DEV_1, "warnings": [123]},
    ):
        bad_dev_net = deepcopy(e.snapshot()["network"])
        bad_dev_net["inventory"]["devices"] = [bad_dev]
        assert classify(bad_dev_net, now)["status"] == "unavailable"

    # (f) Conflicting duplicate MAC in inventory devices
    dup_dev_net = deepcopy(e.snapshot()["network"])
    dup_dev_net["inventory"]["devices"] = [
        {"mac": DEV_1, "addresses": ["198.51.100.10"], "protected": False},
        {"mac": DEV_1, "addresses": ["198.51.100.11"], "protected": False},
    ]
    assert classify(dup_dev_net, now)["status"] == "unavailable"

    # (g) Corrupt admission policy in state gracefully handled in view
    corrupt_policy_state = deepcopy(e.snapshot())
    corrupt_policy_state["network"]["admission"] = {
        "backend": "a" * 64,
        "revision": 1,
        "updated_at": now.isoformat(),
        "entries": {DEV_1: {"label": "A" * 161}},  # label exceeds 160
    }
    view_res = admission.view(corrupt_policy_state, corrupt_policy_state["members"]["owner"], now)
    assert view_res["status"] == "unavailable"
    assert view_res["can_edit"] is False
    assert view_res["devices"] == []
    assert view_res["plans"] == []

    # 3. Capacity limits
    # (a) MAX_PLANS capacity reached on preview
    cap_net = e.snapshot()
    cap_net["network"]["admission_plans"] = {f"plan-{i}": {"id": f"plan-{i}"} for i in range(1000)}
    engine_cap = Engine(cap_net, e._persist)
    with pytest.raises(DomainError, match="capacity_reached"):
        await engine_cap.execute(
            "owner", "mikrotik.admission_preview", preview_payload(engine_cap, now), "prev-cap", now
        )

    # (b) MAX_ENTRIES capacity reached on apply
    req_cap_apply = preview_payload(e, now)
    plan_cap = await e.execute(
        "owner", "mikrotik.admission_preview", req_cap_apply, "prev-apply-cap", now
    )

    # Inject 1000 entries into admission
    def seed_1000_entries(ctx):
        ctx.state["network"]["admission"] = {
            "backend": "a" * 64,
            "revision": 1,
            "updated_at": now.isoformat(),
            "entries": {
                f"02:00:00:{i // 65536:02X}:{(i // 256) % 256:02X}:{i % 256:02X}": {
                    "label": f"Dev {i}"
                }
                for i in range(1000)
            },
        }
        # align plan policy_revision to 1
        ctx.state["network"]["admission_plans"][plan_cap["id"]]["policy_revision"] = 1

    await e.system_update("seed-1000", now, seed_1000_entries)

    with pytest.raises(DomainError, match="capacity_reached"):
        await e.execute(
            "owner",
            "mikrotik.admission_apply",
            {"id": plan_cap["id"], "actor_revision": 1, "confirmed": True},
            "apply-cap-reached",
            now,
        )
