"""Native owner-reviewed source/group editor; no state reads or device effects."""

import inspect
import uuid
from copy import deepcopy

import voluptuous as vol
from homeassistant.helpers import selector

from ..domain.validation import DomainError
from . import config
from .copy import COPY
from .observations import ha_access, readable


class StrictAge(vol.All):
    def __init__(self):
        super().__init__(int, vol.Range(min=30, max=86400))

    def __call__(self, value):
        if type(value) is not int or not 30 <= value <= 86400:
            raise vol.Invalid("invalid_field")
        return value


def choices(values, *, multiple=False):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=values, multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


async def scope(flow):
    runtime, actor_id = flow._authorized_runtime()
    before = runtime.engine.snapshot()["members"][actor_id]
    options = deepcopy(dict(flow.config_entry.options))
    user = flow.hass.auth.async_get_user(before.get("ha_user_id"))
    if inspect.isawaitable(user):
        user = await user
    current_runtime, current_actor = flow._authorized_runtime()
    if (
        current_runtime is not runtime
        or current_actor != actor_id
        or flow.hass.config_entries.async_get_entry(flow.config_entry.entry_id)
        is not flow.config_entry
        or getattr(flow.config_entry, "runtime_data", None) is not runtime
        or runtime.engine.snapshot()["members"].get(actor_id) != before
        or dict(flow.config_entry.options) != options
    ):
        raise DomainError("conflict")
    if (
        before.get("active") is not True
        or before.get("role") != "owner"
        or getattr(user, "is_active", None) is not True
        or getattr(user, "id", None) != before.get("ha_user_id")
    ):
        raise DomainError("forbidden")
    return {
        "runtime": runtime,
        "actor": actor_id,
        "member": before,
        "user": user,
        "options": options,
        "config": config.from_options(options),
    }


def same(left, right):
    return (
        left["runtime"] is right["runtime"]
        and left["actor"] == right["actor"]
        and left["member"] == right["member"]
        and left["options"] == right["options"]
    )


def freeze(flow, current, proposed, summary, changed_source=None):
    proposed = config.validate(proposed)
    changed = proposed != current["config"]
    if changed:
        proposed["revision"] += 1
        proposed = config.validate(proposed)
    flow._home_status_review = {
        "scope": current,
        "config": proposed,
        "summary": summary,
        "source": changed_source,
        "changed": changed,
    }


