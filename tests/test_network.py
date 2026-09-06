"""Synthetic RouterOS REST tables and conservative identity suggestions."""

import json

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.client import (
    TABLES,
    RouterClient,
    certificate_context,
)
from custom_components.family_assistant.network.inventory import build, mac


class Response:
    def __init__(self, status, payload):
        self.status, self.payload, self.content = status, payload, self

    async def __aenter__(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self

    async def __aexit__(self, *_):
        pass

    async def iter_chunked(self, _):
        yield self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def client(session, **config):
    return RouterClient(
        session,
        {
            "url": "https://router.example.org",
            "username": "test-reader",
            "password": "synthetic-only",
            **config,
        },
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://router.example.org",
        "https://user:pass@router.example.org",
        "https://router.example.org/rest/../system",
        "https://router.example.org/?password=x",
        "https://router.example.org/#x",
    ],
)
def test_https_endpoint_scope(url):
    with pytest.raises(DomainError, match="network_url"):
        client(Session(), url=url)


def test_tls_validation_cannot_be_disabled():
    with pytest.raises(DomainError, match="network_certificate"):
        RouterClient(
            Session(),
            {"url": "https://router.example.org", "username": "r", "password": "synthetic-only"},
            False,
        )
    with pytest.raises(DomainError, match="network_certificate"):
        certificate_context("not a certificate")


@pytest.mark.asyncio
async def test_field_projection_readonly_and_no_redirects():
    session = Session(
        Response(
            200,
            [
                {
                    ".id": "*1",
                    "address": "198.51.100.10",
                    "password": "do-not-export",
                    "dynamic": "true",
                }
            ],
        )
    )
    rows = await client(session).read("leases")
    assert "password" not in rows[0] and rows[0]["dynamic"] == "true"
    method, url, args = session.calls[0]
    assert method == "GET" and url.endswith("/rest/ip/dhcp-server/lease")
    assert args["allow_redirects"] is False and args["ssl"] is True
    assert "password" not in args["params"][".proplist"]
    with pytest.raises(DomainError, match="network_operation"):
        await client(session).read("system/reboot")
    assert len(session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,code",
    [
        (401, {}, "network_authentication"),
        (403, {}, "network_permission"),
        (404, {}, "network_missing"),
        (302, {}, "network_unreachable"),
        (200, TimeoutError(), "network_timeout"),
        (200, b"x" * 2097153, "network_response"),
        (200, [{"dynamic": False}], "network_response"),
    ],
    ids=["authentication", "permission", "missing", "redirect", "timeout", "oversize", "bad-type"],
)
async def test_read_failures_are_stable_and_bounded(status, body, code):
    with pytest.raises(DomainError, match=code):
        await client(Session(Response(status, body))).read("leases")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail,code",
    [
        ("no such command or directory (wireless)", "network_missing"),
        ("no such command or directory (unrelated)", "network_unreachable"),
        ("invalid value of argument .proplist", "network_unreachable"),
    ],
)
async def test_native_400_missing_package_is_not_a_router_outage(detail, code):
    session = Session(Response(400, {"error": 400, "message": "Bad Request", "detail": detail}))
    with pytest.raises(DomainError, match=code):
        await client(session).read("wireless")


@pytest.mark.asyncio
async def test_missing_optional_package_keeps_remaining_inventory():
    missing = Response(400, {"detail": "no such command or directory (wireless)"})
    responses = [Response(200, tables()["leases"])]
    responses += [
        missing if "wireless" in name else Response(200, []) for name in TABLES if name != "leases"
    ]
    result = await client(Session(*responses)).inventory()
    assert len(result["leases"]) == 1
    assert result["capabilities"]["wireless"] == "network_missing"
    assert result["capabilities"]["wireless_access"] == "network_missing"
    assert result["capabilities"]["kids"] == "available"


