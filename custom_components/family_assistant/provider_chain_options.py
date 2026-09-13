"""Owner-scoped, server-side drafts for optional ordered provider lists."""

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol

from .domain.validation import DomainError, fields
from .provider_options import _same, _scope, guarded_provider_step

_ROOT = {"text": "provider_chain", "image": "image_generation"}
_PREFIX = {"text": "provider_chain", "image": "image_provider"}
_KINDS = {"text": ["agy", "ollama", "ha_agent"], "image": ["agy_gateway", "comfyui"]}


class _Numeric(vol.Coerce):
    """HA-serializable numeric coercion without accepting boolean settings."""

    def __call__(self, value):
        if isinstance(value, bool):
            raise vol.Invalid("number")
        return super().__call__(value)


def _select(options, key=None, *, custom=False):
    from homeassistant.helpers import selector

    config = {"options": options}
    if key:
        config["translation_key"] = key
    if custom:
        config["custom_value"] = True
    return selector.SelectSelector(selector.SelectSelectorConfig(**config))


def _input(value, allowed, required=()):
    if not isinstance(value, dict):
        raise DomainError("invalid_field")
    fields(value, set(allowed), set(required))


def _normalize(kind, rows):
    if kind == "text":
        from .assistant.provider_registry import normalize_providers

        return normalize_providers(rows)
    from .assistant.image_providers import normalize_config

    return normalize_config({"enabled": False, "providers": rows})["providers"]


async def _draft(flow, kind):
    current = await _scope(flow)
    saved = getattr(flow, "_provider_list_draft", None)
    if saved is not None:
        if saved["kind"] != kind or not _same(current, saved["scope"]):
            raise DomainError("conflict")
        return saved
    if kind == "text":
        from .assistant.provider_registry import provider_rows

        config = deepcopy(dict(flow.config_entry.options.get("conversation", {})))
        rows = provider_rows(config)
    else:
        from .assistant.image_providers import normalize_config

        config = normalize_config(dict(flow.config_entry.options.get("image_generation", {})))
        rows = config["providers"]
    saved = {
        "kind": kind,
        "scope": current,
        "config": config,
        "rows": deepcopy(rows),
        "selected": None,
        "editing": None,
        "models": {},
    }
    flow._provider_list_draft = saved
    return saved


def _row(draft):
    row = next((row for row in draft["rows"] if row["id"] == draft["selected"]), None)
    if row is None:
        raise DomainError("conflict")
    return row


async def _route(flow, kind, suffix=""):
    step = _ROOT[kind] if not suffix else _PREFIX[kind] + "_" + suffix
    return await getattr(flow, "async_step_" + step)()


async def _manager(flow, kind, user_input):
    draft = await _draft(flow, kind)
    errors = {}
    if user_input is not None:
        try:
            _input(user_input, {"enabled", "provider", "action"}, {"enabled", "action"})
            if type(user_input["enabled"]) is not bool:
                raise DomainError("invalid_field", "enabled")
            draft["config"]["enabled"] = user_input["enabled"]
            action = user_input["action"]
            if action == "cancel":
                flow._provider_list_draft = None
                return flow.async_abort(reason="provider_chain_cancelled")
            if action == "save":
                config = {**draft["config"], "providers": _normalize(kind, draft["rows"])}
                if kind == "image":
                    from .assistant.image_providers import normalize_config

                    config = normalize_config(config)
                options = deepcopy(dict(flow.config_entry.options))
                options["conversation" if kind == "text" else "image_generation"] = config
                return flow.async_create_entry(title="", data=options)
            if action == "settings" and kind == "image":
                return await flow.async_step_image_generation_settings()
            if action == "add":
                if len(draft["rows"]) >= 8:
                    raise DomainError("invalid_field", "providers")
                draft["editing"] = None
                return await _route(flow, kind, "kind")
            draft["selected"] = user_input.get("provider")
            selected = _row(draft)
            if action == "edit":
                draft["editing"] = deepcopy(selected)
                draft["edit_values"] = deepcopy(selected)
                return await _route(flow, kind, "edit")
            if action in {"remove", "test"}:
                return await _route(flow, kind, action)
            if action in {"move_up", "move_down"}:
                index = draft["rows"].index(selected)
                other = index + (-1 if action == "move_up" else 1)
                if not 0 <= other < len(draft["rows"]):
                    raise DomainError("invalid_field", "provider")
                draft["rows"][index], draft["rows"][other] = draft["rows"][other], selected
            else:
                raise DomainError("invalid_field", "action")
        except DomainError as error:
            errors["base"] = error.code
    options = [{"value": "_none", "label": "—"}]
    options.extend(
        {
            "value": row["id"],
            "label": f"{index + 1}. {'●' if row['enabled'] else '○'} {row['name']}",
        }
        for index, row in enumerate(draft["rows"])
    )
    actions = ["save", "cancel"]
    if len(draft["rows"]) < 8:
        actions.insert(0, "add")
    if draft["rows"]:
        actions[0:0] = ["edit", "test", "move_up", "move_down", "remove"]
    if kind == "image":
        actions.insert(0, "settings")
    return flow.async_show_form(
        step_id=_ROOT[kind],
        data_schema=vol.Schema(
            {
                vol.Required("enabled", default=draft["config"].get("enabled", False)): bool,
                vol.Optional("provider", default=draft["selected"] or "_none"): _select(options),
                vol.Required("action", default="save"): _select(actions, "provider_chain_action"),
            }
        ),
        errors=errors,
        description_placeholders={
            "count": str(len(draft["rows"])),
            "enabled_count": str(sum(row["enabled"] for row in draft["rows"])),
            "order": "\n".join(f"{i + 1}. {row['name']}" for i, row in enumerate(draft["rows"]))
            or "—",
        },
    )


