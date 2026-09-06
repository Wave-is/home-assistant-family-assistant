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
