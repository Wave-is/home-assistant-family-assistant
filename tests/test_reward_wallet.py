"""Tests for bounded pure reward wallet helper."""

import pytest

from custom_components.family_assistant.domain.reward_wallet import balance
from custom_components.family_assistant.domain.validation import DomainError


def test_reservations_spending_and_refund():
    court = [
        {"id": "c1", "member": "alice", "points": 50, "status": "active", "meta": "clean room"},
        {"id": "c2", "member": "alice", "points": 20, "status": "reversed"},
        {"id": "c3", "member": "alice", "points": -10, "status": "active"},
    ]
    redemptions = [
        {"id": "r1", "member": "alice", "cost": 15, "status": "requested"},
        {"id": "r2", "member": "alice", "cost": 5, "status": "approved"},
        {"id": "r3", "member": "alice", "cost": 10, "status": "fulfilled"},
        {"id": "r4", "member": "alice", "cost": 7, "status": "refunded"},
        {"id": "r5", "member": "alice", "cost": 8, "status": "rejected"},
        {"id": "r6", "member": "alice", "cost": 9, "status": "cancelled"},
        {"id": "r7", "member": "alice", "cost": 6, "status": "expired"},
    ]
    result = balance(court, redemptions, "alice")
    assert result == {
        "earned": 40,
        "reserved": 20,
        "spent": 10,
        "net": 10,
        "available": 10,
    }


def test_negative_debt_preserved():
    court = [
        {"id": "c1", "member": "alice", "points": 30, "status": "reversed"},
    ]
    redemptions = [
        {"id": "r1", "member": "alice", "cost": 50, "status": "fulfilled"},
    ]
    res = balance(court, redemptions, "alice")
    assert res == {
        "earned": 0,
        "reserved": 0,
        "spent": 50,
        "net": -50,
        "available": 0,
    }


def test_two_members_isolation():
    court = [
        {"id": "c1", "member": "alice", "points": 25, "status": "active"},
        {"id": "c2", "member": "bob", "points": 40, "status": "active"},
    ]
    redemptions = [
        {"id": "r1", "member": "alice", "cost": 10, "status": "fulfilled"},
        {"id": "r2", "member": "bob", "cost": 15, "status": "requested"},
    ]
    alice_res = balance(court, redemptions, "alice")
    bob_res = balance(court, redemptions, "bob")
    assert alice_res == {"earned": 25, "reserved": 0, "spent": 10, "net": 15, "available": 15}
    assert bob_res == {"earned": 40, "reserved": 15, "spent": 0, "net": 25, "available": 25}


def test_opaque_guest_like_ids_and_no_role_validation():
    court = [{"id": "guest_uuid_1234", "member": "guest-42", "points": 10, "status": "active"}]
    redemptions = [{"id": "red_guest_99", "member": "guest-42", "cost": 5, "status": "requested"}]
    res = balance(court, redemptions, "guest-42")
    assert res["net"] == 5
    assert res["available"] == 5


def test_no_mutation():
    court = [{"id": "c1", "member": "alice", "points": 15, "status": "active"}]
    redemptions = [{"id": "r1", "member": "alice", "cost": 5, "status": "requested"}]
    c_copy = [{"id": "c1", "member": "alice", "points": 15, "status": "active"}]
    r_copy = [{"id": "r1", "member": "alice", "cost": 5, "status": "requested"}]
    balance(court, redemptions, "alice")
    assert court == c_copy
    assert redemptions == r_copy


def test_duplicates_rejected():
    court_dup = [
        {"id": "c1", "member": "alice", "points": 10, "status": "active"},
        {"id": "c1", "member": "bob", "points": 10, "status": "active"},
    ]
    with pytest.raises(DomainError):
        balance(court_dup, [], "alice")

    red_dup = [
        {"id": "r1", "member": "alice", "cost": 5, "status": "requested"},
        {"id": "r1", "member": "alice", "cost": 5, "status": "approved"},
    ]
    with pytest.raises(DomainError):
        balance([], red_dup, "alice")


@pytest.mark.parametrize(
    "c, r, m",
    [
        ("not_a_list", [], "alice"),
        ([], "not_a_list", "alice"),
        ([], [], "   "),
        ([], [], " alice"),
        ([], [], "alice "),
        ([], [], "a" * 81),
        ([], [], 123),
        ([{"id": "c1", "member": "bob", "points": 0, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": 101, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": -101, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": True, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": "10", "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": 10.5, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": "bob", "points": 10, "status": "unknown"}], [], "alice"),
        ([{"id": " c1", "member": "bob", "points": 10, "status": "active"}], [], "alice"),
        ([{"id": "c1", "member": " bob", "points": 10, "status": "active"}], [], "alice"),
        ([{"id": "c1", "points": 10, "status": "active"}], [], "alice"),
        ([123], [], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": 0, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": 10001, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": True, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": "10", "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": 5.0, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "cost": 5, "status": "pending"}], "alice"),
        ([], [{"id": " r1", "member": "bob", "cost": 5, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob ", "cost": 5, "status": "requested"}], "alice"),
        ([], [{"id": "r1", "member": "bob", "status": "requested"}], "alice"),
        ([], [123], "alice"),
    ],
)
def test_strict_invalid_records_and_malformed_fields(c, r, m):
    with pytest.raises(DomainError):
        balance(c, r, m)
