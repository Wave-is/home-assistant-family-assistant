"""Native scope characterization in the disposable, network-disabled CHR only."""

import asyncio
import ipaddress
from copy import deepcopy
from datetime import UTC, datetime

from custom_components.family_assistant.network import kids
from custom_components.family_assistant.network.inventory import build
from custom_components.family_assistant.network.kid_executor import KidExecutor
from tests.routeros.ipv6_probe import forwarded_probe6
from tests.routeros.packets import forwarded_probe


def udp_tuple(row):
    """RouterOS builds expose ports either separately or inside IPv4 endpoints."""
    if row.get("protocol") != "udp":
        return None
    result = []
    for side in ("src", "dst"):
        value, explicit = row.get(side + "-address"), row.get(side + "-port")
        if not isinstance(value, str):
            return None
        if ":" in value:
            value, port = value.rsplit(":", 1)
            if explicit is not None and str(explicit) != port:
                return None
        else:
            port = str(explicit)
        try:
            value = str(ipaddress.IPv4Address(value))
        except ValueError:
            return None
        if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
            return None
        result.extend((value, int(port)))
    return tuple(result)


def fresh_ports(rows, address):
    """Select two unused tuples, not constants that might collide with prior probes."""
    used = {
        flow[1]
        for row in rows
        if (flow := udp_tuple(row)) and flow[0] == address and flow[2:] == ("203.0.113.10", 45001)
    }
    available = [port for port in range(47000, 50000) if port not in used]
    if len(available) < 2:
        raise AssertionError("Synthetic connection-port budget exhausted")
    return available[0], available[1]


