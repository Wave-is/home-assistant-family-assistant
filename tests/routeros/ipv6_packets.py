"""Minimal RFC8200 IPv6 UDP frames for isolated developer tests, not runtime."""

import ipaddress
import struct

from tests.routeros.packets import checksum


def ip6(value):
    return ipaddress.IPv6Address(value).packed


def _pseudo(source, target, length):
    return source + target + struct.pack("!I3xB", length, 17)


def udp6_frame(src_mac, dst_mac, src_ip, dst_ip, src_port, dst_port, data):
    if (
        any(
            not isinstance(value, bytes) or len(value) != size
            for value, size in (
                (src_mac, 6),
                (dst_mac, 6),
                (src_ip, 16),
                (dst_ip, 16),
            )
        )
        or any(type(port) is not int or not 0 <= port <= 65535 for port in (src_port, dst_port))
        or not isinstance(data, bytes)
        or len(data) > 65527
    ):
        raise ValueError("Invalid synthetic IPv6 UDP fields")
    length = len(data) + 8
    udp = struct.pack("!HHHH", src_port, dst_port, length, 0) + data
    check = checksum(_pseudo(src_ip, dst_ip, length) + udp) or 65535
    udp = udp[:6] + struct.pack("!H", check) + udp[8:]
    header = struct.pack("!IHBB16s16s", 6 << 28, length, 17, 64, src_ip, dst_ip)
    return dst_mac + src_mac + b"\x86\xdd" + header + udp


def udp6_payload(frame):
    if (
        not isinstance(frame, (bytes, bytearray))
        or len(frame) < 62
        or frame[12:14] != b"\x86\xdd"
        or frame[14] >> 4 != 6
        or frame[20] != 17
        or frame[21] == 0
    ):
        return None
    length = int.from_bytes(frame[18:20], "big")
    if length < 8 or len(frame) < 54 + length:
        return None
    udp = bytes(frame[54 : 54 + length])
    source, target, udp_length, check = struct.unpack("!HHHH", udp[:8])
    if udp_length != length or check == 0:
        return None
    if checksum(_pseudo(bytes(frame[22:38]), bytes(frame[38:54]), length) + udp):
        return None
    return source, target, udp[8:]


def endpoint6_match(frame, source_mac, target_mac, source_ip, target_ip, ports, payload):
    parsed = udp6_payload(frame)
    return bool(
        parsed
        and frame[:6] == target_mac
        and frame[6:12] == source_mac
        and frame[22:38] == source_ip
        and frame[38:54] == target_ip
        and parsed[:2] == ports
        and parsed[2] == payload
    )
