"""Developer-only native CHR/REST acceptance, in a network-disabled container.

No household credentials or physical interfaces are accepted. The VM disk is a
temporary copy of the operator-provided official CHR archive. QEMU user-mode
networking is restricted and its HTTPS forward binds container-only loopback.
"""

import asyncio
import hashlib
import os
import re
import secrets
import shutil
import ssl
import sys
import tempfile
import zipfile
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class VirtualRouter:
    def __init__(self, disk):
        self.disk = disk
        self.process = None
        self.pending = ""
        self.password = secrets.token_urlsafe(24)

    async def expect(self, patterns, seconds=45):
        async with asyncio.timeout(seconds):
            while True:
                for index, pattern in enumerate(patterns):
                    match = re.search(pattern, self.pending, re.I)
                    if match:
                        before = self.pending[: match.end()]
                        self.pending = self.pending[match.end() :]
                        return index, before
                data = await self.process.stdout.read(4096)
                if not data:
                    raise RuntimeError("Virtual router console closed")
                clean = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", data.decode("utf-8", "replace"))
                self.pending = (self.pending + clean)[-32768:]

    async def send(self, text):
        self.process.stdin.write((text + "\r").encode())
        await self.process.stdin.drain()

    async def boot(self, existing=False):
        self.pending = ""
        nic_model = os.environ.get("FAMILY_ROUTEROS_NIC", "vmxnet3")
        if nic_model not in {"virtio-net-pci", "vmxnet3"}:
            raise RuntimeError("Only reviewed isolated FastPath-capable NIC models are accepted")
        self.process = await asyncio.create_subprocess_exec(
            "/usr/bin/qemu-system-x86_64",
            "-machine",
            "pc,accel=tcg",
            "-m",
            "256",
            "-smp",
            "1",
            "-drive",
            f"file={self.disk},format=raw,if=ide",
            "-nic",
            f"user,model={nic_model},net=192.0.2.0/24,dhcpstart=192.0.2.15,"
            "restrict=on,hostfwd=tcp:127.0.0.1:18443-:443",
            "-netdev",
            "socket,id=lan,udp=127.0.0.1:30001,localaddr=127.0.0.1:30002",
            "-device",
            f"{nic_model},netdev=lan,mac=02:FA:00:00:00:01",
            "-netdev",
            "socket,id=server,udp=127.0.0.1:30003,localaddr=127.0.0.1:30004",
            "-device",
            f"{nic_model},netdev=server,mac=02:FA:00:00:00:02",
            "-display",
            "none",
            "-monitor",
            "none",
            "-serial",
            "stdio",
            "-no-reboot",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await self.expect([r"Login:"], 120)
        # Official console login options: no colour, detection or line editor.
        await self.send("admin+cte")
        await self.expect([r"Password:"])
        await self.send(self.password if existing else "")
        patterns = [r"Do you want to see.*?\[.*?\]:?", r"new password>", r"\[admin@[^\]]+\]\s*>\s*"]
        index, _ = await self.expect(patterns)
        if index == 0:
            await self.send("n")
            index, _ = await self.expect(patterns)
        if index == 1:
            await self.send(self.password)
            # Password input may redraw the original prompt. Only the next
            # distinct phase may trigger another response.
            await self.expect([r"repeat new password>"])
            await self.send(self.password)
            try:
                await self.expect([r"\[admin@[^\]]+\]\s*>\s*"])
            except TimeoutError:
                # Report only semantic flags, never console text or passwords.
                print(
                    "Virtual login diagnostic flags:",
                    {
                        "password_mismatch": "do not match" in self.pending.lower(),
                        "new_password_prompt": "new password>" in self.pending.lower(),
                        "admin_prompt": "[admin@" in self.pending,
                        "login_prompt": "login:" in self.pending.lower(),
                        "failure": "failure" in self.pending.lower(),
                    },
                    flush=True,
                )
                raise
        elif index != 2:
            raise RuntimeError("Virtual router login did not complete")
        print("PASS: isolated native RouterOS console ready", flush=True)

    async def command(self, source):
        marker = "FA_DONE_" + secrets.token_hex(6)
        await self.send(source + '; :put "' + marker + '"')
        status, output = await self.expect(
            [
                r"[\r\n]" + marker + r"[\r\n]",
                r"(?:failure:|syntax error|no such item|input does not match|"
                r"expected end of command)",
            ],
            60,
        )
        if status:
            safe_lines = [
                line
                for line in output.replace(self.password, "[omitted]").splitlines()
                if re.search(
                    r"failure:|error:|no such|not found|input does not|expected end", line, re.I
                )
                and "password" not in line.casefold()
            ]
            raise RuntimeError("Virtual console rejected command: " + " ".join(safe_lines)[-600:])
        await self.expect([r"\[admin@[^\]]+\]\s*>\s*"])
        return output

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 10)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def reboot(self):
        """Orderly reboot of this disposable disk only; no physical target input."""
        await self.send("/system reboot")
        await self.expect([r"Reboot.*?\[y/N\]"])
        await self.send("y")
        # -no-reboot exits QEMU on the guest's reset request. Start the same
        # persisted test disk again to exercise RouterOS startup schedulers.
        await asyncio.wait_for(self.process.wait(), 60)
        await self.boot(existing=True)


