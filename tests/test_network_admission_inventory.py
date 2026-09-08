"""Tests for network admission and inventory classification."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.admission_inventory import (
    classify,
    observation_token,
)

BACKEND_A = "a" * 64
BACKEND_B = "b" * 64


def make_network(now, *, backend=BACKEND_A, devices=None, protected_macs=None, admission=None):
    return {
        "backend": backend,
        "protected_macs": protected_macs if protected_macs is not None else [],
        "inventory": {
            "observed_at": now.isoformat(),
            "devices": devices
            if devices is not None
            else [
                {
                    "mac": "02:11:22:33:44:01",
                    "addresses": ["198.51.100.10"],
                    "candidate_name": "Phone",
                    "warnings": ["locally_administered"],
                    "protected": False,
                }
            ],
            "capabilities": {},
            "fasttrack": False,
            "ipv6": "disabled",
        },
        **({"admission": admission} if admission is not None else {}),
    }


def test_fresh_valid_classification_and_token(now):
    network = make_network(
        now,
        admission={
            "backend": BACKEND_A,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "Alice Phone"}},
        },
    )
    result = classify(network, now)
    assert result["status"] == "fresh"
    assert result["backend"] == BACKEND_A
    assert result["observed_at"] == now.isoformat()
    assert isinstance(result["token"], str) and len(result["token"]) == 64
    assert result["counts"] == {"protected": 0, "approved": 1, "unreviewed": 0}
    assert len(result["devices"]) == 1

    dev = result["devices"][0]
    assert dev == {
        "mac": "02:11:22:33:44:01",
        "addresses": ["198.51.100.10"],
        "candidate_name": "Phone",
        "warnings": ["locally_administered"],
        "status": "approved",
        "label": "Alice Phone",
    }
    assert observation_token(network, now) == result["token"]


def test_strict_bool_handling(now):
    # Non-literal booleans must fail projection to unavailable empty
    for bad_bool in ("true", "yes", 1, 0, "false"):
        net = make_network(
            now,
            devices=[
                {
                    "mac": "02:11:22:33:44:01",
                    "addresses": ["198.51.100.10"],
                    "protected": bad_bool,
                }
            ],
        )
        res = classify(net, now)
        assert res["status"] == "unavailable"
        assert res["token"] is None
        assert res["devices"] == []
        with pytest.raises(DomainError, match="network_response"):
            observation_token(net, now)

    # Literal True accepted
    net_true = make_network(
        now,
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "protected": True,
            }
        ],
    )
    res_true = classify(net_true, now)
    assert res_true["status"] == "fresh"
    assert res_true["devices"][0]["status"] == "protected"
    assert res_true["counts"]["protected"] == 1


def test_strict_time_boundaries_and_stale(now):
    # Exactly 0 age is fresh
    net = make_network(now)
    assert classify(net, now)["status"] == "fresh"

    # Exactly 180s age is fresh
    net_180 = make_network(now - timedelta(seconds=180))
    res_180 = classify(net_180, now)
    assert res_180["status"] == "fresh"
    assert res_180["token"] is not None

    # Future age (< 0) is stale (token MUST be null)
    net_future = make_network(now + timedelta(seconds=5))
    res_future = classify(net_future, now)
    assert res_future["status"] == "stale"
    assert res_future["token"] is None
    assert len(res_future["devices"]) == 1
    with pytest.raises(DomainError, match="network_stale"):
        observation_token(net_future, now)

    # Over 180s age (> 180) is stale
    net_stale = make_network(now - timedelta(seconds=181))
    res_stale = classify(net_stale, now)
    assert res_stale["status"] == "stale"
    assert res_stale["token"] is None
    with pytest.raises(DomainError, match="network_stale"):
        observation_token(net_stale, now)

    # Naive timestamp fails schema to unavailable
    naive_now = datetime(2026, 9, 8, 12, 0)
    assert classify(net, naive_now)["status"] == "unavailable"


def test_duplicate_canonical_mac_dedup_and_reject(now):
    dev1 = {
        "mac": "02:11:22:33:44:01",
        "addresses": ["198.51.100.10"],
        "candidate_name": "Phone",
        "warnings": ["locally_administered"],
        "protected": False,
    }
    # Exact duplicate: deduplicates safely
    net_dedup = make_network(now, devices=[dev1, deepcopy(dev1)])
    res_dedup = classify(net_dedup, now)
    assert res_dedup["status"] == "fresh"
    assert len(res_dedup["devices"]) == 1

    # Conflicting duplicate: address conflict
    dev_conflict_ip = deepcopy(dev1)
    dev_conflict_ip["addresses"] = ["198.51.100.20"]
    net_conflict_ip = make_network(now, devices=[dev1, dev_conflict_ip])
    assert classify(net_conflict_ip, now)["status"] == "unavailable"

    # Conflicting duplicate: protected conflict
    dev_conflict_prot = deepcopy(dev1)
    dev_conflict_prot["protected"] = True
    net_conflict_prot = make_network(now, devices=[dev1, dev_conflict_prot])
    assert classify(net_conflict_prot, now)["status"] == "unavailable"


def test_no_approval_from_suggestions_or_comments(now):
    net = make_network(
        now,
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "candidate_name": "Known Guest",
                "suggested_name": "Known Guest",
                "hostnames": ["guest-phone"],
                "comments": ["Approved by dad"],
                "leases": [{"dynamic": "false", "status": "bound"}],
            }
        ],
    )
    res = classify(net, now)
    assert res["status"] == "fresh"
    dev = res["devices"][0]
    assert dev["status"] == "unreviewed"
    assert dev["label"] is None
    assert dev["candidate_name"] == "Known Guest"
    assert res["counts"] == {"protected": 0, "approved": 0, "unreviewed": 1}


def test_protected_precedence_over_approval(now):
    net = make_network(
        now,
        protected_macs=["02:11:22:33:44:01"],
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "protected": False,
            }
        ],
        admission={
            "backend": BACKEND_A,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "Admitted Device"}},
        },
    )
    res = classify(net, now)
    assert res["status"] == "fresh"
    dev = res["devices"][0]
    assert dev["status"] == "protected"
    assert res["counts"] == {"protected": 1, "approved": 0, "unreviewed": 0}


def test_backend_mismatch_disables_approvals(now):
    net = make_network(
        now,
        backend=BACKEND_A,
        admission={
            "backend": BACKEND_B,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "Admitted Device"}},
        },
    )
    res = classify(net, now)
    assert res["status"] == "fresh"
    dev = res["devices"][0]
    assert dev["status"] == "unreviewed"
    assert dev["label"] is None
    assert res["counts"] == {"protected": 0, "approved": 0, "unreviewed": 1}


def test_token_stable_across_allowlist_edits(now):
    net1 = make_network(now, admission=None)
    token1 = observation_token(net1, now)

    # Adding admission entry does NOT change observation token
    net2 = make_network(
        now,
        admission={
            "backend": BACKEND_A,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "New Label"}},
        },
    )
    token2 = observation_token(net2, now)
    assert token1 == token2

    # Changing admission label/revision does NOT change observation token
    net3 = make_network(
        now,
        admission={
            "backend": BACKEND_A,
            "revision": 2,
            "entries": {"02:11:22:33:44:01": {"label": "Updated Label"}},
        },
    )
    token3 = observation_token(net3, now)
    assert token1 == token3

    # Changing current observation time DOES change token
    net_diff_time = make_network(now - timedelta(seconds=10))
    assert observation_token(net_diff_time, now) != token1

    # Changing backend source DOES change token
    net_diff_backend = make_network(now, backend=BACKEND_B)
    assert observation_token(net_diff_backend, now) != token1

    # Changing protected device DOES change token
    net_diff_prot = make_network(now, protected_macs=["02:11:22:33:44:01"])
    assert observation_token(net_diff_prot, now) != token1


def test_input_immutability(now):
    net = make_network(
        now,
        protected_macs=["02:11:22:33:44:02"],
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "candidate_name": "Phone",
                "warnings": ["locally_administered", "custom_remote_warning"],
                "protected": False,
            }
        ],
        admission={
            "backend": BACKEND_A,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "Phone Label"}},
        },
    )
    original = deepcopy(net)
    classify(net, now)
    observation_token(net, now)
    assert net == original


def test_malformed_and_schema_failure_conditions(now):
    # Invalid backend hash
    assert classify({"backend": "invalid", "inventory": {}}, now)["status"] == "unavailable"

    # Missing inventory
    assert classify({"backend": BACKEND_A}, now)["status"] == "unavailable"

    # Unknown device / invalid MAC must not be silently omitted; must fail entire projection
    net_bad_mac = make_network(
        now,
        devices=[
            {"mac": "01:00:5E:00:00:01", "addresses": ["198.51.100.10"]},  # multicast MAC
        ],
    )
    assert classify(net_bad_mac, now)["status"] == "unavailable"

    # Invalid address in addresses
    net_bad_ip = make_network(
        now,
        devices=[{"mac": "02:11:22:33:44:01", "addresses": ["not-an-ip"]}],
    )
    assert classify(net_bad_ip, now)["status"] == "unavailable"

    # More than 16 unique addresses
    net_17_ips = make_network(
        now,
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": [f"198.51.100.{i}" for i in range(1, 18)],
            }
        ],
    )
    assert classify(net_17_ips, now)["status"] == "unavailable"

    # Candidate name > 160 chars
    net_long_name = make_network(
        now,
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "candidate_name": "A" * 161,
            }
        ],
    )
    assert classify(net_long_name, now)["status"] == "unavailable"

    # Admission label > 160 chars
    net_long_label = make_network(
        now,
        admission={
            "backend": BACKEND_A,
            "revision": 1,
            "entries": {"02:11:22:33:44:01": {"label": "X" * 161}},
        },
    )
    assert classify(net_long_label, now)["status"] == "unavailable"


def test_inventory_bounds_and_warning_sanitization(now):
    # Remote warning strings filtered
    net_warn = make_network(
        now,
        devices=[
            {
                "mac": "02:11:22:33:44:01",
                "addresses": ["198.51.100.10"],
                "warnings": [
                    "locally_administered",
                    "rogue_dhcp",
                    "multiple_addresses",
                    "custom_alert",
                ],
            }
        ],
    )
    res_warn = classify(net_warn, now)
    assert res_warn["devices"][0]["warnings"] == ["locally_administered", "multiple_addresses"]

    # Oversize input is unavailable, never a silently truncated complete inventory.
    many_devs = [
        {
            "mac": f"02:00:00:{(i >> 16) & 0xFF:02X}:{(i >> 8) & 0xFF:02X}:{i & 0xFF:02X}",
            "addresses": ["203.0.113.1"],
        }
        for i in range(1005)
    ]
    net_many = make_network(now, devices=many_devs)
    res_many = classify(net_many, now)
    assert res_many["status"] == "unavailable"
    assert res_many["token"] is None
    assert res_many["devices"] == []
    assert sum(res_many["counts"].values()) == 0


def test_unobserved_management_anchor_also_invalidates_review_token(now):
    before = make_network(now)
    after = deepcopy(before)
    after["protected_macs"] = ["02:11:22:33:44:99"]
    assert observation_token(before, now) != observation_token(after, now)


@pytest.mark.parametrize("field", ["protected_macs", "addresses", "warnings"])
def test_oversized_raw_lists_are_rejected_before_deduplication(now, field):
    value = make_network(now)
    if field == "protected_macs":
        value[field] = ["02:11:22:33:44:99"] * 1001
    else:
        value["inventory"]["devices"][0][field] = (
            ["198.51.100.2"] if field == "addresses" else ["unknown_device"]
        ) * 17
    assert classify(value, now)["status"] == "unavailable"
