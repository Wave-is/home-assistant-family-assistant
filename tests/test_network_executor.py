"""Selected-record changes with uncertain transport, concurrent edits and disk faults."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.lease_executor import LeaseExecutor
from custom_components.family_assistant.network.leases import preview


class Router:
    def __init__(self, *, dynamic=True):
        self.tables = {
            "leases": [
                {
                    ".id": "*1",
                    "address": "198.51.100.10",
                    "mac-address": "02:11:22:33:44:55",
                    "server": "lan",
                    "dynamic": str(dynamic).lower(),
                    "status": "bound",
                    "comment": "Original",
                }
            ],
            "servers": [{"name": "lan", "interface": "lan"}],
            "networks": [{"address": "198.51.100.0/24"}],
            "addresses": [{"address": "198.51.100.1/24", "interface": "lan"}],
            "interfaces": [],
        }
        self.calls = []
        self.fail = None
        self.external = False
        self.hook = None

    async def read(self, name):
        return deepcopy(self.tables[name])

    def row(self, target):
        return next(r for r in self.tables["leases"] if r[".id"] == target)

    async def make_static(self, target):
        self.calls.append(("static", target))
        self.row(target).update(dynamic="false")
        self.row(target)[".id"] = "*A"
        if self.hook:
            self.hook()
        if self.fail == "static-timeout":
            raise DomainError("network_timeout")

    async def set_comment(self, target, comment):
        self.calls.append(("comment", target, comment))
        if self.external:
            self.row(target)["comment"] = "User's new comment"
            raise DomainError("network_timeout")
        if self.fail == "comment-rejected":
            raise DomainError("network_permission")
        if self.fail == "comment-second" and target == "*2":
            raise DomainError("network_permission")
        self.row(target)["comment"] = comment
        if self.fail == "comment-timeout":
            raise DomainError("network_timeout")

    async def remove_reservation(self, target):
        self.calls.append(("remove", target))
        self.tables["leases"].remove(self.row(target))


class Journal:
    def __init__(self):
        self.saved = None
        self.calls = 0
        self.fail_at = None

    async def save(self, state):
        self.calls += 1
        if self.calls == self.fail_at:
            raise OSError("synthetic storage fault")
        self.saved = deepcopy(state)


def plan(router, now):
    return preview(router.tables, [{"id": "*1", "comment": "Chosen", "replace_comment": True}], now)


@pytest.mark.asyncio
@pytest.mark.parametrize("dynamic,phase", [(True, "converting"), (False, "commenting")])
async def test_permission_revoked_while_persisting_intent_stops_write(now, dynamic, phase):
    router, journal = Router(dynamic=dynamic), Journal()
    authorized = True

    async def persist(progress):
        nonlocal authorized
        await journal.save(progress)
        if progress["targets"][0]["phase"] == phase:
            authorized = False

    result = await LeaseExecutor(router, plan(router, now), persist, lambda: authorized).run(
        now, dhcp_recovery=True
    )
    assert result["status"] == "review_required" and not router.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "static-timeout", "comment-timeout"])
async def test_readback_success_even_when_transport_loses_reply(now, failure):
    router, journal = Router(), Journal()
    router.fail = failure
    selected = plan(router, now)
    executor = LeaseExecutor(router, selected, journal.save, lambda: True)
    result = await executor.run(now, dhcp_recovery=True)
    assert result["status"] == "applied"
    assert router.calls == [("static", "*1"), ("comment", "*A", "Chosen")]
    assert router.tables["leases"][0]["comment"] == "Chosen"
    again = await executor.run(now, journal.saved, dhcp_recovery=True)
    assert again == result and len(router.calls) == 2


@pytest.mark.asyncio
async def test_rollback_removes_only_new_reservation_with_explicit_consent(now):
    router, journal = Router(), Journal()
    router.fail = "comment-rejected"
    selected = plan(router, now)
    router.tables["leases"].append(
        {
            ".id": "*2",
            "address": "198.51.100.20",
            "mac-address": "02:11:22:33:44:66",
            "server": "lan",
            "dynamic": "false",
            "comment": "Untouched",
        }
    )
    result = await LeaseExecutor(router, selected, journal.save, lambda: True).run(
        now, dhcp_recovery=True
    )
    assert result["status"] == "rolled_back"
    assert result["targets"][0]["phase"] == "dhcp_recovery"
    assert router.calls[-1] == ("remove", "*A")
    assert [r[".id"] for r in router.tables["leases"]] == ["*2"]


@pytest.mark.asyncio
async def test_concurrent_user_change_is_not_overwritten_or_removed(now):
    router, journal = Router(), Journal()
    router.external = True
    result = await LeaseExecutor(router, plan(router, now), journal.save, lambda: True).run(
        now, dhcp_recovery=True
    )
    assert result["status"] == "review_required"
    assert router.tables["leases"][0]["comment"] == "User's new comment"
    assert not any(call[0] == "remove" for call in router.calls)


@pytest.mark.asyncio
async def test_storage_fault_before_effect_and_recovery_after_conversion(now):
    router, journal = Router(), Journal()
    selected = plan(router, now)
    journal.fail_at = 2
    with pytest.raises(OSError):
        await LeaseExecutor(router, selected, journal.save, lambda: True).run(
            now, dhcp_recovery=True
        )
    assert not router.calls
    journal.fail_at = 5  # Next run initial save=3, intent=4, conversion receipt=5.
    with pytest.raises(OSError):
        await LeaseExecutor(router, selected, journal.save, lambda: True).run(
            now, journal.saved, dhcp_recovery=True
        )
    assert router.calls == [("static", "*1")]
    assert journal.saved["targets"][0]["phase"] == "converting"
    journal.fail_at = None
    result = await LeaseExecutor(router, selected, journal.save, lambda: True).run(
        now + timedelta(minutes=10), journal.saved, dhcp_recovery=True
    )
    assert result["status"] == "applied"
    assert router.calls == [("static", "*1"), ("comment", "*A", "Chosen")]


@pytest.mark.asyncio
async def test_revoked_authority_and_preview_expiry_never_write(now):
    router, journal = Router(), Journal()
    selected = plan(router, now)
    for auth, clock, consent, code in [
        (False, now, True, "forbidden"),
        (True, now + timedelta(minutes=6), True, "proposal_expired"),
        (True, now, "yes", "network_recovery_consent"),
    ]:
        with pytest.raises(DomainError, match=code):
            await LeaseExecutor(router, selected, journal.save, lambda auth=auth: auth).run(
                clock, dhcp_recovery=consent
            )
    assert not router.calls


@pytest.mark.asyncio
async def test_role_revocation_between_commands_stops_and_requests_review(now):
    router, journal = Router(), Journal()
    allowed = True

    def revoke():
        nonlocal allowed
        allowed = False

    router.hook = revoke
    result = await LeaseExecutor(router, plan(router, now), journal.save, lambda: allowed).run(
        now, dhcp_recovery=True
    )
    assert result["status"] == "review_required"
    assert router.calls == [("static", "*1")]


@pytest.mark.asyncio
async def test_progress_is_bound_to_exact_plan_and_static_edit_does_not_convert(now):
    router, journal = Router(dynamic=False), Journal()
    selected = plan(router, now)
    result = await LeaseExecutor(router, selected, journal.save, lambda: True).run(now)
    assert result["status"] == "applied" and router.calls == [("comment", "*1", "Chosen")]
    changed = {**selected, "expires_at": (now + timedelta(hours=1)).isoformat()}
    with pytest.raises(DomainError, match="network_conflict"):
        await LeaseExecutor(router, changed, journal.save, lambda: True).run(now, journal.saved)


@pytest.mark.asyncio
async def test_partial_static_batch_restores_only_our_comment(now):
    router, journal = Router(dynamic=False), Journal()
    router.tables["leases"].append(
        {
            **router.tables["leases"][0],
            ".id": "*2",
            "address": "198.51.100.20",
            "mac-address": "02:11:22:33:44:66",
        }
    )
    selected = preview(
        router.tables,
        [
            {"id": "*1", "comment": "Chosen", "replace_comment": True},
            {"id": "*2", "comment": "Chosen", "replace_comment": True},
        ],
        now,
    )
    router.fail = "comment-second"
    result = await LeaseExecutor(router, selected, journal.save, lambda: True).run(now)
    assert result["status"] == "rolled_back"
    assert all(row["comment"] == "Original" for row in router.tables["leases"])
    assert router.calls == [
        ("comment", "*1", "Chosen"),
        ("comment", "*2", "Chosen"),
        ("comment", "*1", "Original"),
    ]


@pytest.mark.asyncio
async def test_newly_protected_target_fails_live_revalidation(now):
    router, journal = Router(), Journal()
    selected = plan(router, now)
    router.tables["interfaces"] = [{"mac-address": "02:11:22:33:44:55"}]
    result = await LeaseExecutor(router, selected, journal.save, lambda: True).run(
        now, dhcp_recovery=True
    )
    assert result["status"] == "rolled_back" and result["failure"] == "network_protected"
    assert not router.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("progress", [{}, [], {"status": "applying"}])
async def test_malformed_progress_never_bypasses_expiry_or_journal(now, progress):
    router, journal = Router(), Journal()
    with pytest.raises(DomainError, match="network_conflict"):
        await LeaseExecutor(router, plan(router, now), journal.save, lambda: True).run(
            now + timedelta(hours=1), progress, dhcp_recovery=True
        )
    assert not router.calls and journal.saved is None
