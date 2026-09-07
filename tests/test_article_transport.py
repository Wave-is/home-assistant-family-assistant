"""Public article URL, DNS pin, redirect, and transport-boundary tests."""

# Synthetic address strings are validation inputs, never listening sockets.
# ruff: noqa: S104

import asyncio
import ipaddress
import shutil
import ssl
import subprocess
import sys

import pytest

from custom_components.family_assistant.assistant import article
from custom_components.family_assistant.domain.validation import DomainError


async def current():
    return None


def hop(status=200, body=b"article", content_type="text/plain", **kwargs):
    return article._Hop(status, body, content_type, kwargs.get("charset"), kwargs.get("location"))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/article",
        "https://user:password@example.org/article",
        "https://example.org:8443/article",
        "https://example.org/article#fragment",
        "https://example.org\\@127.0.0.1/article",
        "https://example.org/%0a/article\n",
        "https://localhost/article",
        "https://host.local/article",
        "https://127.1/article",
        "https://2130706433/article",
        "https://[::1]/article",
        "file:///private",
    ],
)
async def test_malformed_non_https_credential_local_and_ambiguous_hosts_never_resolve(url):
    calls = []

    async def resolve(*args):
        calls.append(args)
        return ["93.184.216.34"]

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(url, scope_check=current, resolve=resolve)
    assert calls == []


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        f"{10}.{0}.{0}.{1}",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "192.0.2.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "ff00::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
        "2001:0000:4136:e378:8000:63bf:3fff:fdd2",
        "fe80::1%1",
    ],
)
async def test_every_special_or_translation_address_fails_before_transport(address):
    transports = []

    async def resolve(_host, _port):
        return [address]

    async def request(*args):
        transports.append(args)
        return hop()

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(
            "https://example.org/article",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=request,
        )
    assert transports == []


@pytest.mark.parametrize("address", ["::ffff:8.8.8.8", "::ffff:127.0.0.1"])
def test_ipv4_mapped_ipv6_is_conservatively_rejected_even_for_a_public_embedded_address(address):
    with pytest.raises(DomainError, match="article_invalid_url"):
        article._safe_address(address)


async def test_all_dns_answers_must_be_public_and_are_pinned_once_per_hop():
    resolved = []
    transported = []

    async def mixed(host, port):
        resolved.append((host, port))
        return ["93.184.216.34", "127.0.0.1"]

    async def request(*args):
        transported.append(args)
        return hop()

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(
            "https://example.org/article",
            scope_check=current,
            resolve=mixed,
            _test_request_hop=request,
        )
    assert resolved == [("example.org", 443)] and transported == []

    async def public(host, port):
        resolved.append((host, port))
        return ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]

    async def inspect_target(target, _scope):
        transported.append(target)
        return hop(body=b"Pinned")

    result = await article.fetch(
        "https://EXAMPLE.org/article?q=1",
        scope_check=current,
        resolve=public,
        _test_request_hop=inspect_target,
    )
    assert result["text"] == "Pinned"
    assert transported[-1].hostname == "example.org"
    assert transported[-1].addresses == (
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"),
    )


async def test_redirects_are_revalidated_reresolved_and_never_auto_followed():
    resolutions = []
    requests = []

    async def resolve(host, _port):
        resolutions.append(host)
        return {
            "first.example": ["93.184.216.34"],
            "second.example": ["8.8.8.8"],
        }[host]

    async def request(target, _scope):
        requests.append(target.url)
        if len(requests) == 1:
            return hop(302, location="https://second.example/final")
        return hop(body=b"Final article")

    result = await article.fetch(
        "https://first.example/start",
        scope_check=current,
        resolve=resolve,
        _test_request_hop=request,
    )
    assert resolutions == ["first.example", "second.example"]
    assert requests == ["https://first.example/start", "https://second.example/final"]
    assert result == {
        "title": "",
        "text": "Final article",
        "requested_url": "https://first.example/start",
        "final_url": "https://second.example/final",
    }


async def test_redirect_to_private_literal_is_rejected_without_dns_or_second_request():
    requests = []
    resolutions = []

    async def resolve(host, _port):
        resolutions.append(host)
        return ["93.184.216.34"]

    async def request(target, _scope):
        requests.append(target.url)
        return hop(302, location="https://169.254.169.254/latest/meta-data")

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(
            "https://example.org/start",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=request,
        )
    assert resolutions == ["example.org"]
    assert requests == ["https://example.org/start"]