@pytest.mark.asyncio
async def test_missing_command_on_write_is_not_optional_success():
    session = Session(Response(400, {"detail": "no such command or directory (make-static)"}))
    with pytest.raises(DomainError, match="network_unreachable"):
        await client(session, allow_write=True).make_static("*1")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 500])
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_native_permission_trap_is_not_a_connection_failure(status, method):
    session = Session(Response(status, {"detail": "not enough permissions (9)"}))
    with pytest.raises(DomainError, match="network_permission"):
        await client(session)._request(method, "ip/dhcp-server/lease")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail",
    ["not enough permissions (8)", "Internal failure", "no such command or directory (wireless)"],
)
async def test_other_500_errors_are_not_misclassified_as_permission_or_optional(detail):
    with pytest.raises(DomainError, match="network_unreachable"):
        await client(Session(Response(500, {"detail": detail}))).read("wireless")


def test_mac_normalization_no_multicast():
    assert mac("021122334455") == "02:11:22:33:44:55"
    assert mac("02-11-22-33-44-55") == "02:11:22:33:44:55"
    assert mac("01:11:22:33:44:55") is None
    assert mac("00:00:00:00:00:00") is None


def tables():
    return {
        "leases": [
            {
                ".id": "*1",
                "mac-address": "02:11:22:33:44:55",
                "address": "198.51.100.10",
                "status": "bound",
                "host-name": "mobile",
                "dynamic": "true",
                "comment": "Keep me",
            }
        ],
        "capabilities": {"wifi": "network_missing"},
    }


def test_exact_mac_evidence_and_ambiguity(now):
    candidate = {"id": "ha1", "name": "Example phone", "macs": ["02:11:22:33:44:55"]}
    observed = build(tables(), [candidate], now)["devices"][0]
    assert observed["suggested_name"] == "Example phone"
    assert observed["comments"] == ["Keep me"]
    assert observed["suggestions"][0]["evidence"] == ["exact_mac"]
    assert "locally_administered" in observed["warnings"]
    ambiguous = build(tables(), [candidate, {**candidate, "id": "ha2", "name": "Another"}], now)[
        "devices"
    ][0]
    assert ambiguous["suggested_name"] is None and "ambiguous_identity" in ambiguous["warnings"]


def test_stale_ip_and_hostname_cannot_automatically_name(now):
    candidate = {"id": "ha1", "name": "Old tracker", "ips": ["198.51.100.10"], "current": False}
    assert not build(tables(), [candidate], now)["devices"][0]["suggestions"]
    candidate["current"] = True
    assert build(tables(), [candidate], now)["devices"][0]["suggested_name"] == "Old tracker"
    stale = tables()
    stale["leases"][0]["status"] = "waiting"
    assert not build(stale, [candidate], now)["devices"][0]["suggestions"]
    candidate["hostnames"] = ["MOBILE"]
    item = build(stale, [candidate], now)["devices"][0]
    assert item["suggested_name"] is None and item["suggestions"][0]["confidence"] == 40


def test_router_interfaces_are_protected_and_features_not_guessed(now):
    source = tables()
    source["interfaces"] = [{"mac-address": "02:11:22:33:44:55"}]
    source["filters"] = [{"action": "fasttrack-connection", "disabled": "false"}]
    result = build(source, [], now)
    assert result["devices"][0]["protected"] and result["fasttrack"]
    assert result["ipv6"] == "unknown_or_enabled"
    assert result["capabilities"]["wifi"] == "network_missing"


@pytest.mark.asyncio
async def test_typed_write_methods_require_opt_in_and_do_not_accept_console_paths():
    session = Session(Response(200, []), Response(200, {}), Response(204, b""))
    reader = client(session)
    with pytest.raises(DomainError, match="network_readonly"):
        await reader.make_static("*1")
    writer = client(session, allow_write=True)
    with pytest.raises(DomainError, match="network_target"):
        await writer.make_static("*1/../system/reboot")
    await writer.make_static("*1")
    await writer.set_comment("*A", "Chosen name; still JSON data")
    await writer.remove_reservation("*A")
    assert [call[0] for call in session.calls] == ["POST", "PATCH", "DELETE"]
    assert session.calls[0][2]["json"] == {"numbers": "*1"}
    assert session.calls[1][2]["json"] == {"comment": "Chosen name; still JSON data"}