async def _kind(flow, kind, user_input):
    draft = await _draft(flow, kind)
    errors = {}
    if user_input is not None:
        try:
            _input(user_input, {"kind", "action"}, {"action"})
            if user_input["action"] == "back":
                return await _route(flow, kind)
            if user_input["action"] != "continue" or user_input.get("kind") not in _KINDS[kind]:
                raise DomainError("invalid_field")
            if len(draft["rows"]) >= 8:
                raise DomainError("invalid_field")
            draft["editing"] = {
                "id": "provider-" + uuid4().hex[:24],
                "kind" if kind == "text" else "type": user_input["kind"],
                "name": "",
                "enabled": False,
            }
            draft["edit_values"] = deepcopy(draft["editing"])
            return await _route(flow, kind, "edit")
        except DomainError as error:
            errors["base"] = error.code
    return flow.async_show_form(
        step_id=_PREFIX[kind] + "_kind",
        errors=errors,
        data_schema=vol.Schema(
            {
                vol.Required("kind", default=_KINDS[kind][0]): _select(
                    _KINDS[kind], "provider_kind"
                ),
                vol.Required("action", default="continue"): _select(
                    ["continue", "back"], "provider_chain_action"
                ),
            }
        ),
    )


async def _edit(flow, kind, user_input):
    from homeassistant.helpers import selector

    draft = await _draft(flow, kind)
    old = draft["editing"]
    if old is None:
        raise DomainError("conflict")
    provider_kind = old.get("kind", old.get("type"))
    allowed = {"name", "enabled", "action"}
    if provider_kind != "ha_agent":
        allowed |= {"url", "model", "api_key", "clear_key", "allow_http", "timeout"}
    if provider_kind == "agy":
        allowed.add("search_enabled")
    if provider_kind == "comfyui":
        allowed |= {"workflow", "encoder", "vae"}
    errors = {}
    if user_input is not None:
        try:
            _input(user_input, allowed, {"action"})
            if user_input["action"] == "back":
                draft["editing"] = None
                return await _route(flow, kind)
            if user_input["action"] != "save":
                raise DomainError("invalid_field")
            values = {
                key: value
                for key, value in user_input.items()
                if key not in {"api_key", "clear_key", "action"}
            }
            draft["edit_values"] = {**old, **values}
            row = {**old, **values}
            if provider_kind != "ha_agent":
                if type(user_input.get("clear_key", False)) is not bool:
                    raise DomainError("invalid_field")
                if (
                    row.get("url", "") != old.get("url", "")
                    and old.get("api_key")
                    and not (user_input.get("api_key") or user_input.get("clear_key"))
                ):
                    raise DomainError("provider_key_scope")
                if user_input.get("clear_key"):
                    row.pop("api_key", None)
                elif user_input.get("api_key"):
                    row["api_key"] = user_input["api_key"]
            rows = [row if saved["id"] == row["id"] else saved for saved in draft["rows"]]
            if not any(saved["id"] == row["id"] for saved in draft["rows"]):
                rows.append(row)
            draft["rows"] = _normalize(kind, rows)
            draft["selected"] = row["id"]
            draft["editing"] = None
            return await _route(flow, kind)
        except DomainError as error:
            errors["base"] = error.code
    values = draft["edit_values"]
    schema = {
        vol.Required("name", default=values.get("name", "")): str,
        vol.Required("enabled", default=values.get("enabled", False)): bool,
    }
    if provider_kind != "ha_agent":
        schema.update(
            {
                vol.Optional("url", default=values.get("url", "")): str,
                vol.Optional("model", default=values.get("model", "")): str,
                vol.Optional("api_key"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required("clear_key", default=False): bool,
                vol.Required("allow_http", default=values.get("allow_http", False)): bool,
                vol.Required("timeout", default=values.get("timeout", 15)): vol.All(
                    _Numeric(int), vol.Range(min=5, max=60)
                ),
            }
        )
    if provider_kind == "agy":
        schema[vol.Required("search_enabled", default=values.get("search_enabled", False))] = bool
    if provider_kind == "comfyui":
        schema[vol.Required("workflow", default=values.get("workflow", "checkpoint"))] = _select(
            ["checkpoint", "z_image_turbo"], "image_workflow"
        )
        schema[vol.Optional("encoder", default=values.get("encoder", ""))] = str
        schema[vol.Optional("vae", default=values.get("vae", ""))] = str
    metadata = draft["models"].get(old["id"], {})
    for key, listing in (("model", "models"), ("encoder", "encoders"), ("vae", "vaes")):
        choices = metadata.get(listing, [])
        if choices and any(marker.schema == key for marker in schema):
            schema[vol.Optional(key, default=values.get(key, ""))] = _select(choices, custom=True)
    schema[vol.Required("action", default="save")] = _select(
        ["save", "back"], "provider_chain_action"
    )
    return flow.async_show_form(
        step_id=_PREFIX[kind] + "_edit",
        data_schema=vol.Schema(schema),
        errors=errors,
        description_placeholders={"kind": provider_kind},
    )


async def _remove(flow, kind, user_input):
    draft = await _draft(flow, kind)
    row = _row(draft)
    errors = {}
    if user_input is not None:
        try:
            _input(user_input, {"confirmed", "action"}, {"action"})
            if user_input["action"] == "back":
                return await _route(flow, kind)
            if user_input["action"] != "remove" or user_input.get("confirmed") is not True:
                raise DomainError("invalid_field")
            draft["rows"] = [saved for saved in draft["rows"] if saved["id"] != row["id"]]
            draft["selected"] = None
            draft["models"].pop(row["id"], None)
            return await _route(flow, kind)
        except DomainError as error:
            errors["base"] = error.code
    return flow.async_show_form(
        step_id=_PREFIX[kind] + "_remove",
        errors=errors,
        data_schema=vol.Schema(
            {
                vol.Required("confirmed", default=False): bool,
                vol.Required("action", default="back"): _select(
                    ["remove", "back"], "provider_chain_action"
                ),
            }
        ),
        description_placeholders={"name": row["name"]},
    )


async def _test(flow, kind, user_input):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    draft = await _draft(flow, kind)
    row = _row(draft)
    if user_input is not None:
        _input(user_input, {"action"}, {"action"})
        if user_input["action"] == "back":
            return await _route(flow, kind)
        if user_input["action"] != "test":
            raise DomainError("invalid_field")
    errors = {}
    metadata = {}
    try:
        if kind == "image":
            from .assistant.image_providers import ImageProvider

            metadata = await ImageProvider(async_get_clientsession(flow.hass), row).inspect()
        elif row["kind"] == "ha_agent":
            from .assistant.ha_agent_provider import HAConversationAgent

            config = draft["config"].get("ha_agent")
            if not isinstance(config, dict) or not config.get("binding"):
                raise DomainError("ha_agent_unavailable")
            provider = HAConversationAgent(flow.hass, flow.config_entry, config)
            provider.validate_review(await provider.inspect())
            metadata = {"available": True, "models": []}
        else:
            from .assistant.provider_registry import inspect_provider

            metadata = await inspect_provider(async_get_clientsession(flow.hass), row)
        if not isinstance(metadata, dict) or metadata.get("available") is not True:
            raise DomainError("provider_bad_response")
        if any(
            not isinstance(metadata.get(key, []), list) for key in ("models", "encoders", "vaes")
        ):
            raise DomainError("provider_bad_response")
        metadata = {
            key: [
                value
                for value in metadata.get(key, [])[:128]
                if isinstance(value, str)
                and 0 < len(value) <= 256
                and not any(ord(char) < 32 for char in value)
            ]
            for key in ("models", "encoders", "vaes")
        }
        draft["models"][row["id"]] = metadata
    except DomainError as error:
        errors["base"] = error.code
        metadata = {}
        draft["models"].pop(row["id"], None)
    # The decorator rechecks owner, Options and entry epoch after the await,
    # including failed probes. No remote error body or secret is returned.
    return flow.async_show_form(
        step_id=_PREFIX[kind] + "_test",
        errors=errors,
        data_schema=vol.Schema(
            {
                vol.Required("action", default="back"): _select(
                    ["back", "test"], "provider_chain_action"
                )
            }
        ),
        description_placeholders={
            "name": row["name"],
            "models": "\n".join(metadata.get("models", [])) or "—",
            "encoders": "\n".join(metadata.get("encoders", [])) or "—",
            "vaes": "\n".join(metadata.get("vaes", [])) or "—",
        },
    )


class ProviderChainOptionsMixin:
    """Shared UI mechanics; distinct validated text/image schemas and scopes."""

    @guarded_provider_step
    async def async_step_provider_chain(self, user_input=None):
        return await _manager(self, "text", user_input)

    @guarded_provider_step
    async def async_step_provider_chain_kind(self, user_input=None):
        return await _kind(self, "text", user_input)

    @guarded_provider_step
    async def async_step_provider_chain_edit(self, user_input=None):
        return await _edit(self, "text", user_input)

    @guarded_provider_step
    async def async_step_provider_chain_remove(self, user_input=None):
        return await _remove(self, "text", user_input)

    @guarded_provider_step
    async def async_step_provider_chain_test(self, user_input=None):
        return await _test(self, "text", user_input)

    @guarded_provider_step
    async def async_step_image_generation(self, user_input=None):
        return await _manager(self, "image", user_input)

    @guarded_provider_step
    async def async_step_image_provider_kind(self, user_input=None):
        return await _kind(self, "image", user_input)

    @guarded_provider_step
    async def async_step_image_provider_edit(self, user_input=None):
        return await _edit(self, "image", user_input)

    @guarded_provider_step
    async def async_step_image_provider_remove(self, user_input=None):
        return await _remove(self, "image", user_input)

    @guarded_provider_step
    async def async_step_image_provider_test(self, user_input=None):
        return await _test(self, "image", user_input)

    @guarded_provider_step
    async def async_step_image_generation_settings(self, user_input=None):
        from homeassistant.helpers import selector

        from .assistant.image_providers import normalize_config

        draft = await _draft(self, "image")
        errors = {}
        if user_input is not None:
            try:
                _input(
                    user_input,
                    {"width", "height", "steps", "cfg", "negative_prompt", "action"},
                    {"action"},
                )
                if user_input["action"] == "back":
                    return await _route(self, "image")
                if user_input["action"] != "save":
                    raise DomainError("invalid_field")
                values = {key: value for key, value in user_input.items() if key != "action"}
                draft["config"] = normalize_config(
                    {**draft["config"], **values, "providers": draft["rows"]}
                )
                return await _route(self, "image")
            except DomainError as error:
                errors["base"] = error.code
        config = draft["config"]
        return self.async_show_form(
            step_id="image_generation_settings",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("width", default=config.get("width", 512)): vol.In(
                        [512, 768, 1024]
                    ),
                    vol.Required("height", default=config.get("height", 512)): vol.In(
                        [512, 768, 1024]
                    ),
                    vol.Required("steps", default=config.get("steps", 20)): vol.All(
                        _Numeric(int), vol.Range(min=1, max=50)
                    ),
                    vol.Required("cfg", default=config.get("cfg", 7)): vol.All(
                        _Numeric(float), vol.Range(min=1, max=20)
                    ),
                    vol.Optional(
                        "negative_prompt", default=config.get("negative_prompt", "")
                    ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                    vol.Required("action", default="save"): _select(
                        ["save", "back"], "provider_chain_action"
                    ),
                }
            ),
        )
