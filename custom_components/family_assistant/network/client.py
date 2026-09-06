"""Bounded HTTPS REST reads with explicit tables and field-level allowlists."""

import base64
import json
import ssl
from urllib.parse import urlsplit

import aiohttp

from ..assistant.http import endpoint
from ..domain.validation import DomainError, text

TABLES = {
    "resource": ("system/resource", "version,board-name,architecture-name,uptime"),
    "clock": ("system/clock", "date,time,time-zone-name,gmt-offset"),
    "leases": (
        "ip/dhcp-server/lease",
        ".id,address,active-address,mac-address,active-mac-address,host-name,client-id,"
        "server,active-server,dynamic,disabled,blocked,status,comment,last-seen",
    ),
    "servers": ("ip/dhcp-server", ".id,name,interface,disabled,invalid,address-pool"),
    "networks": ("ip/dhcp-server/network", ".id,address,gateway"),
    "addresses": ("ip/address", ".id,address,network,interface,actual-interface,disabled,invalid"),
    "arp": ("ip/arp", ".id,address,mac-address,interface,dynamic,complete,status"),
    "bridge": ("interface/bridge/host", ".id,mac-address,on-interface,bridge,local,vid"),
    "interfaces": ("interface", ".id,name,type,mac-address,running,disabled"),
    "wifi": ("interface/wifi/registration-table", ".id,mac-address,interface,uptime"),
    "wireless": ("interface/wireless/registration-table", ".id,mac-address,interface,uptime"),
    "wifi_access": (
        "interface/wifi/access-list",
        ".id,mac-address,interface,action,disabled,comment",
    ),
    "wireless_access": (
        "interface/wireless/access-list",
        ".id,mac-address,interface,authentication,disabled,comment",
    ),
    "kids": (
        "ip/kid-control",
        ".id,name,mon,tue,wed,thu,fri,sat,sun,disabled,paused,blocked,"
        "rate-limit,tur-mon,tur-tue,tur-wed,tur-thu,tur-fri,tur-sat,tur-sun",
    ),
    "kid_devices": (
        "ip/kid-control/device",
        ".id,name,mac-address,user,disabled,dynamic,blocked,limited,inactive",
    ),
    "filters": ("ip/firewall/filter", ".id,chain,action,disabled,dynamic,comment"),
    "ipv6": ("ipv6/settings", "disable-ipv6,forward"),
}


def certificate_context(pem=""):
    """Call in HA's executor: loading system certificate roots performs file IO."""
    try:
        context = ssl.create_default_context()
        if pem:
            if not isinstance(pem, str) or len(pem) > 65536 or "PRIVATE KEY" in pem:
                raise ValueError
            context.load_verify_locations(cadata=pem)
        return context
    except (ValueError, ssl.SSLError):
        raise DomainError("network_certificate") from None


