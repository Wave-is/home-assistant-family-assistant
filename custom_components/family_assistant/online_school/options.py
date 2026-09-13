"""Explicit owner-reviewed school accounts; credentials stay in ConfigEntry Options."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import voluptuous as vol
from homeassistant.helpers import selector

from ..domain.validation import DomainError
from .provider import RespublikaClient


def _scope(flow):
    runtime, actor = flow._authorized_runtime()
    state = runtime.engine.snapshot()
    if "school" not in state["settings"]["modules"]:
        raise DomainError("module_disabled")
    members = {
        key: (value["revision"], value["name"])
        for key, value in state["members"].items()
        if value.get("active") and value.get("role") == "child"
    }
    return (
        runtime,
        actor,
        state["members"][actor]["revision"],
        members,
        deepcopy(dict(flow.config_entry.options)),
    )


def _same(current, expected):
    return expected is not None and current[0] is expected[0] and current[1:] == expected[1:]


def _select(values):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in values.items()]
        )
    )


async def select_step(flow, user_input=None):
    try:
        scope = _scope(flow)
        sources = scope[4].get("online_school", {}).get("sources", {})
        choices = {key: value.get("label", key) for key, value in sources.items()}
        choices["new"] = "+"
        if user_input is not None:
            if not _same(scope, getattr(flow, "_school_scope", None)):
                raise DomainError("conflict")
            selected = user_input.get("source")
            if selected not in choices:
                raise DomainError("invalid_field")
            if selected == "new" and len(sources) >= 8:
                raise DomainError("invalid_field")
            flow._school_source = "OS" + uuid4().hex if selected == "new" else selected
            return await account_step(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    flow._school_scope = scope
    return flow.async_show_form(
        step_id="online_school",
        data_schema=vol.Schema(
            {
                vol.Required("source"): _select(choices),
            }
        ),
    )


async def account_step(flow, user_input=None):
    try:
        scope = _scope(flow)
        if not _same(scope, getattr(flow, "_school_scope", None)):
            raise DomainError("conflict")
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    current = scope[4].get("online_school", {}).get("sources", {}).get(flow._school_source, {})
    errors = {}
    if user_input is not None:
        client = None
        try:
            if type(user_input.get("enabled")) is not bool:
                raise DomainError("invalid_field")
            if not user_input["enabled"] and current:
                updated = {**current, "enabled": False, "generation": uuid4().hex}
                return _finish(flow, scope, updated)
            if not user_input["enabled"]:
                raise DomainError("invalid_field")
            member = user_input.get("member")
            if member not in scope[3]:
                raise DomainError("unknown_member")
            url = user_input.get("url", "").strip().rstrip("/")
            username = user_input.get("username", "").strip()
            password = user_input.get("password", "")
            if (url != current.get("url") or username != current.get("username")) and not password:
                raise DomainError("provider_key_scope")
            password = password or current.get("password", "")
            label = user_input.get("label", "").strip()
            if not label or len(label) > 200:
                raise DomainError("invalid_field")
            client = RespublikaClient(url, username, password)
            students = await client.discover()
            if not students:
                raise DomainError("online_school_student_mismatch")
            flow._school_pending = {
                "id": flow._school_source,
                "provider": "respublika",
                "enabled": True,
                "url": url,
                "username": username,
                "password": password,
                "label": label,
                "member": member,
                "member_revision": scope[3][member][0],
                "timezone": scope[0].engine.snapshot()["settings"].get("timezone", "UTC"),
                "generation": uuid4().hex,
            }
            flow._school_students = {str(row["id"]): row["name"] for row in students}
        except DomainError as error:
            errors["base"] = error.code
        finally:
            if client is not None:
                await client.close()
        try:
            if not _same(_scope(flow), scope):
                raise DomainError("conflict")
        except DomainError as error:
            flow._school_pending = None
            return flow.async_abort(reason=error.code)
        if not errors:
            return await student_step(flow)
    return flow.async_show_form(
        step_id="online_school_account",
        errors=errors,
        data_schema=vol.Schema(
            {
                vol.Required("enabled", default=current.get("enabled", True)): bool,
                vol.Required("label", default=current.get("label", "School")): str,
                vol.Required(
                    "url", default=current.get("url", "https://example.respublika.school")
                ): str,
                vol.Required("username", default=current.get("username", "")): str,
                vol.Optional("password"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    "member",
                    **({"default": current["member"]} if current.get("member") in scope[3] else {}),
                ): _select({key: row[1] for key, row in scope[3].items()}),
            }
        ),
    )


def _finish(flow, scope, config):
    if not _same(_scope(flow), scope):
        raise DomainError("conflict")
    options = deepcopy(scope[4])
    options.setdefault("online_school", {}).setdefault("sources", {})[flow._school_source] = config
    options["online_school"]["revision"] = options["online_school"].get("revision", 0) + 1
    # Validate the exact domain binding/rule caps before Options can report a
    # successful save. This preview writes neither Store nor external services.
    from ..domain.context import Context
    from ..domain.online_school import sync_bindings

    checked = sync_bindings(
        Context(
            scope[0].engine.snapshot(),
            {"id": "system", "role": "system"},
            datetime.now(UTC),
            "school-options-preview",
        ),
        options,
    )
    if not checked["applied"]:
        raise DomainError("conflict")
    flow._school_pending = None
    return flow.async_create_entry(title="", data=options)


async def student_step(flow, user_input=None):
    try:
        scope = _scope(flow)
        if not _same(scope, flow._school_scope) or not getattr(flow, "_school_pending", None):
            raise DomainError("conflict")
        pending = flow._school_pending
        state = scope[0].engine.snapshot()
        recipients = {
            key: row["name"]
            for key, row in state["members"].items()
            if row.get("active")
            and (row.get("role") in {"owner", "parent"} or key == pending["member"])
        }
        if user_input is not None:
            from ..domain.recurrence import clock

            student = user_input.get("student_id")
            selected = user_input.get("recipients", [])
            if (
                student not in flow._school_students
                or not isinstance(selected, list)
                or any(key not in recipients for key in selected)
            ):
                raise DomainError("invalid_field")
            enabled = user_input.get("notifications", False)
            changes = user_input.get("notify_changes", False)
            if type(enabled) is not bool or type(changes) is not bool or enabled and not selected:
                raise DomainError("invalid_field")
            config = {
                **pending,
                "student_id": student,
                "rules": {
                    "enabled": enabled,
                    "notify_changes": changes,
                    "homework_time": clock(user_input.get("homework_time", "18:00")),
                    "recipients": list(dict.fromkeys(selected)),
                },
            }
            return _finish(flow, scope, config)
    except DomainError as error:
        flow._school_pending = None
        return flow.async_abort(reason=error.code)
    return flow.async_show_form(
        step_id="online_school_student",
        description_placeholders={"member": scope[3][pending["member"]][1]},
        data_schema=vol.Schema(
            {
                vol.Required("student_id"): _select(flow._school_students),
                vol.Required("notifications", default=False): bool,
                vol.Required("notify_changes", default=False): bool,
                vol.Required("homework_time", default="18:00"): str,
                vol.Optional("recipients", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        multiple=True,
                        options=[
                            {"value": key, "label": label} for key, label in recipients.items()
                        ],
                    )
                ),
            }
        ),
    )
