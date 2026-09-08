"""Strict synthetic ND response scope; no sockets or live router involved."""

import struct

import pytest

from tests.routeros.ipv6_packets import ip6
from tests.routeros.ipv6_probe import icmp6_frame, neighbor_reply
from tests.routeros.packets import CLIENT_MAC, ROUTER_LAN_MAC, checksum

ADDRESS = ip6("2001:db8:1::10")
ROUTER = ip6("fe80::fa:1")
MULTICAST = ip6("ff02::1:ff00:10")


def solicitation(*, source=ROUTER, destination=MULTICAST, options=None, target=ADDRESS):
    body = bytes((135, 0, 0, 0)) + b"\x00" * 4 + target
    body += bytes((1, 1)) + ROUTER_LAN_MAC if options is None else options
    return icmp6_frame(ROUTER_LAN_MAC, b"\x33\x33\xff\x00\x00\x10", source, destination, body)


def test_valid_multicast_and_unicast_ns_return_solicited_override_na():
    for frame in (solicitation(), CLIENT_MAC + solicitation(destination=ADDRESS)[6:]):
        result = neighbor_reply(frame, ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC)
        assert result[:12] == ROUTER_LAN_MAC + CLIENT_MAC
        assert result[20:22] == bytes((58, 255))
        assert result[22:54] == ADDRESS + ROUTER
        body = result[54:]
        assert body[:2] == bytes((136, 0))
        assert body[4:8] == bytes.fromhex("60000000")
        assert body[8:24] == ADDRESS and body[24:] == bytes((2, 1)) + CLIENT_MAC
        assert checksum(ADDRESS + ROUTER + struct.pack("!I3xB", len(body), 58) + body) == 0


@pytest.mark.parametrize("length", [0, 12, 54, 77, 85])
def test_truncated_nd_cannot_produce_response(length):
    assert neighbor_reply(solicitation()[:length], ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC) is None


@pytest.mark.parametrize("offset", [0, 6, 12, 14, 18, 20, 21, 22, 38, 54, 55, 56, 70])
def test_misaddressed_invalid_header_or_checksum_ns_cannot_produce_response(offset):
    frame = bytearray(solicitation())
    frame[offset] ^= 0x10 if offset == 14 else 1
    assert neighbor_reply(bytes(frame), ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC) is None


@pytest.mark.parametrize(
    "options", [b"\x01\x00", b"\x01\x02" + b"\x00" * 6, b"\x01", b"\x01\x01" + b"\x00" * 6]
)
def test_rechecks_options_with_valid_checksum(options):
    assert (
        neighbor_reply(solicitation(options=options), ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC) is None
    )


def test_dad_multicast_source_and_other_target_are_outside_fixture_scope():
    for frame in (
        solicitation(source=b"\x00" * 16, options=b""),
        solicitation(source=ip6("ff02::1")),
        solicitation(target=ip6("2001:db8:1::11")),
    ):
        assert neighbor_reply(frame, ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC) is None


def test_unknown_well_formed_option_is_ignored_as_rfc_requires():
    frame = solicitation(options=bytes((254, 1)) + b"\x00" * 6)
    assert neighbor_reply(frame, ADDRESS, CLIENT_MAC, ROUTER_LAN_MAC) is not None
