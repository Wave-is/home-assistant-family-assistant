"""Journal before effects; read back uncertain writes and compensate selected records only."""

import hashlib
import json
from copy import deepcopy

from ..domain.validation import DomainError, timestamp
from .inventory import mac, yes
from .leases import fingerprint, preview, readback_match


def expected(target, *, commented):
    row = {**target["before"], "dynamic": "false"}
    if commented:
        row["comment"] = target["comment"]
    return fingerprint(row)


class LeaseExecutor:
    """Host adapter serializes jobs and persists this progress outside component code.

    No automatic network retry is made after an uncertain operation: reads establish
    whether it happened. If persistence fails, stop immediately; the saved intent
    remains sufficient for explicit recovery without guessing success.
    """

    def __init__(self, client, plan, persist, authorized, *, protected_macs=()):
        self.client, self.plan, self.persist, self.authorized = (
            client,
            deepcopy(plan),
            persist,
            authorized,
        )
        self.protected_macs = tuple(protected_macs)
        self.progress = None
        self.plan_hash = hashlib.sha256(json.dumps(self.plan, sort_keys=True).encode()).hexdigest()

    async def _save(self):
        await self.persist(deepcopy(self.progress))

    def _authorize(self):
        if self.authorized() is not True:
            raise DomainError("forbidden")

    async def run(self, now, progress=None, *, dhcp_recovery=False):
        self._authorize()
        if self.plan["requires_dhcp_recovery_consent"] and dhcp_recovery is not True:
            raise DomainError("network_recovery_consent")
        if progress is not None:
            if (
                not isinstance(progress, dict)
                or progress.get("plan_hash") != self.plan_hash
                or progress.get("status")
                not in {"applying", "rolling_back", "applied", "rolled_back", "review_required"}
                or not isinstance(progress.get("targets"), list)
                or len(progress["targets"]) != len(self.plan["targets"])
                or any(
                    not isinstance(step, dict)
                    or step.get("phase")
                    not in {
                        "ready",
                        "converting",
                        "converted",
                        "commenting",
                        "verified",
                        "unchanged",
                        "removing",
                        "restoring_comment",
                        "restored",
                        "dhcp_recovery",
                    }
                    for step in progress["targets"]
                )
            ):
                raise DomainError("network_conflict")
        if progress and progress.get("status") in {"applied", "rolled_back", "review_required"}:
            return deepcopy(progress)
        if progress is None and now >= timestamp(self.plan["expires_at"], "expires_at"):
            raise DomainError("proposal_expired")
        self.progress = (
            deepcopy(progress)
            if progress
            else {
                "plan_hash": self.plan_hash,
                "status": "applying",
                "targets": [{"phase": "ready"} for _ in self.plan["targets"]],
                "failure": None,
            }
        )
        await self._save()
        if self.progress["status"] == "rolling_back":
            await self._rollback()
            return deepcopy(self.progress)
        try:
            for index, target in enumerate(self.plan["targets"]):
                await self._apply(index, target, now)
            self.progress["status"] = "applied"
            await self._save()
        except DomainError as err:
            self.progress.update(status="rolling_back", failure=err.code)
            await self._save()
            await self._rollback()
        return deepcopy(self.progress)

    async def _apply(self, index, target, now):
        self._authorize()
        step = self.progress["targets"][index]
        rows = await self.client.read("leases")
        row = readback_match(target, rows)
        actual = fingerprint(row)
        # Resuming a saved effect intent may find its already-applied result.
        if step["phase"] != "ready" and actual == expected(target, commented=True):
            step["phase"] = "verified"
            await self._save()
            return
        if not target["changed"] and actual == target["fingerprint"]:
            step["phase"] = "unchanged"
            await self._save()
            return
        after_conversion = step["phase"] in {
            "converting",
            "converted",
            "commenting",
        } and actual == expected(target, commented=False)
        if actual != target["fingerprint"] and not after_conversion:
            raise DomainError("network_conflict")
        # Repeat topology/conflict/protection validation on live data before writing.
        tables = {"leases": rows}
        for name in ("servers", "networks", "addresses", "interfaces"):
            tables[name] = await self.client.read(name)
        preview(
            tables,
            [{"id": row[".id"], "comment": target["comment"], "replace_comment": True}],
            now,
            protected_macs=self.protected_macs,
        )
        self._authorize()
        if yes(row.get("dynamic")):
            step["phase"] = "converting"
            await self._save()
            error = None
            try:
                await self.client.make_static(row[".id"])
            except DomainError as err:
                error = err
            row = readback_match(target, await self.client.read("leases"))
            if fingerprint(row) != expected(target, commented=False):
                raise error or DomainError("network_readback")
            step["phase"] = "converted"
            await self._save()
        self._authorize()
        if row.get("comment", "") != target["comment"]:
            step["phase"] = "commenting"
            await self._save()
            error = None
            try:
                await self.client.set_comment(row[".id"], target["comment"])
            except DomainError as err:
                error = err
            row = readback_match(target, await self.client.read("leases"))
            if fingerprint(row) != expected(target, commented=True):
                raise error or DomainError("network_readback")
        step["phase"] = "verified"
        await self._save()

    async def _rollback(self):
        needs_review = False
        for index in reversed(range(len(self.plan["targets"]))):
            target, step = self.plan["targets"][index], self.progress["targets"][index]
            if step["phase"] in {"ready", "unchanged", "restored", "dhcp_recovery"}:
                continue
            try:
                # Revoked authority stops further device effects, including compensation.
                self._authorize()
                rows = await self.client.read("leases")
                matches = [
                    r
                    for r in rows
                    if mac(r.get("mac-address")) == target["mac"]
                    and r.get("address") == target["address"]
                    and r.get("server") == target["server"]
                ]
                if step["phase"] == "removing" and not matches:
                    step["phase"] = "dhcp_recovery"
                else:
                    row = readback_match(target, rows)
                    actual = fingerprint(row)
                    if actual == target["fingerprint"]:
                        step["phase"] = "restored"
                    elif actual not in {
                        expected(target, commented=False),
                        expected(target, commented=True),
                    }:
                        raise DomainError("network_conflict")
                    elif target["convert"]:
                        step["phase"] = "removing"
                        await self._save()
                        try:
                            await self.client.remove_reservation(row[".id"])
                        except DomainError:
                            pass  # Read-back, not the HTTP response, decides the outcome.
                        remaining = [
                            r
                            for r in await self.client.read("leases")
                            if mac(r.get("mac-address")) == target["mac"]
                            and r.get("address") == target["address"]
                            and r.get("server") == target["server"]
                        ]
                        if any(not yes(r.get("dynamic")) for r in remaining):
                            raise DomainError("network_readback")
                        step["phase"] = "dhcp_recovery"
                    else:
                        step["phase"] = "restoring_comment"
                        await self._save()
                        try:
                            await self.client.set_comment(
                                row[".id"], target["before"].get("comment", "")
                            )
                        except DomainError:
                            pass
                        restored = readback_match(target, await self.client.read("leases"))
                        if fingerprint(restored) != target["fingerprint"]:
                            raise DomainError("network_readback")
                        step["phase"] = "restored"
                await self._save()
            except DomainError as err:
                needs_review = True
                step["error"] = err.code
                await self._save()
        self.progress["status"] = "review_required" if needs_review else "rolled_back"
        await self._save()
