"""Checks for the isolated lab's packet fixtures; no sockets or RouterOS needed."""

import pytest

from tests.routeros.packets import (
    CLIENT_MAC,
    Link,
    checksum,
    dhcp_options,
    dhcp_request,
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
