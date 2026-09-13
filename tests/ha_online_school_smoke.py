"""Real HA Options/runtime/Store acceptance; all school transport is synthetic."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from aiohttp import ClientSession
from ha_options_menu import select_option
from voluptuous import UNDEFINED


def _snapshot(student_id, student_name, timezone, now):
    return {
        "student_id": student_id,
        "student_name": student_name,
        "timezone": timezone,
        "source_url": f"https://portal.example.invalid/daybook/{student_id}",
        "coverage_start": now.date().isoformat(),
        "coverage_end": (now + timedelta(days=20)).date().isoformat(),
        "lessons": [
            {
                "id": "lesson-" + student_id,
                "date": (now + timedelta(days=1)).date().isoformat(),
                "start": "09:00",
                "end": "09:45",
                "subject": "Synthetic science " + student_id,
                "room": "",
                "teacher": "Synthetic teacher",
                "topic": "Synthetic topic",
                "homework": "Private synthetic homework " + student_id,
                "estimated_minutes": 20,
                "cancelled": False,
                "replacement": False,
                "links": [],
                "attachments": [],
            }
        ],
        "grades": [],
        "absences": [],
    }


async def _school_form(hass, entry, user):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    return await select_option(hass, flow, "online_school")


async def _view(hass, entry, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/online-school-smoke"
    )
    try:
        async with (
            ClientSession() as session,
            session.ws_connect("http://127.0.0.1:8123/api/websocket") as socket,
        ):
            assert (await socket.receive_json())["type"] == "auth_required"
            await socket.send_json(
                {"type": "auth", "access_token": hass.auth.async_create_access_token(refresh)}
            )
            assert (await socket.receive_json())["type"] == "auth_ok"
            await socket.send_json(
                {"id": 1, "type": "family_assistant/view", "entry_id": entry.entry_id}
            )
            result = await socket.receive_json()
            assert result["success"], result
            return result["result"]
    finally:
        hass.auth.async_remove_refresh_token(refresh)


async def _drain(hass, entry):
    await hass.async_block_till_done()
    worker = entry.runtime_data.online_school
    # HA background tasks are deliberately excluded from the ordinary drain.
    if worker is not None and worker.task is not None:
        await asyncio.wait_for(asyncio.shield(worker.task), timeout=10)
    await hass.async_block_till_done()


async def verify_online_school(hass, user):
    """Exercise native onboarding, private projections and the actual persistent runtime."""
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import Context
    from homeassistant.helpers import event as ha_event
    from homeassistant.helpers.storage import Store
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant.const import DOMAIN, SCHEMA_VERSION
    from custom_components.family_assistant.diagnostics import async_get_config_entry_diagnostics
    from custom_components.family_assistant.domain.online_school import homework_fingerprint
    from custom_components.family_assistant.domain.settings import current_revision
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.online_school import manager, options
    from custom_components.family_assistant.online_school.provider import RespublikaClient

    clock = datetime.now(UTC)
    password = "synthetic-ha-school-password"
    username = "synthetic-school-account"
    url = "https://school.example.invalid"
    students = {"101": "Synthetic pupil Alpha", "202": "Synthetic pupil Beta"}
    clients, fetches, started, stopped = [], [], [], []

    class SyntheticSchool(RespublikaClient):
        """Keep the actual constructor validation; replace only external school I/O."""

        def __init__(self, base_url, selected_username, selected_password):
            super().__init__(base_url, selected_username, selected_password)
            assert (base_url, selected_username, selected_password) == (url, username, password)
            clients.append(self)

        async def discover(self):
            return [{"id": key, "name": name} for key, name in students.items()]

        async def fetch(self, student_id, timezone, now):
            assert student_id in students and timezone == "UTC"
            fetches.append(student_id)
            return _snapshot(student_id, students[student_id], timezone, now)

        async def close(self):
            self._closed = True
            assert self._session is None

    real_start = manager.SchoolManager.start

    # The Options fixture below controls its clock; separately prove the real
    # HA interval dispatcher rather than treating a patched timer as evidence.
    from ha_online_school_interval_smoke import verify_online_school_interval

    await verify_online_school_interval(hass)

    def controlled_start(worker):
        def timer(selected_hass, callback, interval):
            assert selected_hass is hass and callback == worker._interval
            assert interval == timedelta(minutes=1)
            started.append(worker)
            return lambda: stopped.append(worker)

        # Exercise real start/request/stop, but register no autonomous school timer.
        # These synchronous patches cannot affect unrelated HA workers across an await.
        with (
            patch.object(ha_event, "async_track_time_interval", timer),
            patch.object(dt_util, "utcnow", return_value=clock),
        ):
            real_start(worker)

    await async_setup_component(hass, "websocket_api", {})
    entry = None
    with (
        patch.object(options, "RespublikaClient", SyntheticSchool),
        patch.object(manager, "RespublikaClient", SyntheticSchool),
        patch.object(manager.SchoolManager, "start", controlled_start),
    ):
        try:
            flow = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user", "user_id": user.id}
            )
            flow = await hass.config_entries.flow.async_configure(
                flow["flow_id"],
                {
                    "name": "Synthetic school household",
                    "owner_name": "Synthetic guardian",
                    "language": "en",
                    "timezone": "UTC",
                    "template": "manual",
                },
            )
            assert flow["step_id"] == "modules", flow
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"school": True}
            )
            assert result["type"] == "create_entry", result
            entry = result["result"]
            await _drain(hass, entry)
            assert entry.state is ConfigEntryState.LOADED
            assert entry.runtime_data.online_school is None
            await entry.runtime_data.scheduler.stop()

            async def execute(action, payload):
                response = await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    {
                        "entry_id": entry.entry_id,
                        "action": action,
                        "payload": payload,
                        "operation_id": uuid4().hex,
                    },
                    blocking=True,
                    return_response=True,
                    context=Context(user_id=user.id),
                )
                return response["result"]

            children = []
            for student_id, name in students.items():
                child_user = await hass.auth.async_create_user(name)
                child = await execute(
                    "members.save",
                    {
                        "name": "Synthetic child " + student_id,
                        "role": "child",
                        "ha_user_id": child_user.id,
                    },
                )
                children.append((child, child_user, student_id))
            for child, child_user, student_id in children:
                denied = await _school_form(hass, entry, child_user)
                assert denied["type"] == "abort" and denied["reason"] == "forbidden", denied
                form = await _school_form(hass, entry, user)
                form = await hass.config_entries.options.async_configure(
                    form["flow_id"], {"source": "new"}
                )
                assert form["step_id"] == "online_school_account", form
                marker = next(key for key in form["data_schema"].schema if key.schema == "password")
                assert marker.default is UNDEFINED
                before = deepcopy(dict(entry.options))
                form = await hass.config_entries.options.async_configure(
                    form["flow_id"],
                    {
                        "enabled": True,
                        "label": "Synthetic school " + student_id,
                        "url": url,
                        "username": username,
                        "password": password,
                        "member": child["id"],
                    },
                )
                assert form["step_id"] == "online_school_student", form
                assert dict(entry.options) == before  # Discovery is not a saved binding.
                assert all(value not in repr(form) for value in (url, username, password))
                result = await hass.config_entries.options.async_configure(
                    form["flow_id"],
                    {
                        "student_id": student_id,
                        "notifications": False,
                        "notify_changes": False,
                        "homework_time": "18:00",
                        "recipients": [],
                    },
                )
                assert result["type"] == "create_entry", result
                await _drain(hass, entry)
            assert fetches == ["101", "202"] and len(started) == 2
            assert started[0] in stopped and started[0].task is None
            config = deepcopy(dict(entry.options))
            assert config["online_school"]["revision"] == 2
            sources = entry.runtime_data.engine.snapshot()["school"]["online"]["sources"]
            assert {row["member"] for row in sources.values()} == {c[0]["id"] for c in children}
            assert all(row["status"] == "ready" for row in sources.values())
            assert all(
                row["password"] == password for row in config["online_school"]["sources"].values()
            )

            owner_view = await _view(hass, entry, user)
            assert len(owner_view["school"]["online"]["sources"]) == 2
            for child, child_user, student_id in children:
                view = await _view(hass, entry, child_user)
                projected = view["school"]["online"]["sources"]
                assert len(projected) == 1 and projected[0]["member"] == child["id"]
                assert projected[0]["snapshot"]["student_id"] == student_id
                assert not projected[0]["stale"] and "recipients" not in projected[0]["rules"]
                assert all(students[key] not in repr(view) for key in students if key != student_id)
                assert all(value not in repr(view) for value in (url, username, password))
            diagnostics = await async_get_config_entry_diagnostics(hass, entry)
            assert all(
                value not in repr(diagnostics)
                for value in (url, username, password, *students.values())
            )
            assert all(value not in repr(owner_view) for value in (url, username, password))
            assert password not in repr(entry.runtime_data.engine.snapshot())
            persisted = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}").async_load()
            assert persisted["school"]["online"]["sources"] == sources
            assert password not in repr(persisted)

            worker = entry.runtime_data.online_school
            await execute(
                "settings.patch",
                {
                    "revision": current_revision(entry.runtime_data.engine.snapshot()),
                    "changes": {"modules": []},
                },
            )
            await _drain(hass, entry)
            assert entry.runtime_data.online_school is None and worker in stopped
            assert worker.task is None and worker.unsubscribe is None
            assert "school" not in await _view(hass, entry, children[0][1])
            await execute(
                "settings.patch",
                {
                    "revision": current_revision(entry.runtime_data.engine.snapshot()),
                    "changes": {"modules": ["school"]},
                },
            )
            await _drain(hass, entry)
            assert entry.runtime_data.online_school is not worker and len(started) == 3
            assert fetches == ["101", "202"] and dict(entry.options) == config

            previous = entry.runtime_data
            worker = previous.online_school
            assert await hass.config_entries.async_unload(entry.entry_id)
            assert entry.state is ConfigEntryState.NOT_LOADED
            assert worker in stopped and worker.task is None and worker.unsubscribe is None
            assert await hass.config_entries.async_setup(entry.entry_id)
            await _drain(hass, entry)
            assert entry.state is ConfigEntryState.LOADED and entry.runtime_data is not previous
            assert dict(entry.options) == config and fetches == ["101", "202"]
            assert entry.runtime_data.engine.snapshot()["school"]["online"]["sources"] == sources
            assert (
                len((await _view(hass, entry, children[1][1]))["school"]["online"]["sources"]) == 1
            )
            assert len(started) == 4 and all(client._closed for client in clients)

            # Native editing uses an already-reviewed binding while the portal is
            # unavailable; only explicit identity/student refresh may rediscover.
            source_id = next(key for key, row in sources.items() if row["student_id"] == "101")
            cached = sources[source_id]
            lesson = cached["snapshot"]["lessons"][0]
            await execute(
                "school.online_homework_ack",
                {
                    "id": source_id,
                    "revision": cached["revision"],
                    "member_revision": cached["member_revision"],
                    "lesson_id": lesson["id"],
                    "homework_hash": homework_fingerprint(lesson),
                    "ack_revision": None,
                    "done": True,
                },
            )
            cached = entry.runtime_data.engine.snapshot()["school"]["online"]["sources"][source_id]
            client_count = len(clients)

            async def unavailable_discovery(self):
                raise DomainError("online_school_timeout")

            with patch.object(SyntheticSchool, "discover", unavailable_discovery):
                for changed in (True, False):
                    form = await _school_form(hass, entry, user)
                    form = await hass.config_entries.options.async_configure(
                        form["flow_id"], {"source": source_id}
                    )
                    account_defaults = form["data_schema"]({})
                    assert account_defaults["refresh_students"] is False
                    form = await hass.config_entries.options.async_configure(
                        form["flow_id"], account_defaults
                    )
                    assert form["step_id"] == "online_school_student", form
                    defaults = form["data_schema"]({})
                    assert defaults["student_id"] == "101"
                    if changed:
                        defaults.update(
                            notifications=True,
                            notify_changes=True,
                            homework_time="17:25",
                            recipients=["owner"],
                        )
                    else:
                        assert defaults == {
                            "student_id": "101",
                            "notifications": True,
                            "notify_changes": True,
                            "homework_time": "17:25",
                            "recipients": ["owner"],
                        }
                        before_noop = deepcopy(dict(entry.options))
                    result = await hass.config_entries.options.async_configure(
                        form["flow_id"], defaults
                    )
                    assert result["type"] == "create_entry", result
                    await _drain(hass, entry)
                    edited = entry.runtime_data.engine.snapshot()["school"]["online"]["sources"][
                        source_id
                    ]
                    assert edited["generation"] == cached["generation"]
                    assert edited["revision"] == cached["revision"] + 1
                    assert edited["snapshot"] == cached["snapshot"]
                    assert edited["acknowledgements"] == cached["acknowledgements"]
                    assert len(clients) == client_count and fetches == ["101", "202"]
                    if not changed:
                        assert dict(entry.options) == before_noop

                form = await _school_form(hass, entry, user)
                form = await hass.config_entries.options.async_configure(
                    form["flow_id"], {"source": source_id}
                )
                result = await hass.config_entries.options.async_configure(
                    form["flow_id"], {"enabled": False}
                )
                assert result["type"] == "create_entry", result
                await _drain(hass, entry)
                disabled = entry.runtime_data.engine.snapshot()["school"]["online"]["sources"][
                    source_id
                ]
                assert disabled["enabled"] is False
                assert disabled["generation"] == cached["generation"]
                assert disabled["snapshot"] == cached["snapshot"]
                assert disabled["acknowledgements"] == cached["acknowledgements"]
                assert len(clients) == client_count

            persisted = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}").async_load()
            assert persisted["school"]["online"]["sources"][source_id] == disabled
            previous = entry.runtime_data
            assert await hass.config_entries.async_unload(entry.entry_id)
            assert await hass.config_entries.async_setup(entry.entry_id)
            await _drain(hass, entry)
            assert entry.runtime_data is not previous
            assert (
                entry.runtime_data.engine.snapshot()["school"]["online"]["sources"][source_id]
                == disabled
            )
            assert fetches == ["101", "202"]
        finally:
            # Unload while patches are active: no fixture can escape to a real school poller.
            if entry is not None and entry.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(entry.entry_id)
    print(
        "PASS: actual HA school Options/edit defaults/offline policy and disable, "
        "private child views, polling, module lifecycle and Store"
    )