@pytest.mark.parametrize("locations", [["/same"], ["/1", "/2", "/3", "/4"]])
async def test_redirect_loops_and_fourth_redirect_fail_closed(locations):
    calls = []

    async def resolve(_host, _port):
        return ["93.184.216.34"]

    async def request(target, _scope):
        calls.append(target.url)
        index = min(len(calls) - 1, len(locations) - 1)
        return hop(302, location=locations[index])

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(
            "https://example.org/same" if len(locations) == 1 else "https://example.org/0",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=request,
        )
    assert len(calls) <= 4


async def test_scope_is_checked_around_dns_transport_and_result_release():
    checks = 0

    async def scope():
        nonlocal checks
        checks += 1
        if checks == 6:
            raise DomainError("forbidden")

    async def resolve(_host, _port):
        return ["93.184.216.34"]

    async def request(_target, callback):
        await callback()
        return hop(body=b"must not escape")

    with pytest.raises(DomainError, match="forbidden"):
        await article.fetch(
            "https://example.org/article",
            scope_check=scope,
            resolve=resolve,
            _test_request_hop=request,
        )
    assert checks == 6


async def test_cancellation_propagates_and_total_timeout_is_code_only(monkeypatch):
    async def resolve(_host, _port):
        return ["93.184.216.34"]

    async def cancelled(_target, _scope):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await article.fetch(
            "https://example.org/article",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=cancelled,
        )

    monkeypatch.setattr(article, "TOTAL_TIMEOUT", 0.01)

    async def slow(_target, _scope):
        await asyncio.sleep(1)

    with pytest.raises(DomainError, match="article_timeout") as error:
        await article.fetch(
            "https://example.org/private-query?token=CANARY",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=slow,
        )
    assert "CANARY" not in str(error.value)


async def test_injected_transport_cannot_bypass_final_body_limit_or_status_validation():
    async def resolve(_host, _port):
        return ["93.184.216.34"]

    async def oversized(_target, _scope):
        return hop(body=b"x" * (article.MAX_BODY_BYTES + 1))

    with pytest.raises(DomainError, match="article_too_large"):
        await article.fetch(
            "https://example.org/article",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=oversized,
        )


async def test_pinned_resolver_never_performs_a_second_lookup_or_changes_hostname():
    target = article._PinnedTarget(
        "https://article.example/path",
        "article.example",
        443,
        (ipaddress.ip_address("93.184.216.34"),),
    )
    resolver = article._PinnedResolver(target)
    assert await resolver.resolve("article.example", 443, family=article.socket.AF_UNSPEC) == [
        article.ResolveResult(
            hostname="article.example",
            host="93.184.216.34",
            port=443,
            family=article.socket.AF_INET,
            proto=article.socket.IPPROTO_TCP,
            flags=article.socket.AI_NUMERICHOST | article.socket.AI_NUMERICSERV,
        )
    ]
    with pytest.raises(OSError):
        await resolver.resolve("rebound.example", 443)
    with pytest.raises(OSError):
        await resolver.resolve("article.example", 80)
    with pytest.raises(OSError):
        await resolver.resolve("article.example", 443, family=article.socket.AF_INET6)