class RouterClient:
    def __init__(self, session, config, tls_context=True):
        try:
            self.url = endpoint(config.get("url", ""))
            if urlsplit(self.url).path not in {"", "/rest"}:
                raise ValueError
            self.url = self.url.removesuffix("/rest") + "/rest"
        except (DomainError, ValueError):
            raise DomainError("network_url") from None
        self.session = session
        self._write_enabled = config.get("allow_write") is True
        self._kid_enabled = config.get("allow_kid_control") is True
        username = text(config.get("username"), "username", 128)
        text(config.get("password"), "password", 1024)
        password = config["password"]  # Leading/trailing password spaces are significant.
        if ":" in username or any(ord(c) < 32 for c in username):
            raise DomainError("invalid_field", "username")
        try:
            self._headers = {
                "Authorization": "Basic "
                + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
            }
        except UnicodeError:
            raise DomainError("invalid_field", "credentials") from None
        if tls_context is False:
            raise DomainError("network_certificate")
        self._tls = tls_context

    async def read(self, table):
        if table not in TABLES:
            raise DomainError("network_operation")
        path, properties = TABLES[table]
        result = await self._request("GET", path, params={".proplist": properties})
        if isinstance(result, dict) and table in {"resource", "clock", "ipv6"}:
            result = [result]
        if not isinstance(result, list) or len(result) > 10000:
            raise DomainError("network_response")
        allowed = set(properties.split(","))
        clean = []
        for row in result:
            if not isinstance(row, dict) or any(not isinstance(v, str) for v in row.values()):
                raise DomainError("network_response")
            # Defensive projection even if RouterOS ignores .proplist.
            clean.append({k: v[:2048] for k, v in row.items() if k in allowed})
        return clean

    async def inspect(self):
        resource = await self.read("resource")
        if len(resource) != 1 or not resource[0].get("version", "").startswith("7."):
            raise DomainError("network_version")
        await self.read("leases")
        return {"version": resource[0]["version"]}

    def _write_target(self, target):
        from .leases import identifier

        if not self._write_enabled:
            raise DomainError("network_readonly")
        return identifier(target)

    async def make_static(self, target):
        target = self._write_target(target)
        await self._request("POST", "ip/dhcp-server/lease/make-static", json={"numbers": target})

    async def set_comment(self, target, comment):
        target = self._write_target(target)
        if not isinstance(comment, str) or len(comment) > 255 or any(ord(c) < 32 for c in comment):
            raise DomainError("invalid_field", "comment")
        await self._request("PATCH", "ip/dhcp-server/lease/" + target, json={"comment": comment})

    async def remove_reservation(self, target):
        """Only for an explicitly approved rollback of a newly converted lease."""
        target = self._write_target(target)
        await self._request("DELETE", "ip/dhcp-server/lease/" + target)

    def _kid_target(self, target):
        from .leases import identifier

        if not self._kid_enabled:
            raise DomainError("network_readonly")
        return identifier(target)

    async def set_kid_profile(self, target, changes):
        from .kids import DAYS, rate, windows

        target = self._kid_target(target)
        allowed = {"disabled", "rate-limit", *DAYS, *("tur-" + d for d in DAYS)}
        if not isinstance(changes, dict) or not changes or changes.keys() - allowed:
            raise DomainError("network_operation")
        for key, value in changes.items():
            if key == "disabled":
                if value not in {"true", "false"}:
                    raise DomainError("invalid_field", key)
            elif key == "rate-limit":
                rate(value)
            else:
                windows(value)
        await self._request("PATCH", "ip/kid-control/" + target, json=changes)

    async def pause_kid(self, target, paused):
        target = self._kid_target(target)
        if type(paused) is not bool:
            raise DomainError("invalid_field", "paused")
        await self._request(
            "POST", "ip/kid-control/" + ("pause" if paused else "resume"), json={"numbers": target}
        )

    async def kid_timers(self, timer_name):
        from .kid_timer import name

        properties = (
            ".id,name,on-event,start-date,start-time,interval,policy,disabled,comment,run-count"
        )
        result = await self._request(
            "GET", "system/scheduler", params={"name": name(timer_name), ".proplist": properties}
        )
        if not isinstance(result, list) or any(not isinstance(r, dict) for r in result):
            raise DomainError("network_response")
        selected = [r for r in result if r.get("name") == timer_name]
        if any(not isinstance(v, str) or len(v) > 8192 for row in selected for v in row.values()):
            raise DomainError("network_response")
        return [{k: v for k, v in row.items() if k in properties.split(",")} for row in selected]

    async def install_kid_timer(self, plan, timer_name):
        from .kid_timer import specifications

        self._kid_target(plan["binding"]["profile_id"])
        specs = [s for s in specifications(plan) if s["name"] == timer_name]
        if len(specs) != 1:
            raise DomainError("network_operation")
        await self._request("PUT", "system/scheduler", json=specs[0])

    async def remove_kid_timer(self, target, timer_name):
        target = self._kid_target(target)
        rows = await self.kid_timers(timer_name)
        if len(rows) != 1 or rows[0].get(".id") != target:
            raise DomainError("network_conflict")
        await self._request("DELETE", "system/scheduler/" + target)

    async def inventory(self):
        # Required table failing does not replace a known inventory with an empty list.
        result = {"leases": await self.read("leases"), "capabilities": {}}
        for name in TABLES:
            if name == "leases":
                continue
            try:
                result[name] = await self.read(name)
                result["capabilities"][name] = "available"
            except DomainError as err:
                if err.code not in {"network_missing", "network_permission"}:
                    raise
                result["capabilities"][name] = err.code
        return result

    async def _request(self, method, path, **kwargs):
        try:
            async with self.session.request(
                method,
                self.url + "/" + path,
                headers=self._headers,
                ssl=self._tls,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10, connect=4),
                **kwargs,
            ) as response:
                if response.status == 401:
                    raise DomainError("network_authentication")
                if response.status == 403:
                    raise DomainError("network_permission")
                if response.status == 404:
                    raise DomainError("network_missing")
                if not 200 <= response.status < 300:
                    raise DomainError("network_unreachable")
                body = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    body.extend(chunk)
                    if len(body) > 2097152:
                        raise DomainError("network_response")
                return None if method == "DELETE" and not body else json.loads(body)
        except DomainError:
            raise
        except aiohttp.ClientSSLError:
            raise DomainError("network_certificate") from None
        except TimeoutError:
            raise DomainError("network_timeout") from None
        except (aiohttp.ClientError, OSError):
            raise DomainError("network_unreachable") from None
        except (ValueError, UnicodeError, RecursionError):
            raise DomainError("network_response") from None