async def verify_topology(vm, client, lan, server_link, address):
    await vm.command("/ipv6 settings set disable-ipv6=no forward=yes")
    await vm.command("/ipv6 address add address=2001:db8:1::1/64 interface=ether2 advertise=no")
    await vm.command("/ipv6 address add address=2001:db8:2::1/64 interface=ether3 advertise=no")
    await vm.command("/ip firewall connection tracking set enabled=yes")
    assert await forwarded_probe(lan, server_link, address)
    assert await forwarded_probe6(lan, server_link), "IPv6 baseline did not route bidirectionally"
    print("PASS: native IPv4/IPv6 routed baseline and scoped neighbor discovery", flush=True)
    native = device = None
    filters = []

    async def fasttrack_count():
        settings = await client._request("GET", "ip/settings")
        row = settings[0] if isinstance(settings, list) else settings
        return int(row.get("ipv4-fasttrack-packets", 0)), row

    try:
        # Calibrate before adopting the client. Kid Control itself may change
        # acceleration eligibility; do not mistake that for a broken packet fixture.
        for action in ("fasttrack-connection", "accept"):
            body = {
                "chain": "forward",
                "action": action,
                "connection-state": "established,related",
                "comment": "Synthetic topology FastTrack",
            }
            if action == "fasttrack-connection":
                body["hw-offload"] = "no"
            row = await client._request("PUT", "ip/firewall/filter", json=body)
            filters.append(row[".id"])
        tables = await client.inventory()
        assert build(tables, [], datetime.now(UTC))["fasttrack"] is True
        port, new_port = fresh_ports(
            await client._request("GET", "ip/firewall/connection"), address
        )
        count_before, settings = await fasttrack_count()
        fasttracked, flow = False, []
        for _ in range(4):
            # Only this routed flow is active during calibration.
            for _packet in range(64):
                assert await forwarded_probe(lan, server_link, address, client_port=port)
            await asyncio.sleep(0.5)
            rows = await client._request("GET", "ip/firewall/connection")
            flow = [row for row in rows if udp_tuple(row) == (address, port, "203.0.113.10", 45001)]
            count_after, settings = await fasttrack_count()
            if len(flow) == 1 and flow[0].get("fasttrack") == "true" and count_after > count_before:
                fasttracked = True
                print(
                    "PASS: pre-adoption dedicated flow increased FastTrack packet counter by",
                    count_after - count_before,
                    flush=True,
                )
                break
        if not fasttracked:
            print(
                "Synthetic calibration diagnostic:",
                {
                    "port": port,
                    "matches": len(flow),
                    "ip_settings": {
                        k: settings.get(k)
                        for k in (
                            "allow-fast-path",
                            "ipv4-fast-path-active",
                            "ipv4-fasttrack-active",
                            "ipv4-fasttrack-packets",
                        )
                    },
                    "flow": [
                        {
                            k: row.get(k)
                            for k in (
                                "src-address",
                                "src-port",
                                "dst-address",
                                "dst-port",
                                "fasttrack",
                                "orig-fasttrack-packets",
                                "repl-fasttrack-packets",
                            )
                        }
                        for row in flow
                    ],
                },
                flush=True,
            )
            raise AssertionError(
                "FastTrack baseline unproven: profile test must not claim acceleration"
            )

        native = await client._request(
            "PUT",
            "ip/kid-control",
            json={
                "name": "Synthetic topology child",
                **dict.fromkeys(kids.DAYS, "00:00-24:00"),
            },
        )
        device = await client._request(
            "PUT",
            "ip/kid-control/device",
            json={
                "name": "Synthetic topology client",
                "user": "Synthetic topology child",
                "mac-address": "02:11:22:33:44:55",
            },
        )
        tables = await client.inventory()
        binding = {**kids.bind(tables, native[".id"], [device[".id"]]), "member": "test-child"}
        sequence = 0

        async def apply(mode):
            nonlocal sequence
            sequence += 1
            now, tables = datetime.now(UTC), await client.inventory()
            plan = {
                **kids.prepare(
                    tables,
                    binding,
                    {"member": "test-child", "mode": mode},
                    now,
                    tables["clock"][0]["time-zone-name"],
                ),
                "id": f"K{100 + sequence:06}",
                "backend": "isolated-native-rest",
            }
            journal = []

            async def persist(progress):
                journal.append(deepcopy(progress))

            result = await KidExecutor(client, plan, persist, lambda: True).run(now)
            assert result["status"] == "applied", result
            assert "ipv6_and_fasttrack_require_verification" in plan["warnings"]

        async def settled_v4(expected, *, selected_port=None):
            attempts = []
            for _ in range(6):
                observations = {}
                returned = await forwarded_probe(
                    lan,
                    server_link,
                    address,
                    client_port=selected_port,
                    observations=observations,
                )
                attempts.append({**observations, "result": returned})
                if returned is expected and observations["forwarded"] is expected:
                    return
                await asyncio.sleep(1)
            rows4 = await client._request(
                "GET",
                "ip/firewall/filter",
                params={
                    ".proplist": (
                        "chain,action,dynamic,src-address,dst-address,"
                        "src-mac-address,connection-state,packets"
                    )
                },
            )
            print(
                "Synthetic one-way probe diagnostic:",
                {"port": selected_port, "attempts": attempts, "filters4": rows4},
                flush=True,
            )
            raise AssertionError(f"Topology IPv4 probe did not settle allowed={expected}")

        await settled_v4(True, selected_port=port)
        assert await forwarded_probe6(lan, server_link)
        await apply("pause")
        for _ in range(24):
            dynamic = await client._request(
                "GET",
                "ip/firewall/filter",
                params={".proplist": "chain,action,dynamic,src-address,dst-address"},
            )
            if all(
                any(
                    row.get("dynamic") == "true"
                    and row.get("action") == "reject"
                    and row.get(direction) in {address, address + "/32"}
                    for row in dynamic
                )
                for direction in ("src-address", "dst-address")
            ):
                break
            await asyncio.sleep(0.25)
        else:
            raise AssertionError("Native pause did not install both directional reject rules")
        # Profile read-back does not imply that cached accelerated connections
        # stopped, nor that dynamic filter installation was synchronous. Record
        # both directions without treating a failed echo as packet isolation.
        accelerated_observations = {}
        for candidate in (new_port, port):
            attempts = []
            for _ in range(3):
                seen = {}
                returned = await forwarded_probe(
                    lan, server_link, address, client_port=candidate, observations=seen
                )
                attempts.append({**seen, "result": returned})
            accelerated_observations[candidate] = attempts
        print(
            "OBSERVED: raw Kid Control pause with accelerated tuples (not isolation proof):",
            accelerated_observations,
            flush=True,
        )

        # Fixture-only mitigation, NOT a runtime integration operation: disable
        # the exact acceleration rule created above and expire only these two
        # synthetic connections. Existing FastTrack state can outlive a rule edit.
        await client._request(
            "PATCH", "ip/firewall/filter/" + filters[0], json={"disabled": "true"}
        )
        owned = await client._request("GET", "ip/firewall/filter/" + filters[0])
        owned = owned[0] if isinstance(owned, list) else owned
        assert owned.get("disabled") == "true"
        tuples = {(address, candidate, "203.0.113.10", 45001) for candidate in (port, new_port)}
        # Resolve anew for every deletion; native dynamic table identifiers must
        # not be treated as a durable multi-record deletion plan.
        for _ in range(24):
            remaining = [
                connection
                for connection in await client._request("GET", "ip/firewall/connection")
                if udp_tuple(connection) in tuples
            ]
            if not remaining:
                break
            selected = remaining[0]
            current = await client._request("GET", "ip/firewall/connection/" + selected[".id"])
            current = current[0] if isinstance(current, list) else current
            if udp_tuple(current) == udp_tuple(selected):
                await client._request("DELETE", "ip/firewall/connection/" + selected[".id"])
            await asyncio.sleep(0.25)
        else:
            print(
                "Synthetic selected-expiry diagnostic:",
                [
                    {
                        key: row.get(key)
                        for key in (
                            ".id",
                            "src-address",
                            "src-port",
                            "dst-address",
                            "dst-port",
                            "fasttrack",
                            "dying",
                            "timeout",
                        )
                    }
                    for row in remaining
                ],
                flush=True,
            )
            raise AssertionError("Selected native connections did not expire after deletion")
        await settled_v4(False, selected_port=new_port)
        await settled_v4(False, selected_port=port)
        print(
            "PASS: no outbound IPv4 leak after fixture-owned FastTrack withdrawal "
            "and selected expiry",
            flush=True,
        )
        observations6 = {}
        assert await forwarded_probe6(lan, server_link, observations=observations6) is False, (
            "Pinned IPv6 pause behavior changed"
        )
        assert observations6["forwarded"] is False, "Blocking only replies must not pass"
        fields6 = "chain,action,dynamic,src-address,dst-address,comment"
        filters6 = await client._request(
            "GET", "ipv6/firewall/filter", params={".proplist": fields6}
        )
        for direction in ("src-address", "dst-address"):
            assert any(
                row.get("dynamic") == "true"
                and row.get("action") == "reject"
                and row.get(direction) == "2001:db8:1::10/128"
                for row in filters6
            )
        assert await forwarded_probe(
            lan, server_link, "198.51.100.30", client_mac=bytes.fromhex("021122334477")
        )
        assert await forwarded_probe6(
            lan, server_link, address="2001:db8:1::30", client_mac=bytes.fromhex("021122334477")
        )
        await apply("resume")
        await settled_v4(True, selected_port=new_port)
        await settled_v4(True, selected_port=port)
        assert await forwarded_probe6(lan, server_link)
        print(
            "PASS: native IPv4/IPv6 pause/resume after fixture-only acceleration mitigation "
            "and independent control clients; raw FastTrack observations are not isolation proof",
            flush=True,
        )
    finally:
        # Only exact records created inside this disposable VM.
        if device:
            await client._request("DELETE", "ip/kid-control/device/" + device[".id"])
        if native:
            await client._request("DELETE", "ip/kid-control/" + native[".id"])
        for item_id in filters:
            await client._request("DELETE", "ip/firewall/filter/" + item_id)
