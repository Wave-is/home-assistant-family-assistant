"""Synthetic Ethernet endpoints carried only over container-loopback UDP.

No raw sockets, TAPs, host interfaces or LAN targets. These small RFC 2131/IPv4
fixtures are developer tests, not an integration network implementation.
"""

import asyncio
import ipaddress
import secrets
import socket
import struct

BROADCAST = b"\xff" * 6
ZERO = b"\x00" * 4
MAGIC = b"\x63\x82\x53\x63"
CLIENT_MAC = bytes.fromhex("021122334455")
SERVER_MAC = bytes.fromhex("021122334466")
ROUTER_LAN_MAC = bytes.fromhex("02fa00000001")
ROUTER_SERVER_MAC = bytes.fromhex("02fa00000002")


def ip(value):
    return ipaddress.IPv4Address(value).packed


def checksum(data):
    padded = data + b"\x00" * (len(data) % 2)
    total = sum(struct.unpack("!" + "H" * (len(padded) // 2), padded))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def udp_frame(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, data):
    udp = struct.pack("!HHHH", src_port, dst_port, len(data) + 8, 0) + data
    header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 1, 0, 64, 17, 0, src_ip, dst_ip)
    header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
    return dst_mac + src_mac + b"\x08\x00" + header + udp


def udp_payload(frame):
    if len(frame) < 42 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
        return None
    head = (frame[14] & 15) * 4
    if head < 20 or len(frame) < 14 + head + 8:
        return None
    offset = 14 + head
    src, dst, length, _ = struct.unpack("!HHHH", frame[offset : offset + 8])
    if length < 8 or len(frame) < offset + length:
        return None
    return src, dst, frame[offset + 8 : offset + length]


def dhcp_options(payload):
    if len(payload) < 240 or payload[236:240] != MAGIC:
        return {}
    result, offset = {}, 240
    while offset < len(payload):
        kind = payload[offset]
        offset += 1
        if kind == 255:
            break
        if kind == 0:
            continue
        if offset >= len(payload):
            return {}
        length = payload[offset]
        offset += 1
        if offset + length > len(payload):
            return {}
        result[kind] = payload[offset : offset + length]
        offset += length
    return result


def dhcp_request(xid, message_type, selected=None, server=None):
    header = struct.pack("!BBBBIHH", 1, 1, 6, 0, xid, 0, 0x8000)
    header += ZERO * 4 + CLIENT_MAC.ljust(16, b"\x00") + b"\x00" * 192
    options = MAGIC + bytes((53, 1, message_type, 61, 7, 1)) + CLIENT_MAC
    options += bytes((12, 9)) + b"synthetic" + bytes((55, 3, 1, 3, 6))
    if selected is not None:
        options += bytes((50, 4)) + selected + bytes((54, 4)) + server
    return udp_frame(CLIENT_MAC, BROADCAST, ZERO, b"\xff" * 4, 68, 67, header + options + b"\xff")


class Link:
    """Fixed loopback Ethernet transport; no caller-specified host accepted."""

    def __init__(self, port):
        if port not in {30001, 30003}:
            raise ValueError("Only isolated lab endpoint ports are accepted")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.setblocking(False)
        self.peer = ("127.0.0.1", port + 1)

    async def send(self, data):
        await asyncio.get_running_loop().sock_sendto(self.sock, data, self.peer)

    async def receive(self):
        while True:
            data, address = await asyncio.get_running_loop().sock_recvfrom(self.sock, 65536)
            if address == self.peer:
                return data

    def close(self):
        self.sock.close()


async def dhcp_bind(link):
    xid = secrets.randbits(32)
    selected = server = None
    for request_type, reply_type in ((1, 2), (3, 5)):
        for attempt in range(4):
            await link.send(dhcp_request(xid, request_type, selected, server))
            try:
                async with asyncio.timeout(4):
                    while True:
                        frame = await link.receive()
                        parsed = udp_payload(frame)
                        if not parsed or parsed[:2] != (67, 68):
                            continue
                        data = parsed[2]
                        opts = dhcp_options(data)
                        if (
                            len(data) >= 240
                            and data[0] == 2
                            and data[4:8] == struct.pack("!I", xid)
                            and data[28:34] == CLIENT_MAC
                            and opts.get(53) == bytes((reply_type,))
                        ):
                            selected, server = data[16:20], opts[54]
                            assert selected[:3] == ip("198.51.100.0")[:3]
                            assert server == ip("198.51.100.1")
                            break
                break
            except TimeoutError:
                if attempt == 3:
                    raise AssertionError("Synthetic DHCP exchange did not complete") from None
    return str(ipaddress.IPv4Address(selected))


async def arp_reply(link, frame, address, mac_address):
    if (
        len(frame) >= 42
        and frame[12:14] == b"\x08\x06"
        and frame[20:22] == b"\x00\x01"
        and frame[38:42] == address
    ):
        sender_mac, sender_ip = frame[22:28], frame[28:32]
        payload = struct.pack("!HHBBH", 1, 0x800, 6, 4, 2)
        payload += mac_address + address + sender_mac + sender_ip
        await link.send(sender_mac + mac_address + b"\x08\x06" + payload)


async def forwarded_probe(lan, server_link, address, *, client_mac=CLIENT_MAC):
    """One bidirectional routed IPv4 UDP flow with a fresh payload and port."""
    nonce, port = secrets.token_bytes(24), 40000 + secrets.randbelow(10000)
    client_ip, server_ip = ip(address), ip("203.0.113.10")
    frame = udp_frame(client_mac, ROUTER_LAN_MAC, client_ip, server_ip, port, 45001, nonce)
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
                    parsed = udp_payload(received)
                    if key == "server":
                        await arp_reply(server_link, received, server_ip, SERVER_MAC)
                        if parsed and parsed[:2] == (port, 45001) and parsed[2] == nonce:
                            await server_link.send(
                                udp_frame(
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
                        await arp_reply(lan, received, client_ip, client_mac)
                        if parsed and parsed[:2] == (45001, port) and parsed[2] == nonce:
                            return True
        return False
    finally:
        for task in pending.values():
            task.cancel()
        await asyncio.gather(*pending.values(), return_exceptions=True)