async def main():
    if os.environ.get("FAMILY_ROUTEROS_ISOLATED") != "1":
        raise RuntimeError("Use the isolated network-disabled developer container")
    archive = Path("/input/chr.img.zip")
    expected = os.environ.get("FAMILY_ROUTEROS_SHA256", "")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise RuntimeError("A verified archive checksum is required")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected.lower():
        raise RuntimeError("CHR archive checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="family-routeros-") as temporary:
        disk = Path(temporary) / "test.img"
        with zipfile.ZipFile(archive) as zipped:
            images = [i for i in zipped.infolist() if i.filename.endswith(".img")]
            if len(images) != 1 or images[0].file_size > 300_000_000:
                raise RuntimeError("Unexpected CHR archive")
            with zipped.open(images[0]) as source, disk.open("wb") as target:
                shutil.copyfileobj(source, target)
        vm = VirtualRouter(disk)
        try:
            await vm.boot()
            output = await vm.command(":put [/system resource get version]")
            version = re.search(r"\b7\.\d+\.\d+\b", output)
            assert version
            print("Native test version:", version[0], flush=True)
            await rest_acceptance(vm)
        finally:
            await vm.close()


async def rest_acceptance(vm):
    """Bootstrap only the isolated VM. Runtime client keeps verified HTTPS."""
    from datetime import UTC, datetime

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.network.client import RouterClient

    now = datetime.now(UTC)
    await vm.command(
        "/system clock set time-zone-name=Etc/UTC date="
        + now.strftime("%Y-%m-%d")
        + " time="
        + now.strftime("%H:%M:%S")
    )
    await vm.command(
        "/ip dhcp-client disable [find]; /ip address add address=192.0.2.15/24 interface=ether1"
    )
    await vm.command('/user set [find name=admin] password="' + vm.password + '"')
    await vm.command(
        "/certificate add name=fa-rest common-name=localhost subject-alt-name=IP:127.0.0.1 "
        "key-size=2048 days-valid=1 "
        "key-usage=digital-signature,key-encipherment,key-cert-sign,tls-server"
    )
    await vm.command("/certificate sign [find name=fa-rest]")
    await vm.command(
        "/certificate export-certificate [find name=fa-rest] type=pem file-name=fa-rest"
    )
    print("PASS: virtual test certificate created and exported", flush=True)
    output = await vm.command(':put [/file get [find where name~"fa-rest.*crt"] contents]')
    cert = re.search(r"-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----", output)
    if not cert:
        raise RuntimeError("Virtual router test certificate was not exported")
    context = ssl.create_default_context(cadata=cert[0].replace("\r", ""))
    await vm.command("/ip service set www-ssl disabled=no certificate=fa-rest address=192.0.2.2/32")
    # A bootstrap administrator is necessary only to build the empty test VM.
    # Every integration request below uses the documented limited service role.
    await vm.command("/user group add name=fa-rest policy=read,write,rest-api")
    await vm.command(
        '/user add name=fa-client group=fa-rest address=192.0.2.2/32 password="' + vm.password + '"'
    )
    async with aiohttp.ClientSession() as session:
        client = RouterClient(
            session,
            {
                "url": "https://127.0.0.1:18443",
                "username": "fa-client",
                "password": vm.password,
                "allow_kid_control": True,
                "allow_write": True,
            },
            context,
        )
        try:
            result = await client.inspect()
            policies = "read,rest-api"
        except DomainError as error:
            if error.code != "network_authentication":
                raise
            output = await vm.command(
                ':foreach i in=[/log find where message~"login failure.*fa-client"] '
                "do={ :put [/log get $i message] }"
            )
            for line in output.splitlines():
                if line.startswith("login failure"):
                    print("Synthetic account diagnostic:", line, flush=True)
            # The native REST-to-API bridge on some builds also checks the api
            # login policy. Test that narrowly, keeping both source restrictions.
            await vm.command("/user group set [find name=fa-rest] policy=read,write,api,rest-api")
            result = await client.inspect()
            policies = "read,api,rest-api"
            print(
                "Native REST requires api in addition to read,write,rest-api on this build",
                flush=True,
            )
        await vm.command("/user group add name=fa-audit policy=" + policies)
        await vm.command(
            '/user add name=fa-audit group=fa-audit address=192.0.2.2/32 password="'
            + vm.password
            + '"'
        )
        audit = RouterClient(
            session,
            {
                "url": "https://127.0.0.1:18443",
                "username": "fa-audit",
                "password": vm.password,
                "allow_write": True,
            },
            context,
        )
        await audit.inspect()
        assert result["version"].startswith("7.")
        tables = await client.inventory()
        print(
            "PASS: native limited-role verified-HTTPS REST inventory; table capabilities:",
            tables["capabilities"],
            flush=True,
        )
        from tests.routeros.packets import Link, dhcp_bind, forwarded_probe

        await vm.command("/ip address add address=198.51.100.1/24 interface=ether2")
        await vm.command("/ip address add address=203.0.113.1/24 interface=ether3")
        await vm.command("/ip pool add name=fa-lan ranges=198.51.100.10-198.51.100.20")
        await vm.command(
            "/ip dhcp-server add name=fa-lan interface=ether2 address-pool=fa-lan "
            "lease-time=1h disabled=no"
        )
        await vm.command("/ip dhcp-server network add address=198.51.100.0/24 gateway=198.51.100.1")
        lan, server_link = Link(30001), Link(30003)
        try:
            address = await dhcp_bind(lan)
            print("PASS: native DHCP discover/offer/request/ack", flush=True)
            assert await forwarded_probe(lan, server_link, address), "Baseline routed UDP failed"
            print("PASS: baseline bidirectional routed IPv4 UDP", flush=True)
            if os.environ.get("FAMILY_ROUTEROS_TOPOLOGY_ONLY") == "1":
                print("FOCUSED RUN: lease/timer lifecycle suite omitted, topology only", flush=True)
            else:
                from tests.routeros.lease_faults import native_lease_faults

                address = await native_lease_faults(client, audit, lan, server_link, address)
                await native_leases(client, audit, address)
                address = await native_lease_faults(client, audit, lan, server_link, address)
                await native_kids(vm, client, lan, server_link, address)
            from tests.routeros.topology import verify_topology

            await verify_topology(vm, client, lan, server_link, address)
        finally:
            lan.close()
            server_link.close()


async def native_leases(client, audit, address):
    from copy import deepcopy
    from datetime import UTC, datetime

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.network.lease_executor import LeaseExecutor
    from custom_components.family_assistant.network.leases import preview, readback_match

    tables = await client.inventory()
    row = next(r for r in tables["leases"] if r["address"] == address)
    assert row["dynamic"] == "true" and row["status"] == "bound"
    try:
        await audit.set_comment(row[".id"], "Must not be written")
    except DomainError as error:
        assert error.code == "network_permission"
        assert (await audit.read("leases"))[0].get("comment", "") == row.get("comment", "")
        print("PASS: native read-only account rejects write:", error.code, flush=True)
    else:
        raise AssertionError("Native read-only role unexpectedly allowed a write")
    now = datetime.now(UTC)
    plan = preview(tables, [{"id": row[".id"], "comment": "Synthetic client reservation"}], now)
    journal = []

    async def persist(progress):
        journal.append(deepcopy(progress))

    worker = LeaseExecutor(client, plan, persist, lambda: True)
    result = await worker.run(now, dhcp_recovery=True)
    assert result["status"] == "applied", result
    assert await worker.run(now, result, dhcp_recovery=True) == result
    actual = readback_match(plan["targets"][0], await client.read("leases"))
    assert actual["dynamic"] == "false" and actual["address"] == address
    assert actual["comment"] == "Synthetic client reservation"
    print("PASS: native REST dynamic lease conversion/comment/read-back/replay", flush=True)


async def native_kids(vm, client, lan, server_link, address):
    from copy import deepcopy
    from datetime import UTC, datetime

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.network import kid_timer, kids
    from custom_components.family_assistant.network.kid_executor import KidExecutor
    from tests.routeros.packets import forwarded_probe

    async def traffic(expected):
        # RouterOS propagates profile changes into dynamic rules asynchronously.
        for _ in range(6):
            if await forwarded_probe(lan, server_link, address) is expected:
                if not expected:
                    assert await forwarded_probe(
                        lan,
                        server_link,
                        "198.51.100.30",
                        client_mac=bytes.fromhex("021122334477"),
                    ), "Control client must remain reachable while the child is blocked"
                return
            await asyncio.sleep(1)
        raise AssertionError(f"Routed UDP did not reach expected allowed={expected}")

    native = await client._request(
        "PUT",
        "ip/kid-control",
        json={"name": "Synthetic child", **dict.fromkeys(kids.DAYS, "07:30-24:00")},
    )
    device = await client._request(
        "PUT",
        "ip/kid-control/device",
        json={
            "name": "Synthetic test client",
            "user": "Synthetic child",
            "mac-address": "02:11:22:33:44:55",
        },
    )
    tables = await client.inventory()
    binding = {**kids.bind(tables, native[".id"], [device[".id"]]), "member": "test-child"}
    assert kids.profile(tables["kids"][0])["mon"] == "07:30-24:00"
    print("PASS: native REST profile duration and membership projection", flush=True)
    await client.set_kid_profile(native[".id"], dict.fromkeys(kids.DAYS, "00:00-24:00"))
    await traffic(True)
    for sequence, mode in enumerate(
        ("pause", "resume", "schedule", "rate", "grant", "timed_pause", "reboot_grant"), 1
    ):
        if mode == "reboot_grant":
            await client.pause_kid(native[".id"], True)
            await traffic(False)
        tables = await client.inventory()
        now = datetime.now(UTC)
        payload = {"member": "test-child", "mode": "grant" if mode == "reboot_grant" else mode}
        if mode == "schedule":
            # Exercise a real edit without making acceptance depend on wall time.
            payload["schedule"] = {kids.DAYS[(now.weekday() + 1) % 7]: "08:45-22:15"}
        elif mode == "rate":
            payload["rate_limit"] = "5M"
        elif mode in {"grant", "timed_pause"}:
            payload["minutes"] = 1
        elif mode == "reboot_grant":
            payload["minutes"] = 30
        plan = {
            **kids.prepare(tables, binding, payload, now, tables["clock"][0]["time-zone-name"]),
            "id": f"K{sequence:06}",
            "backend": "isolated-native-rest",
        }
        journal = []

        async def persist(progress, journal=journal):
            journal.append(deepcopy(progress))

        worker = KidExecutor(client, plan, persist, lambda: True)
        result = await worker.run(now)
        assert result["status"] == "applied", result
        assert await worker.run(now, result) == result
        print("PASS: native HTTPS REST executor/read-back/replay:", mode, flush=True)
        await traffic(mode not in {"pause", "timed_pause"})
        print("PASS: native routed UDP mode enforcement:", mode, flush=True)
        if mode == "reboot_grant":
            await vm.reboot()
        if plan.get("until"):
            for _ in range(20):
                await asyncio.sleep(5)
                try:
                    row = next(r for r in await client.read("kids") if r[".id"] == native[".id"])
                except DomainError as error:
                    if mode == "reboot_grant" and error.code in {
                        "network_timeout",
                        "network_unreachable",
                    }:
                        continue  # The rebooted VM's HTTPS service can start after its console.
                    raise
                if kids.profile(row) == plan["before"]:
                    for spec in kid_timer.specifications(plan):
                        assert not await client.kid_timers(spec["name"])
                    await traffic(plan["before"]["paused"] == "false")
                    print("PASS: native router-only expiry/startup restoration:", mode, flush=True)
                    break
            else:
                raise AssertionError("Native REST temporary-mode expiry failed")
    # All fixture removal is inside the isolated disposable VM.
    await client._request("DELETE", "ip/kid-control/device/" + device[".id"])
    await client._request("DELETE", "ip/kid-control/" + native[".id"])
    assert not await client.read("kids")
    print("PASS: native REST fixture cleanup", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
