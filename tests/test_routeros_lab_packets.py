"""Checks for the isolated lab's packet fixtures; no sockets or RouterOS needed."""

import pytest

from tests.routeros.packets import (
    CLIENT_MAC,
    Link,
    checksum,
    dhcp_options,
    dhcp_request,
    endpoint_match,
    ip,
    udp_frame,
    udp_payload,
)


def test_discover_and_request_have_valid_headers_and_identity():
    discover = dhcp_request(12345, 1)
    assert discover[:6] == b"\xff" * 6 and discover[6:12] == CLIENT_MAC
    assert checksum(discover[14:34]) == 0
    src, dst, body = udp_payload(discover)
    assert (src, dst) == (68, 67)
    assert body[:4] == bytes((1, 1, 6, 0)) and body[28:34] == CLIENT_MAC
    assert dhcp_options(body)[53] == b"\x01"
    request = dhcp_request(12345, 3, bytes((198, 51, 100, 10)), bytes((198, 51, 100, 1)))
    options = dhcp_options(udp_payload(request)[2])
    assert options[53] == b"\x03" and options[50] == bytes((198, 51, 100, 10))
    assert options[54] == bytes((198, 51, 100, 1))


def test_ipv4_fixture_checks_udp_checksum_when_present_and_accepts_legal_zero():
    packet = udp_frame(
        CLIENT_MAC,
        bytes.fromhex("02fa00000001"),
        ip("198.51.100.10"),
        ip("203.0.113.10"),
        47000,
        45001,
        b"checksum-fixture",
    )
    assert packet[40:42] != b"\x00\x00"
    assert udp_payload(packet) == (47000, 45001, b"checksum-fixture")
    corrupted = packet[:-1] + bytes((packet[-1] ^ 1,))
    assert udp_payload(corrupted) is None
    assert udp_payload(packet[:40] + b"\x00\x00" + packet[42:]) == udp_payload(packet)


def test_truncated_packet_fixtures_are_ignored():
    discover = dhcp_request(12345, 1)
    for length in (0, 12, 15, 34, 41, 80):
        assert udp_payload(discover[:length]) is None
    body = udp_payload(discover)[2]
    assert dhcp_options(body[:238]) == {}
    assert dhcp_options(body[:240] + b"\x35\x05\x01") == {}


def test_lab_has_no_arbitrary_socket_destination():
    with pytest.raises(ValueError, match="isolated"):
        Link(11434)


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [True, "42001", 4.5, 39999, 50000])
async def test_established_flow_port_validation_occurs_before_link_access(port):
    from tests.routeros.packets import forwarded_probe

    with pytest.raises(ValueError, match="synthetic"):
        await forwarded_probe(None, None, "198.51.100.10", client_port=port)


def test_topology_selects_unused_flow_tuples():
    from tests.routeros.topology import fresh_ports

    rows = [
        {
            "protocol": "udp",
            "src-address": "198.51.100.10:47000",
            "dst-address": "203.0.113.10:45001",
        },
        {
            "protocol": "udp",
            "src-address": "198.51.100.10:47002",
            "dst-address": "203.0.113.10:45001",
        },
    ]
    assert fresh_ports(rows, "198.51.100.10") == (47001, 47003)
    rows = [
        {
            "protocol": "udp",
            "src-address": f"198.51.100.10:{port}",
            "dst-address": "203.0.113.10:45001",
        }
        for port in range(47000, 49999)
    ]
    with pytest.raises(AssertionError, match="exhausted"):
        fresh_ports(rows, "198.51.100.10")


def test_native_udp_connection_tuple_supports_explicit_or_combined_ports():
    from tests.routeros.topology import fresh_ports, udp_tuple

    separate = {
        "protocol": "udp",
        "src-address": "198.51.100.10",
        "src-port": "47000",
        "dst-address": "203.0.113.10",
        "dst-port": 45001,
    }
    assert udp_tuple(separate) == ("198.51.100.10", 47000, "203.0.113.10", 45001)
    assert fresh_ports([separate], "198.51.100.10") == (47001, 47002)
    combined = {
        "protocol": "udp",
        "src-address": "198.51.100.10:47000",
        "dst-address": "203.0.113.10:45001",
    }
    assert udp_tuple(combined) == udp_tuple(separate)
    assert udp_tuple({**combined, "src-port": 47001}) is None
    assert udp_tuple({**separate, "src-port": True}) is None
    assert udp_tuple({**separate, "src-address": "2001:db8::10"}) is None


@pytest.mark.parametrize(
    "field", ["source_mac", "target_mac", "source_ip", "target_ip", "ports", "payload"]
)
def test_matching_nonce_is_not_delivery_to_a_wrong_endpoint(field):
    expected = {
        "source_mac": bytes.fromhex("02fa00000001"),
        "target_mac": CLIENT_MAC,
        "source_ip": ip("203.0.113.10"),
        "target_ip": ip("198.51.100.10"),
        "ports": (45001, 40001),
        "payload": b"fresh synthetic probe",
    }
    frame = udp_frame(
        expected["source_mac"],
        expected["target_mac"],
        expected["source_ip"],
        expected["target_ip"],
        *expected["ports"],
        expected["payload"],
    )
    assert endpoint_match(frame, **expected)
    wrong = {
        **expected,
        field: (45001, 40002) if field == "ports" else b"\x00" * len(expected[field]),
    }
    assert not endpoint_match(frame, **wrong)


def test_bad_ipv4_checksum_and_fragment_are_not_valid_probe_payloads():
    frame = bytearray(dhcp_request(12345, 1))
    frame[24] ^= 1
    assert udp_payload(frame) is None
    frame = bytearray(dhcp_request(12345, 1))
    frame[20:22] = b"\x20\x00"  # More fragments: this fixture never reassembles packets.
    frame[24:26] = b"\x00\x00"
    frame[24:26] = checksum(frame[14:34]).to_bytes(2, "big")
    assert udp_payload(frame) is None
