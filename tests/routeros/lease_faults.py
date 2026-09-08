"""Selected-record compensation against actual REST in the disposable VM only."""

from copy import deepcopy
from datetime import UTC, datetime

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.lease_executor import LeaseExecutor
from custom_components.family_assistant.network.leases import fingerprint, preview, readback_match
from tests.routeros.packets import CLIENT_MAC, dhcp_bind, forwarded_probe


class DeniedSecondComment:
    """Use native read-only credentials for one exact second-target write.

    All reads and other mutations use the real integration client. A deliberately
    lost response after make-static tests reconciliation of an applied effect;
    it does not substitute mock router state for native read-back.
    """

    def __init__(self, client, audit, denied_id):
        self.client, self.audit, self.denied_id = client, audit, denied_id
        self.calls = 0
        self.lost_response = False

    async def read(self, name):
        self.calls += 1
        return await self.client.read(name)

    async def make_static(self, item_id):
        self.calls += 1
        await self.client.make_static(item_id)
        if not self.lost_response:
            self.lost_response = True
            raise DomainError("network_timeout")

    async def set_comment(self, item_id, comment):
        self.calls += 1
        client = self.audit if item_id == self.denied_id else self.client
        await client.set_comment(item_id, comment)

    async def remove_reservation(self, item_id):
        self.calls += 1
        await self.client.remove_reservation(item_id)


async def native_lease_faults(client, audit, lan, server_link, address):
    """Fail target two; verify target one compensation and an untouched sentinel.

    Called once before and once after the ordinary native lease conversion. The
    dynamic case requires explicit DHCP recovery consent and an actual new DHCP
    exchange; the static case must restore the exact prior configuration hash.
    """
    fixtures = []
    try:
        for suffix, hardware in ((60, "02:11:22:33:44:88"), (61, "02:11:22:33:44:99")):
            row = await client._request(
                "PUT",
                "ip/dhcp-server/lease",
                json={
                    "address": f"198.51.100.{suffix}",
                    "mac-address": hardware,
                    "server": "fa-lan",
                    "comment": f"Synthetic rollback sentinel {suffix}",
                },
            )
            fixtures.append(row[".id"])
        tables = await client.inventory()
        first = next(row for row in tables["leases"] if row["address"] == address)
        sentinels = {
            row[".id"]: fingerprint(row) for row in tables["leases"] if row[".id"] in fixtures
        }
        assert len(sentinels) == 2
        now = datetime.now(UTC)
        plan = preview(
            tables,
            [
                {"id": first[".id"], "comment": "Synthetic first update", "replace_comment": True},
                {"id": fixtures[0], "comment": "Must be denied", "replace_comment": True},
            ],
            now,
        )
        converting = plan["targets"][0]["convert"]
        journal = []

        async def persist(progress):
            journal.append(deepcopy(progress))

        fault = DeniedSecondComment(client, audit, fixtures[0])
        worker = LeaseExecutor(fault, plan, persist, lambda: True)
        result = await worker.run(now, dhcp_recovery=True)
        assert result["status"] == "rolled_back", result
        assert result["failure"] == "network_permission", result
        assert any(saved["targets"][0]["phase"] == "verified" for saved in journal)
        assert result["targets"][0]["phase"] == ("dhcp_recovery" if converting else "restored")
        assert result["targets"][1]["phase"] == "restored"
        calls = fault.calls
        assert await worker.run(now, result, dhcp_recovery=True) == result
        assert fault.calls == calls, "Terminal replay must not perform even a router read"
        rows = await client.read("leases")
        assert {
            row[".id"]: fingerprint(row) for row in rows if row[".id"] in fixtures
        } == sentinels, "Denied and unselected native records must be unchanged"
        if converting:
            assert fault.lost_response
            assert not any(
                row.get("mac-address") == CLIENT_MAC.hex(":").upper()
                and row.get("dynamic") != "true"
                for row in rows
            ), "Only the converted reservation may be removed for DHCP recovery"
            address = await dhcp_bind(lan)
            recovered = next(
                row for row in await client.read("leases") if row["address"] == address
            )
            assert recovered["dynamic"] == "true" and recovered["status"] == "bound"
            assert recovered["mac-address"] == CLIENT_MAC.hex(":").upper()
        else:
            assert fingerprint(readback_match(plan["targets"][0], rows)) == fingerprint(first)
        assert await forwarded_probe(lan, server_link, address)
        print(
            "PASS: native two-target permission fault, exact compensation, sentinel and replay:",
            "dynamic with lost-response/read-back and DHCP recovery"
            if converting
            else "static comment",
            flush=True,
        )
        return address
    finally:
        for item_id in fixtures:
            await client._request("DELETE", "ip/dhcp-server/lease/" + item_id)
