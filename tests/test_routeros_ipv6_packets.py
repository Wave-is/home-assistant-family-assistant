"""Byte-level independent checksum and malformed IPv6 fixture checks."""

import struct

import pytest

from tests.routeros.ipv6_packets import endpoint6_match, ip6, udp6_frame, udp6_payload
from tests.routeros.packets import CLIENT_MAC, SERVER_MAC


def frame(data=b"synthetic fresh payload"):
    return udp6_frame(
        CLIENT_MAC, SERVER_MAC, ip6("2001:db8:1::10"), ip6("2001:db8:2::10"), 42001, 45001, data
    )


def summed_words(data):
    # Independent arithmetic, rather than reusing the generator's checksum.
    if len(data) % 2:
        data += b"\x00"
    total = sum(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return total


@pytest.mark.parametrize("data", [b"", b"odd", b"even", b"x" * 1000])
def test_udp6_wire_fields_and_independent_pseudoheader_checksum(data):
    packet = frame(data)
    assert packet[:14] == SERVER_MAC + CLIENT_MAC + b"\x86\xdd"
    assert packet[14:18] == bytes.fromhex("60000000")
    assert packet[20:22] == bytes((17, 64))
    length = len(data) + 8
    assert int.from_bytes(packet[18:20], "big") == length
    pseudo = packet[22:54] + struct.pack("!I3xB", length, 17)
    assert summed_words(pseudo + packet[54:]) == 65535
    assert udp6_payload(packet) == (42001, 45001, data)
    assert udp6_payload(packet + b"\x00" * 10) == (42001, 45001, data)


@pytest.mark.parametrize("length", [0, 12, 14, 53, 54, 61, 63])
def test_truncation_rejected(length):
    assert udp6_payload(frame()[:length]) is None


@pytest.mark.parametrize("offset", [12, 14, 18, 20, 22, 38, 54, 56, 58, 60, 62])
def test_wrong_headers_lengths_endpoints_and_corruption_rejected(offset):
    packet = bytearray(frame())
    packet[offset] ^= 0x10 if offset == 14 else 1
    assert udp6_payload(packet) is None


@pytest.mark.parametrize("next_header", [0, 43, 44, 50, 51, 60])
def test_extensions_and_fragmentation_outside_bounded_fixture(next_header):
    packet = bytearray(frame())
    packet[20] = next_header
    assert udp6_payload(packet) is None


def test_ipv6_zero_udp_checksum_and_expired_hop_limit_rejected():
    packet = frame()
    assert udp6_payload(packet[:60] + b"\x00\x00" + packet[62:]) is None
    assert udp6_payload(packet[:21] + b"\x00" + packet[22:]) is None


def test_computed_zero_is_encoded_as_ffff():
    packet = frame(b"\x00\x00")
    pseudo = packet[22:54] + struct.pack("!I3xB", 10, 17)
    base = packet[54:60] + b"\x00\x00\x00\x00"
    compensation = 65535 - summed_words(pseudo + base)
    special = frame(struct.pack("!H", compensation))
    assert special[60:62] == b"\xff\xff"
    assert udp6_payload(special) == (42001, 45001, struct.pack("!H", compensation))


@pytest.mark.parametrize(
    "field", ["source_mac", "target_mac", "source_ip", "target_ip", "ports", "payload"]
)
def test_matching_payload_cannot_confirm_wrong_endpoint(field):
    expected = {
        "source_mac": CLIENT_MAC,
        "target_mac": SERVER_MAC,
        "source_ip": ip6("2001:db8:1::10"),
        "target_ip": ip6("2001:db8:2::10"),
        "ports": (42001, 45001),
        "payload": b"synthetic fresh payload",
    }
    assert endpoint6_match(frame(), **expected)
    expected[field] = (42002, 45001) if field == "ports" else b"\x00" * len(expected[field])
    assert not endpoint6_match(frame(), **expected)


@pytest.mark.parametrize("port", [True, -1, 65536, "42001", 4.5])
def test_generator_rejects_invalid_port(port):
    with pytest.raises(ValueError):
        udp6_frame(
            CLIENT_MAC, SERVER_MAC, ip6("2001:db8:1::10"), ip6("2001:db8:2::10"), port, 45001, b"x"
        )
