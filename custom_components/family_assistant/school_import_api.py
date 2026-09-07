"""Explicit, read-only calendar week proposals with current HA/family authority."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.calendar import DATA_COMPONENT, CalendarEntity, CalendarEvent
from homeassistant.util import dt as dt_util

from .command_scope import capture
from .const import DOMAIN
from .domain.validation import DomainError

_BUSY = "school_calendar_inflight"
_ENTITY = re.compile(r"calendar\.[a-z0-9_]{1,120}")


def _week(value, timezone):
    try:
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError
        start = date.fromisoformat(value)
        zone = ZoneInfo(timezone)
        today = dt_util.utcnow().astimezone(zone).date()
        if start.weekday() != 0 or abs((start - today).days) > 366:
            raise ValueError
        return datetime.combine(start, time.min, zone), datetime.combine(
            start + timedelta(days=7), time.min, zone
        )
    except (TypeError, ValueError, OverflowError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "week_start") from None


def _source(hass, user, entity_id):
    if not isinstance(entity_id, str) or _ENTITY.fullmatch(entity_id) is None:
        raise DomainError("invalid_field", "entity_id")
    try:
        readable = (
            user is not None
            and user.is_active is True
            and user.permissions.check_entity(entity_id, POLICY_READ) is True
        )
    except (AttributeError, TypeError, ValueError):
        readable = False
    if not readable:
        raise DomainError("forbidden")
    component = hass.data.get(DATA_COMPONENT)
    entity = component.get_entity(entity_id) if component is not None else None
    if not isinstance(entity, CalendarEntity) or entity.available is not True:
        raise DomainError("not_ready")
    return entity


def _settings(scope):
    settings = scope.engine.snapshot()["settings"]
    if scope.role not in {"owner", "parent"}:
        raise DomainError("forbidden")
    if "school" not in settings.get("modules", []):
        raise DomainError("module_disabled")
    return settings["timezone"], settings.get("revision")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/school_calendar_preview",
        vol.Required("entry_id"): str,
        vol.Required("entity_id"): str,
        vol.Required("week_start"): str,
    }
)
@websocket_api.async_response
async def preview(hass, connection, msg):
    scope = None
    busy = None
    token = object()
    try:
        scope = await capture(hass, msg["entry_id"], connection.user.id, connection.user)
        await scope.check()
        settings = _settings(scope)
        start, end = _week(msg["week_start"], settings[0])
        current_user = await hass.auth.async_get_user(connection.user.id)
        await scope.check()
        entity = _source(hass, current_user, msg["entity_id"])
        busy = hass.data[DOMAIN].setdefault(_BUSY, {})
        if msg["entry_id"] in busy or len(busy) >= 4:
            raise DomainError("not_ready")
        busy[msg["entry_id"]] = token
        async with asyncio.timeout(15) as deadline:
            # Documented CalendarEntity contract; no calendar mutation service.
            events = await entity.async_get_events(
                hass, dt_util.as_local(start), dt_util.as_local(end)
            )
        if deadline.expired():
            raise DomainError("provider_timeout")
        await scope.check()
        current_user = await hass.auth.async_get_user(connection.user.id)
        await scope.check()
        if (
            _settings(scope) != settings
            or _source(hass, current_user, msg["entity_id"]) is not entity
        ):
            raise DomainError("conflict")
        if not isinstance(events, list) or not 1 <= len(events) <= 100:
            raise DomainError("invalid_field", "events")
        normalized = []
        for event in events:
            if (
                not isinstance(event, CalendarEvent)
                or not isinstance(event.start, datetime)
                or not isinstance(event.end, datetime)
            ):
                raise DomainError("invalid_field", "events")
            normalized.append(
                {
                    "start": event.start.isoformat(),
                    "end": event.end.isoformat(),
                    "summary": event.summary,
                    "location": "" if event.location is None else event.location,
                }
            )
        from .domain.school_import import calendar_week

        result = calendar_week(normalized, week_start=msg["week_start"], timezone=settings[0])
        # Parsed text is untrusted content, not a command or an LLM instruction.
        connection.send_result(msg["id"], {**result, "timezone": settings[0], "saved": False})
    except Exception as error:
        code = error.code if isinstance(error, DomainError) else "provider_unavailable"
        if isinstance(error, TimeoutError):
            code = "provider_timeout"
        if scope is not None:
            try:
                await scope.check()
                _settings(scope)
                user = await hass.auth.async_get_user(connection.user.id)
                await scope.check()
                _source(hass, user, msg["entity_id"])
            except DomainError as revoked:
                code = revoked.code
            except Exception:
                code = "not_ready"
        connection.send_error(msg["id"], code, code)
    finally:
        if busy is not None and busy.get(msg["entry_id"]) is token:
            busy.pop(msg["entry_id"])
