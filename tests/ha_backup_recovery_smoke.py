"""Actual Home Assistant Repairs acceptance for failed backup release."""

from __future__ import annotations

from contextlib import asynccontextmanager

from aiohttp import ClientSession
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component


@asynccontextmanager
async def _token(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/backup-recovery-smoke"
    )
    try:
        yield hass.auth.async_create_access_token(refresh)
    finally:
        hass.auth.async_remove_refresh_token(refresh)


async def _repair_request(session, token, path, data):
    async with session.post(
        f"http://127.0.0.1:8123{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=data,
    ) as response:
        assert response.status == 200, await response.text()
        return await response.json()


async def _repair_status(session, token, path, data):
    async with session.post(
        f"http://127.0.0.1:8123{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=data,
    ) as response:
        await response.read()
        return response.status


class _Media:
    def __init__(self, log):
        self.log = log
        self.token = None

    async def async_pause_backup(self):
        assert self.token is None
        self.token = object()
        self.log.append("pause")
        return self.token

    async def async_resume_backup(self, token):
        self.log.append("resume")
        if self.token is token:
            self.token = None


class _Engine:
    def __init__(self, log):
        self.log = log
        self.token = None
        self.fail_release = True

    async def async_begin_backup(self):
        assert self.token is None
        self.token = object()
        self.log.append("begin")
        return self.token

    async def async_end_backup(self, token):
        self.log.append("end")
        assert self.token is token
        if self.fail_release:
            raise RuntimeError("synthetic release failure")
        self.token = None


async def verify_backup_recovery(hass, owner) -> None:
    """Use the real admin Repairs flow without creating a backup archive."""
    from custom_components.family_assistant import backup
    from custom_components.family_assistant.backup_recovery import ISSUE_ID
    from custom_components.family_assistant.const import DOMAIN

    assert owner.is_admin
    assert await async_setup_component(hass, "repairs", {})
    await hass.async_block_till_done()
    users = await hass.auth.async_get_users()
    non_admin = next(
        user for user in users if user.is_active and not user.is_admin and not user.system_generated
    )

    data = hass.data[DOMAIN]
    entries = data["entries"]
    synthetic_key = "zz-backup-recovery-smoke"
    assert synthetic_key not in entries and not data.get("backup")
    log = []
    selected = type(
        "SyntheticRecoveryRuntime",
        (),
        {"media": _Media(log), "engine": _Engine(log)},
    )()
    setup_lock = data["setup_lock"]
    async with setup_lock:
        entries[synthetic_key] = selected

    try:
        await backup.async_pre_backup(hass)
        coordinator = data["backup"]
        try:
            await backup.async_post_backup(hass)
        except HomeAssistantError as error:
            assert str(error) == "backup_unavailable"
        else:
            raise AssertionError("synthetic failed release unexpectedly succeeded")
        assert coordinator.phase == backup.PHASE_RECOVERY
        assert not coordinator.released.is_set()
        assert selected.engine.token is not None
        assert selected.media.token is None
        release_attempts = log.count("end")

        issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)
        assert issue is not None
        assert issue.is_fixable is True and issue.is_persistent is False
        assert issue.data is None and issue.translation_placeholders is None

        async with (
            _token(hass, owner) as token,
            _token(hass, non_admin) as non_admin_token,
            ClientSession() as session,
        ):
            assert (
                await _repair_status(
                    session,
                    non_admin_token,
                    "/api/repairs/issues/fix",
                    {"handler": DOMAIN, "issue_id": ISSUE_ID},
                )
                == 401
            )
            assert log.count("end") == release_attempts
            first = await _repair_request(
                session,
                token,
                "/api/repairs/issues/fix",
                {"handler": DOMAIN, "issue_id": ISSUE_ID},
            )
            second = await _repair_request(
                session,
                token,
                "/api/repairs/issues/fix",
                {"handler": DOMAIN, "issue_id": ISSUE_ID},
            )
            assert first["type"] == second["type"] == "form"
            assert first["step_id"] == second["step_id"] == "confirm"
            assert log.count("end") == release_attempts, "opening a Repair must not retry"
            assert (
                await _repair_status(
                    session,
                    non_admin_token,
                    f"/api/repairs/issues/fix/{first['flow_id']}",
                    {},
                )
                == 401
            )
            assert log.count("end") == release_attempts

            for _attempt in range(2):
                failed = await _repair_request(
                    session,
                    token,
                    f"/api/repairs/issues/fix/{first['flow_id']}",
                    {},
                )
                assert failed["type"] == "form"
                assert failed["step_id"] == "confirm"
                assert failed["errors"] == {"base": "backup_unavailable"}
                assert data["backup"] is coordinator
                assert backup.recovery_identity(hass) == (
                    coordinator,
                    coordinator.generation,
                )
                assert selected.engine.token is not None
                assert selected.media.token is None
                release_attempts += 1
                assert log.count("end") == release_attempts

            selected.engine.fail_release = False
            completed = await _repair_request(
                session,
                token,
                f"/api/repairs/issues/fix/{first['flow_id']}",
                {},
            )
            assert completed["type"] == "create_entry"
            stale = await _repair_request(
                session,
                token,
                f"/api/repairs/issues/fix/{second['flow_id']}",
                {},
            )
            assert stale["type"] == "abort" and stale["reason"] == "stale_recovery"

        assert data.get("backup") is None
        assert coordinator.released.is_set()
        assert selected.engine.token is None and selected.media.token is None
        assert log[-1] == "end"
        assert log.count("resume") == 1
        assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None
    finally:
        selected.engine.fail_release = False
        if data.get("backup") is not None:
            await backup.async_post_backup(hass)
        async with setup_lock:
            entries.pop(synthetic_key, None)

    print(
        "PASS: actual HA admin Repairs retries only the failed backup lease and "
        "rejects a stale generation"
    )
