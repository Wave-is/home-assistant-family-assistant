"""Bounded IPv6 probes on the existing isolated emulated Ethernet links only."""

import asyncio
import ipaddress
import secrets
import struct

from tests.routeros.ipv6_packets import endpoint6_match, ip6, udp6_frame
from tests.routeros.packets import (
    CLIENT_MAC,
    ROUTER_LAN_MAC,
    ROUTER_SERVER_MAC,
    SERVER_MAC,
    checksum,
)


def icmp6_frame(src_mac, dst_mac, source, target, body):
    pseudo = source + target + struct.pack("!I3xB", len(body), 58)
    check = checksum(pseudo + body)
    body = body[:2] + struct.pack("!H", check) + body[4:]
    header = struct.pack("!IHBB16s16s", 6 << 28, len(body), 58, 255, source, target)
    return dst_mac + src_mac + b"\x86\xdd" + header + body


def neighbor_reply(frame, address, local_mac, router_mac):
    """Reply only to valid, directly addressed NS from this synthetic router NIC.

    Deliberately excludes DAD, extension headers and unrelated discovery. This
    is a tiny lab fixture, not an IPv6 stack. RFC4861 section7.1.1 is validated
    before producing one solicited/override NA with a target-link-layer option.
    """
    if (
        len(frame) < 78
        or frame[6:12] != router_mac
        or frame[12:14] != b"\x86\xdd"
        or frame[14] >> 4 != 6
        or frame[20:22] != bytes((58, 255))
    ):
        return None
    length = int.from_bytes(frame[18:20], "big")
    source, destination = frame[22:38], frame[38:54]
    multicast = ip6("ff02::1:ff00:0")[:-3] + address[-3:]
    if (
        length < 24
        or len(frame) < 54 + length
        or source == b"\x00" * 16
        or ipaddress.IPv6Address(source).is_multicast
        or ipaddress.IPv6Address(address).is_multicast
        or (destination, frame[:6])
        not in {(address, local_mac), (multicast, b"\x33\x33\xff" + address[-3:])}
    ):
        return None
    body = frame[54 : 54 + length]
    if body[:2] != bytes((135, 0)) or body[8:24] != address:
        return None
    if checksum(source + destination + struct.pack("!I3xB", length, 58) + body):
        return None
    offset = 24
    while offset < len(body):
        if offset + 2 > len(body):
            return None
        size = body[offset + 1] * 8
        if size == 0 or offset + size > len(body):
            return None
        if body[offset] == 1 and (size != 8 or body[offset + 2 : offset + 8] != router_mac):
            return None
        offset += size
    reply = bytes((136, 0, 0, 0)) + struct.pack("!I", 0x60000000) + address
    reply += bytes((2, 1)) + local_mac
    return icmp6_frame(local_mac, router_mac, address, source, reply)


async def forwarded_probe6(
    lan, server_link, *, client_mac=CLIENT_MAC, address="2001:db8:1::10", observations=None
):
    """Fresh bidirectional routed IPv6 UDP plus scoped neighbor responses."""
    client_ip, server_ip = ip6(address), ip6("2001:db8:2::10")
    if observations is not None:
        observations.clear()
        observations.update(forwarded=False, returned=False)
    nonce, port = secrets.token_bytes(24), 40000 + secrets.randbelow(10000)
    frame = udp6_frame(client_mac, ROUTER_LAN_MAC, client_ip, server_ip, port, 45001, nonce)
    pending = {}
    try:
        for _ in range(3):
            await lan.send(frame)
            deadline = asyncio.get_running_loop().time() + 1
            while asyncio.get_running_loop().time() < deadline:
                for key, link in (("lan", lan), ("server", server_link)):
                    if key not in pending:
                        pending[key] = asyncio.create_task(link.receive())
                ready, _ = await asyncio.wait(
                    pending.values(),
                    timeout=max(0, deadline - asyncio.get_running_loop().time()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in ready:
                    key = next(k for k, value in pending.items() if value is task)
                    del pending[key]
                    received = task.result()
                    if key == "server":
                        reply = neighbor_reply(received, server_ip, SERVER_MAC, ROUTER_SERVER_MAC)
                        if reply:
                            await server_link.send(reply)
                        if endpoint6_match(
                            received,
                            ROUTER_SERVER_MAC,
                            SERVER_MAC,
                            client_ip,
                            server_ip,
                            (port, 45001),
                            nonce,
                        ):
                            if observations is not None:
                                observations["forwarded"] = True
                            await server_link.send(
                                udp6_frame(
                                    SERVER_MAC,
                                    ROUTER_SERVER_MAC,
                                    server_ip,
                                    client_ip,
                                    45001,
                                    port,
                                    nonce,
                                )
                            )
                    else:
                        reply = neighbor_reply(received, client_ip, client_mac, ROUTER_LAN_MAC)
                        if reply:
                            await lan.send(reply)
                        if endpoint6_match(
                            received,
                            ROUTER_LAN_MAC,
                            client_mac,
                            server_ip,
                            client_ip,
                            (45001, port),
                            nonce,
                        ):
                            if observations is not None:
                                observations["returned"] = True
                            return True
        return False
    finally:
        for task in pending.values():
            task.cancel()
        await asyncio.gather(*pending.values(), return_exceptions=True)