def test_socket_factory_accepts_only_the_pinned_connection_tuple():
    target = article._PinnedTarget(
        "https://article.example/path",
        "article.example",
        443,
        (ipaddress.ip_address("93.184.216.34"),),
    )
    factory = article._pinned_socket_factory(target)
    for rejected in (
        (
            article.socket.AF_INET,
            article.socket.SOCK_STREAM,
            article.socket.IPPROTO_TCP,
            "",
            ("127.0.0.1", 443),
        ),
        (
            article.socket.AF_INET6,
            article.socket.SOCK_STREAM,
            article.socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        ),
        (
            article.socket.AF_INET,
            article.socket.SOCK_DGRAM,
            article.socket.IPPROTO_UDP,
            "",
            ("93.184.216.34", 443),
        ),
        (
            article.socket.AF_INET,
            article.socket.SOCK_STREAM,
            article.socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 80),
        ),
    ):
        with pytest.raises(OSError):
            factory(rejected)
    sock = factory(
        (
            article.socket.AF_INET,
            article.socket.SOCK_STREAM,
            article.socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    )
    sock.close()


async def test_excessive_dns_answer_set_fails_before_transport():
    requests = []

    async def resolve(_host, _port):
        return [f"8.8.8.{index}" for index in range(1, article.MAX_DNS_ADDRESSES + 2)]

    async def request(*args):
        requests.append(args)
        return hop()

    with pytest.raises(DomainError, match="article_invalid_url"):
        await article.fetch(
            "https://example.org/article",
            scope_check=current,
            resolve=resolve,
            _test_request_hop=request,
        )
    assert requests == []


def _generate_tls_material(cert, key):
    if sys.platform == "win32":
        executable = shutil.which("pwsh") or shutil.which("powershell")
        if executable is None:
            pytest.skip("PowerShell is required to generate a synthetic TLS certificate")
        script = cert.parent / "generate-article-tls.ps1"
        script.write_text(
            r"""
param([string]$CertPath,[string]$KeyPath)
$rsa=[System.Security.Cryptography.RSA]::Create(2048)
$name=[System.Security.Cryptography.X509Certificates.X500DistinguishedName]::new('CN=article.test')
$request=[System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
  $name,$rsa,[System.Security.Cryptography.HashAlgorithmName]::SHA256,
  [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
$san=[System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$san.AddDnsName('article.test')
$request.CertificateExtensions.Add($san.Build())
$certificate=$request.CreateSelfSigned(
  [DateTimeOffset]::UtcNow.AddMinutes(-5),[DateTimeOffset]::UtcNow.AddHours(1))
[IO.File]::WriteAllText($CertPath,$certificate.ExportCertificatePem())
[IO.File]::WriteAllText($KeyPath,$rsa.ExportPkcs8PrivateKeyPem())
""",
            encoding="utf-8",
        )
        subprocess.run(  # noqa: S603
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(script),
                str(cert),
                str(key),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return
    executable = shutil.which("openssl")
    if executable is None:
        pytest.skip("OpenSSL is required to generate a synthetic TLS certificate")
    subprocess.run(  # noqa: S603
        [
            executable,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=article.test",
            "-addext",
            "subjectAltName=DNS:article.test",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )


@pytest.fixture(scope="module")
def tls_material(tmp_path_factory):
    directory = tmp_path_factory.mktemp("article-tls")
    cert = directory / "article-cert.pem"
    key = directory / "article-key.pem"
    _generate_tls_material(cert, key)
    return cert, key


async def _tls_hop(tls_material, response_bytes):
    cert, key = tls_material
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.load_cert_chain(cert, key)
    received = []

    async def handler(reader, writer):
        received.append(await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2))
        writer.write(response_bytes)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=server_ssl)
    try:
        port = server.sockets[0].getsockname()[1]
        target = article._PinnedTarget(
            f"https://article.test:{port}/one",
            "article.test",
            port,
            (ipaddress.ip_address("127.0.0.1"),),
        )
        client_ssl = ssl.create_default_context(cafile=str(cert))
        response = await article._request_hop(target, current, ssl_context=client_ssl)
    finally:
        server.close()
        await server.wait_closed()
    return response, received[0].decode("ascii")


async def test_real_tls_socket_uses_pinned_resolver_original_host_and_no_ambient_headers(
    tls_material,
):
    response, request = await _tls_hop(
        tls_material,
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
        b"Content-Length: 13\r\nSet-Cookie: never=return\r\nConnection: close\r\n\r\n"
        b"Pinned socket",
    )
    assert response.body == b"Pinned socket"
    assert "Host: article.test:" in request
    assert "Accept-Encoding: identity\r\n" in request
    for forbidden in ("Authorization:", "Cookie:", "Referer:"):
        assert forbidden not in request


@pytest.mark.parametrize(
    "response,code",
    [
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Encoding: gzip\r\n"
            b"Content-Length: 1\r\nConnection: close\r\n\r\nx",
            "article_unsupported",
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 524289\r\n"
            b"Connection: close\r\n\r\n",
            "article_too_large",
        ),
        (
            b"HTTP/1.1 302 Found\r\nLocation: https://one.example\r\n"
            b"Location: https://two.example\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
            "article_invalid_content",
        ),
    ],
    ids=["compressed", "declared-size", "duplicate-location"],
)
async def test_real_tls_hop_rejects_encoding_declared_size_and_ambiguous_redirect(
    tls_material, response, code
):
    with pytest.raises(DomainError, match=code):
        await _tls_hop(tls_material, response)