async def menu(flow, user_input=None):
    try:
        await scope(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    return flow.async_show_menu(
        step_id="home_status",
        menu_options=["home_status_settings", "home_status_group", "home_status_source", "init"],
    )


async def settings(flow, user_input=None):
    try:
        current = await scope(flow)
        if user_input is None:
            flow._home_status_settings_scope = current
        elif not isinstance(getattr(flow, "_home_status_settings_scope", None), dict) or not same(
            current, flow._home_status_settings_scope
        ):
            raise DomainError("conflict")
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        try:
            if not isinstance(user_input, dict) or set(user_input) != {"max_age_seconds"}:
                config.fail()
            proposed = deepcopy(current["config"])
            proposed["max_age_seconds"] = user_input["max_age_seconds"]
            freeze(flow, current, proposed, str(user_input["max_age_seconds"]))
            return await review(flow)
        except DomainError as error:
            errors["base"] = error.code
    return flow.async_show_form(
        step_id="home_status_settings",
        data_schema=vol.Schema(
            {
                vol.Required(
                    "max_age_seconds", default=current["config"]["max_age_seconds"]
                ): StrictAge()
            }
        ),
        errors=errors,
    )


async def pick(flow, kind, user_input=None):
    try:
        current = await scope(flow)
        records = current["config"]["groups" if kind == "group" else "sources"]
        if user_input is not None:
            if not isinstance(user_input, dict) or set(user_input) != {"record"}:
                config.fail()
            key = user_input["record"]
            if key != "new" and not any(item["id"] == key for item in records):
                config.fail()
            flow._home_status_edit = {"scope": current, "kind": kind, "key": key}
            return await edit(flow, kind)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    values = [
        {"value": "new", "label": "+"},
        *[{"value": item["id"], "label": item.get("title", item.get("label"))} for item in records],
    ]
    return flow.async_show_form(
        step_id=f"home_status_{kind}",
        data_schema=vol.Schema({vol.Required("record", default="new"): choices(values)}),
    )


async def edit(flow, kind, user_input=None):
    try:
        current = await scope(flow)
        draft = getattr(flow, "_home_status_edit", None)
        if (
            not isinstance(draft, dict)
            or draft["kind"] != kind
            or not same(current, draft["scope"])
        ):
            raise DomainError("conflict")
    except DomainError as error:
        flow._home_status_edit = None
        return flow.async_abort(reason=error.code)
    key = draft["key"]
    bucket = "groups" if kind == "group" else "sources"
    original = next((item for item in current["config"][bucket] if item["id"] == key), None)
    defaults = original or {}
    errors = {}
    if user_input is not None:
        try:
            fields = (
                {"key", "title", "roles", "remove"}
                if kind == "group"
                else {"label", "entity_id", "mode", "roles", "active_states", "remove"}
            )
            if (
                not isinstance(user_input, dict)
                or set(user_input) != fields
                or type(user_input["remove"]) is not bool
            ):
                config.fail()
            proposed = deepcopy(current["config"])
            position = next(
                (index for index, item in enumerate(proposed[bucket]) if item["id"] == key),
                len(proposed[bucket]),
            )
            proposed[bucket] = [item for item in proposed[bucket] if item["id"] != key]
            changed_source = None
            if user_input["remove"]:
                if original is None:
                    config.fail()
                if kind == "group" and any(item["group_id"] == key for item in proposed["sources"]):
                    raise DomainError("home_status_group_in_use")
                summary = original.get("title", original.get("label"))
            elif kind == "group":
                group_key = config.identifier(user_input["key"])
                if original is not None and group_key != original["id"]:
                    raise DomainError("conflict")
                record = {
                    "id": group_key,
                    "title": user_input["title"],
                    "roles": user_input["roles"],
                }
                proposed[bucket].insert(position, record)
                summary = f"{record['title']} · {record['id']}"
            else:
                entity = user_input["entity_id"]
                mode = user_input["mode"]
                if not isinstance(entity, str) or not isinstance(mode, str):
                    config.fail()
                registry, policy = ha_access(flow.hass)
                registered = registry.async_get(entity)
                if registered is None or registered.entity_id != entity:
                    raise DomainError("forbidden")
                section, _, value = mode.partition(":")
                if mode not in {
                    "active",
                    *("energy:" + metric for metric in config.METRICS),
                    *("group:" + item["id"] for item in current["config"]["groups"]),
                }:
                    config.fail()
                record = {
                    "id": original["id"] if original else "s_" + uuid.uuid4().hex[:16],
                    "label": user_input["label"],
                    "entity_id": entity,
                    "registry_id": registered.id,
                    "section": section,
                    "group_id": value if section == "group" else None,
                    "metric": value if section == "energy" else None,
                    "roles": user_input["roles"],
                    "active_states": user_input["active_states"],
                }
                if not readable(registry, current["user"], policy, record):
                    raise DomainError("forbidden")
                proposed[bucket].insert(position, record)
                changed_source = record
                summary = f"{record['label']} · {entity} · {mode}"
            freeze(flow, current, proposed, summary, changed_source)
            return await review(flow)
        except DomainError as error:
            errors["base"] = error.code
    language = current["member"].get("language", "en")
    t = COPY.get(language, COPY["en"])
    fields = (
        {
            vol.Required("key", default=defaults.get("id", "")): str,
            vol.Required("title", default=defaults.get("title", "")): str,
        }
        if kind == "group"
        else {
            vol.Required("label", default=defaults.get("label", "")): str,
            vol.Required(
                "entity_id",
                **({"default": defaults["entity_id"]} if defaults.get("entity_id") else {}),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=list(config.DOMAINS))),
            vol.Required(
                "mode",
                default=(
                    "group:" + defaults["group_id"]
                    if defaults.get("group_id")
                    else "energy:" + defaults["metric"]
                    if defaults.get("metric")
                    else "active"
                ),
            ): choices(
                [{"value": "energy:" + metric, "label": t[metric]} for metric in config.METRICS]
                + [{"value": "active", "label": t["active"]}]
                + [
                    {"value": "group:" + item["id"], "label": item["title"]}
                    for item in current["config"]["groups"]
                ]
            ),
            vol.Required("active_states", default=defaults.get("active_states", [])): choices(
                [
                    {"value": state, "label": f"{t['state_' + state]} ({state})"}
                    for state in sorted(
                        {state for states in config.STATES.values() for state in states}
                    )
                ],
                multiple=True,
            ),
        }
    )
    fields.update(
        {
            vol.Required("roles", default=defaults.get("roles", ["owner", "parent"])): choices(
                [{"value": role, "label": t["role_" + role]} for role in config.ROLES],
                multiple=True,
            ),
            vol.Required("remove", default=False): bool,
        }
    )
    return flow.async_show_form(
        step_id=f"home_status_{kind}_edit", data_schema=vol.Schema(fields), errors=errors
    )


async def review(flow, user_input=None):
    frozen = getattr(flow, "_home_status_review", None)
    if not isinstance(frozen, dict):
        return await menu(flow)
    try:
        current = await scope(flow)
        if not same(current, frozen["scope"]):
            raise DomainError("conflict")
        if frozen["source"] is not None:
            registry, policy = ha_access(flow.hass)
            if not readable(registry, current["user"], policy, frozen["source"]):
                raise DomainError("forbidden")
        if user_input is not None:
            if (
                not isinstance(user_input, dict)
                or set(user_input) != {"confirmed"}
                or type(user_input["confirmed"]) is not bool
            ):
                config.fail()
            if user_input["confirmed"]:
                options = deepcopy(current["options"])
                if frozen["changed"]:
                    options[config.MODULE] = deepcopy(frozen["config"])
                # No await between current identity/options/ACL checks and handing the
                # complete reviewed options to Home Assistant's supported flow commit.
                result = flow.async_create_entry(title="", data=options)
                flow._home_status_review = None
                flow._home_status_edit = None
                return result
            flow._home_status_review = None
            flow._home_status_edit = None
            return await menu(flow)
    except DomainError as error:
        flow._home_status_review = None
        flow._home_status_edit = None
        return flow.async_abort(reason=error.code)
    return flow.async_show_form(
        step_id="home_status_review",
        data_schema=vol.Schema({vol.Required("confirmed", default=False): bool}),
        description_placeholders={
            "summary": frozen["summary"],
            "revision": str(frozen["config"]["revision"]),
        },
    )
