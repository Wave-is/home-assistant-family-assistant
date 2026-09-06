"""No writes: lease selection, conflicts, comments, expiry and protected devices."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.leases import fingerprint, preview, readback_match


def data():
    return {
        "leases": [
            {
                ".id": "*1",
                "mac-address": "02:11:22:33:44:55",
                "address": "198.51.100.10",
                "server": "lan",
                "dynamic": "true",
                "status": "bound",
                "comment": "Old comment",
            }
        ],
        "servers": [{"name": "lan", "interface": "bridge-lan", "disabled": "false"}],
        "networks": [{"address": "198.51.100.0/24"}],
        "addresses": [{"address": "198.51.100.1/24", "interface": "bridge-lan"}],
    }


def test_preview_preserves_comments_and_source(now):
    source = data()
    prior = deepcopy(source)
    plan = preview(source, [{"id": "*1", "comment": "Suggested by HA"}], now)
    assert source == prior
    assert plan["targets"][0]["comment"] == "Old comment"
    assert plan["targets"][0]["convert"] and plan["requires_dhcp_recovery_consent"]
    assert plan["expires_at"].endswith("08:05:00+00:00")
    replaced = preview(
        source, [{"id": "*1", "comment": "Chosen name", "replace_comment": True}], now
    )
    assert replaced["targets"][0]["comment"] == "Chosen name"


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-ip",
        "duplicate-mac",
        "wrong-subnet",
        "server-disabled",
        "wrong-interface",
        "router-ip",
        "unbound",
        "active-mismatch",
        "server-mismatch",
    ],
)
def test_conflicts_fail_closed(now, mutation):
    source = data()
    if mutation.startswith("duplicate"):
        other = {**source["leases"][0], ".id": "*2"}
        if mutation == "duplicate-ip":
            other["mac-address"] = "02:11:22:33:44:66"
        else:
            other["address"] = "198.51.100.11"
        source["leases"].append(other)
    elif mutation == "wrong-subnet":
        source["leases"][0]["address"] = "203.0.113.10"
    elif mutation == "server-disabled":
        source["servers"][0]["disabled"] = "true"
    elif mutation == "wrong-interface":
        source["servers"][0]["interface"] = "different"
    elif mutation == "router-ip":
        source["leases"][0]["address"] = "198.51.100.1"
    elif mutation == "unbound":
        source["leases"][0]["status"] = "offered"
    elif mutation == "active-mismatch":
        source["leases"][0]["active-mac-address"] = "02:11:22:33:44:66"
    else:
        source["leases"][0]["active-server"] = "different"
    with pytest.raises(DomainError):
        preview(source, [{"id": "*1"}], now)


def test_noop_static_and_readback_new_id(now):
    source = data()
    source["leases"][0]["dynamic"] = "false"
    plan = preview(source, [{"id": "*1"}], now)
    assert not plan["targets"][0]["changed"] and not plan["requires_dhcp_recovery_consent"]
    source["leases"][0][".id"] = "*A"
    row = readback_match(plan["targets"][0], source["leases"])
    assert row[".id"] == "*A"
    assert fingerprint(row) == plan["targets"][0]["fingerprint"]
    source["leases"].append({**row, ".id": "*B"})
    with pytest.raises(DomainError, match="network_conflict"):
        readback_match(plan["targets"][0], source["leases"])


def test_protection_selection_and_comment_validation(now):
    for selection in (
        [{"id": "*1"}, {"id": "*1"}],
        [{"id": "*1/../reboot"}],
        [{"id": "*1", "comment": "line\nbreak"}],
        [{"id": "*1", "replace_comment": "true"}],
    ):
        with pytest.raises(DomainError):
            preview(data(), selection, now)
    with pytest.raises(DomainError, match="network_protected"):
        preview(data(), [{"id": "*1"}], now, protected_macs=["02:11:22:33:44:55"])
    source = data()
    source["interfaces"] = [{"mac-address": "02:11:22:33:44:55"}]
    with pytest.raises(DomainError, match="network_protected"):
        preview(source, [{"id": "*1"}], now)
