"""UI onboarding and owner-managed family members."""

from __future__ import annotations

import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import DEFAULT_MODULES, DOMAIN, LANGUAGES, ROLES
from .domain.household import TEMPLATES, timezone
from .domain.validation import DomainError


def select(options, translation_key=None):
    config = {"options": list(options)}
    if translation_key:
        config["translation_key"] = translation_key
    return selector.SelectSelector(selector.SelectSelectorConfig(**config))


class FamilyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FamilyOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user = await self.hass.auth.async_get_user(self.context.get("user_id"))
            if user is None or not user.is_admin:
                return self.async_abort(reason="admin_required")
            if not user_input["name"].strip() or not user_input["owner_name"].strip():
                errors["base"] = "invalid_field"
            else:
                try:
                    timezone(user_input.get("timezone", self.hass.config.time_zone))
                except DomainError:
                    errors["timezone"] = "invalid_field"
                if errors:
                    return self.async_show_form(
                        step_id="user", data_schema=self._user_schema(user_input), errors=errors
                    )
                self._household = {**user_input, "owner_user_id": user.id}
                return await self.async_step_modules()
        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(user_input or {}),
            errors=errors,
        )

    def _user_schema(self, values):
        return vol.Schema(
            {
                vol.Required("name", default=values.get("name", "Family")): str,
                vol.Required("owner_name", default=values.get("owner_name", "")): str,
                vol.Required("language", default=values.get("language", "en")): select(LANGUAGES),
                vol.Required(
                    "timezone", default=values.get("timezone", self.hass.config.time_zone)
                ): str,
                vol.Required("template", default=values.get("template", "manual")): select(
                    TEMPLATES, "template"
                ),
            }
        )

    async def async_step_modules(self, user_input=None):
        if user_input is not None:
            modules = [key for key in DEFAULT_MODULES if user_input.get(key)]
            self._household["modules"] = modules
            return self.async_create_entry(title=self._household["name"], data=self._household)
        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(
                {vol.Required(module, default=True): bool for module in DEFAULT_MODULES}
            ),
        )


class FamilyOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "member",
                "alarm_device",
                "telegram",
                "telegram_group",
                "telegram_member",
                "conversation",
                "search",
            ],
        )

    def _authorized_runtime(self):
        from .runtime import get_runtime

        runtime = get_runtime(self.hass, self.config_entry.entry_id)
        actor = runtime.engine.actor_for_ha(self.context.get("user_id"))
        if runtime.engine.view(actor)["role"] != "owner":
            raise DomainError("forbidden")
        return runtime, actor

    async def async_step_conversation(self, user_input=None):
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        from .assistant.provider import Ollama

        try:
            self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        current = self.config_entry.options.get("conversation", {})
        errors = {}
        if user_input is not None:
            config = dict(current)
            config["enabled"] = user_input["enabled"]
            try:
                if config["enabled"]:
                    for key in ("primary", "fallback"):
                        if key == "fallback" and not user_input.get("fallback_enabled"):
                            config.pop(key, None)
                            continue
                        old = current.get(key, {})
                        provider = {
                            "url": user_input.get(key + "_url", ""),
                            "model": user_input.get(key + "_model", ""),
                            "allow_http": user_input.get("allow_http", False),
                            "timeout": user_input["timeout"],
                        }
                        # Blank means preserve; explicitly clearing uses the dedicated checkbox.
                        if (
                            provider["url"] != old.get("url")
                            and old.get("api_key")
                            and not (
                                user_input.get(key + "_key") or user_input.get(key + "_clear_key")
                            )
                        ):
                            raise DomainError("provider_key_scope")
                        api_key = user_input.get(key + "_key") or old.get("api_key", "")
                        if user_input.get(key + "_clear_key"):
                            api_key = ""
                        if api_key:
                            provider["api_key"] = api_key
                        await Ollama(async_get_clientsession(self.hass), provider).inspect()
                        config[key] = provider
                options = dict(self.config_entry.options)
                options["conversation"] = config
                return self.async_create_entry(title="", data=options)
            except DomainError as err:
                errors["base"] = err.code
        schema = {vol.Required("enabled", default=current.get("enabled", False)): bool}
        for key in ("primary", "fallback"):
            old = current.get(key, {})
            schema[vol.Optional(key + "_url", default=old.get("url", ""))] = str
            schema[vol.Optional(key + "_model", default=old.get("model", ""))] = str
            schema[vol.Optional(key + "_key")] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
            schema[vol.Required(key + "_clear_key", default=False)] = bool
        schema.update(
            {
                vol.Required("fallback_enabled", default=bool(current.get("fallback"))): bool,
                vol.Required(
                    "allow_http", default=current.get("primary", {}).get("allow_http", False)
                ): bool,
                vol.Required(
                    "timeout", default=current.get("primary", {}).get("timeout", 15)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=45)),
            }
        )
        return self.async_show_form(
            step_id="conversation", data_schema=vol.Schema(schema), errors=errors
        )

    async def async_step_search(self, user_input=None):
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        from .assistant.search import Search

        try:
            self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        current = self.config_entry.options.get("conversation", {}).get("search", {})
        errors = {}
        if user_input is not None:
            options = dict(self.config_entry.options)
            config = dict(options.get("conversation", {}))
            try:
                if user_input["enabled"]:
                    search = {
                        "url": user_input["url"],
                        "allow_http": user_input.get("allow_http", False),
                    }
                    if (
                        search["url"] != current.get("url")
                        and current.get("api_key")
                        and not (user_input.get("api_key") or user_input.get("clear_key"))
                    ):
                        raise DomainError("provider_key_scope")
                    api_key = user_input.get("api_key") or current.get("api_key", "")
                    if api_key and not user_input.get("clear_key"):
                        search["api_key"] = api_key
                    # Uses only a public synthetic query, never household data.
                    await Search(async_get_clientsession(self.hass), search).query(
                        "Home Assistant", "en"
                    )
                    config["search"] = search
                else:
                    config.pop("search", None)
                options["conversation"] = config
                return self.async_create_entry(title="", data=options)
            except DomainError as err:
                errors["base"] = err.code
        return self.async_show_form(
            step_id="search",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("enabled", default=bool(current)): bool,
                    vol.Optional("url", default=current.get("url", "")): str,
                    vol.Optional("api_key"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required("clear_key", default=False): bool,
                    vol.Required("allow_http", default=current.get("allow_http", False)): bool,
                }
            ),
        )

    async def async_step_telegram(self, user_input=None):
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        from .notifications import DeliveryError
        from .telegram.client import TelegramClient

        try:
            self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        current = self.config_entry.options.get("telegram", {})
        errors = {}
        if user_input is not None:
            config = dict(current)
            config["enabled"] = user_input["enabled"]
            token = user_input.get("token") or current.get("token", "")
            if config["enabled"]:
                try:
                    # Detect the built-in HA integration before starting another poller.
                    for existing in self.hass.config_entries.async_entries("telegram_bot"):
                        if existing.data.get("api_key") == token:
                            raise DomainError("telegram_polling_conflict")
                    client = TelegramClient(async_get_clientsession(self.hass), token)
                    bot = await client.inspect()
                    for existing in self.hass.config_entries.async_entries(DOMAIN):
                        other = existing.options.get("telegram", {})
                        if (
                            existing.entry_id != self.config_entry.entry_id
                            and other.get("bot", {}).get("id") == bot["id"]
                        ):
                            raise DomainError("telegram_polling_conflict")
                    config.update(token=token, bot=bot)
                except (DomainError, DeliveryError) as err:
                    errors["base"] = err.code
            if not errors:
                options = dict(self.config_entry.options)
                options["telegram"] = config
                return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="telegram",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("enabled", default=current.get("enabled", True)): bool,
                    vol.Optional("token"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
        )

    async def _begin_enrollment(self, kind, member_id=None):
        from .telegram.enrollment import Enrollment

        try:
            runtime, actor = self._authorized_runtime()
            if not runtime.telegram:
                return self.async_abort(reason="telegram_not_ready")
            self._invite = await Enrollment(runtime.engine).issue(
                actor, kind, dt_util.utcnow(), member_id
            )
            self._invite_kind = kind
        except DomainError as err:
            return self.async_abort(reason=err.code)
        return await self.async_step_telegram_wait()

    async def async_step_telegram_group(self, user_input=None):
        return await self._begin_enrollment("group")

    async def async_step_telegram_member(self, user_input=None):
        try:
            runtime, _actor = self._authorized_runtime()
            if not runtime.telegram:
                return self.async_abort(reason="telegram_not_ready")
        except DomainError as err:
            return self.async_abort(reason=err.code)
        if user_input is not None:
            return await self._begin_enrollment("member", user_input["member"])
        return self.async_show_form(
            step_id="telegram_member",
            data_schema=vol.Schema(
                {
                    vol.Required("member"): select(
                        [
                            {"value": m["id"], "label": m["name"]}
                            for m in runtime.engine.snapshot()["members"].values()
                            if m["active"]
                        ]
                    ),
                }
            ),
        )

    async def async_step_telegram_wait(self, user_input=None):
        from .telegram.enrollment import Enrollment

        try:
            runtime, actor = self._authorized_runtime()
            status = Enrollment(runtime.engine).status(actor, self._invite["id"])
            if dt_util.utcnow() >= dt_util.parse_datetime(status["expires_at"]):
                return self.async_abort(reason="telegram_enrollment_expired")
        except DomainError as err:
            return self.async_abort(reason=err.code)
        if status["state"] == "captured":
            return await self.async_step_telegram_confirm()
        username = self.config_entry.options["telegram"]["bot"]["username"]
        code = self._invite["code"]
        instruction = (
            f"/family_setup@{username} {code}"
            if self._invite_kind == "group"
            else f"https://t.me/{username}?start={code}"
        )
        return self.async_show_form(
            step_id="telegram_wait",
            data_schema=vol.Schema({}),
            description_placeholders={"instruction": instruction},
            errors={"base": "telegram_waiting"} if user_input is not None else {},
        )

    async def async_step_telegram_confirm(self, user_input=None):
        from .telegram.enrollment import Enrollment

        try:
            runtime, actor = self._authorized_runtime()
            enrollment = Enrollment(runtime.engine)
            status = enrollment.status(actor, self._invite["id"])
            if user_input is not None:
                if not user_input.get("confirmed"):
                    return self.async_abort(reason="telegram_not_confirmed")
                await enrollment.confirm(actor, self._invite["id"], dt_util.utcnow())
                runtime.updated()
                return self.async_create_entry(title="", data=dict(self.config_entry.options))
        except DomainError as err:
            return self.async_abort(reason=err.code)
        candidate = status.get("candidate", {})
        return self.async_show_form(
            step_id="telegram_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("confirmed", default=False): bool,
                }
            ),
            description_placeholders={
                "name": candidate.get("name", ""),
                "id": str(candidate.get("chat_id", "")),
            },
        )

    async def async_step_general(self, user_input=None):
        try:
            runtime, actor = self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        errors = {}
        if user_input is not None:
            try:
                result = await runtime.engine.execute(
                    actor,
                    "settings.save",
                    {
                        "name": user_input["name"],
                        "language": user_input["language"],
                        "modules": [
                            m for m in (*DEFAULT_MODULES, "conversation") if user_input.get(m)
                        ],
                        "automatic_penalties": user_input.get("automatic_penalties", False),
                        "daily_penalty_cap": user_input.get("daily_penalty_cap", 1),
                        "timezone": user_input.get(
                            "timezone",
                            runtime.engine.snapshot()["settings"].get(
                                "timezone", self.hass.config.time_zone
                            ),
                        ),
                    },
                    f"options:{uuid.uuid4()}",
                    dt_util.utcnow(),
                )
                runtime.updated()
                self.hass.config_entries.async_update_entry(self.config_entry, title=result["name"])
                return self.async_create_entry(title="", data=dict(self.config_entry.options))
            except DomainError as err:
                errors["base"] = err.code
        settings = runtime.engine.snapshot()["settings"]
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=settings["name"]): str,
                    vol.Required("language", default=settings["language"]): select(LANGUAGES),
                    vol.Required(
                        "timezone", default=settings.get("timezone", self.hass.config.time_zone)
                    ): str,
                    vol.Required(
                        "automatic_penalties", default=settings.get("automatic_penalties", False)
                    ): bool,
                    vol.Required(
                        "daily_penalty_cap", default=settings.get("daily_penalty_cap", 1)
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                    **{
                        vol.Required(m, default=m in settings["modules"]): bool
                        for m in (*DEFAULT_MODULES, "conversation")
                    },
                }
            ),
            errors=errors,
        )

    async def async_step_alarm_device(self, user_input=None):
        from homeassistant.components.siren import SirenEntityFeature

        try:
            runtime, _actor = self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        members = runtime.engine.snapshot()["members"]
        errors = {}
        if user_input is not None:
            if user_input["member"] in members and not user_input.get("enabled", True):
                options = dict(self.config_entry.options)
                bindings = dict(options.get("alarm_devices", {}))
                bindings.pop(user_input["member"], None)
                options["alarm_devices"] = bindings
                return self.async_create_entry(title="", data=options)
            entity_id = user_input.get("entity_id", "")
            state = self.hass.states.get(entity_id)
            features = state.attributes.get("supported_features", 0) if state else 0
            if user_input["member"] not in members:
                errors["base"] = "unknown_member"
            elif not state or not entity_id.startswith("siren."):
                errors["base"] = "device_unavailable"
            elif (
                not features & SirenEntityFeature.TURN_ON
                or not features & SirenEntityFeature.TURN_OFF
            ):
                errors["base"] = "device_unsupported"
            elif not user_input.get("confirmed"):
                errors["base"] = "device_confirmation_required"
            else:
                # An entity belongs to only one wake-up owner/household.
                for other in self.hass.config_entries.async_entries(DOMAIN):
                    for member_id, binding in other.options.get("alarm_devices", {}).items():
                        if binding.get("entity_id") == entity_id and (
                            other.entry_id != self.config_entry.entry_id
                            or member_id != user_input["member"]
                        ):
                            errors["base"] = "device_already_assigned"
                if not errors:
                    options = dict(self.config_entry.options)
                    bindings = dict(options.get("alarm_devices", {}))
                    if user_input.get("enabled", True):
                        bindings[user_input["member"]] = {
                            "entity_id": entity_id,
                            "volume": user_input["volume"],
                            "confirmed": True,
                        }
                    else:
                        bindings.pop(user_input["member"], None)
                    options["alarm_devices"] = bindings
                    return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="alarm_device",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("member"): select(
                        [
                            {"value": m["id"], "label": m["name"]}
                            for m in members.values()
                            if m["active"]
                        ]
                    ),
                    vol.Optional("entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="siren")
                    ),
                    vol.Required("volume", default=0.5): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=1)
                    ),
                    vol.Required("enabled", default=True): bool,
                    vol.Required("confirmed", default=False): bool,
                }
            ),
        )

    async def async_step_member(self, user_input=None):
        try:
            runtime, _actor = self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        if user_input is not None:
            self._member_id = user_input["member_id"]
            return await self.async_step_edit_member()
        options = [
            {
                "value": "_new",
                "label": {"ru": "Добавить участника", "uk": "Додати учасника"}.get(
                    runtime.engine.snapshot()["settings"]["language"], "Add member"
                ),
            }
        ]
        options += [
            {"value": m["id"], "label": m["name"]}
            for m in runtime.engine.snapshot()["members"].values()
        ]
        return self.async_show_form(
            step_id="member",
            data_schema=vol.Schema(
                {
                    vol.Required("member_id"): select(options),
                }
            ),
        )

    async def async_step_edit_member(self, user_input=None):
        try:
            runtime, actor = self._authorized_runtime()
        except DomainError as err:
            return self.async_abort(reason=err.code)
        existing = runtime.engine.snapshot()["members"].get(self._member_id, {})

        errors = {}
        if user_input is not None:
            try:
                payload = dict(user_input)
                if "aliases" in payload:
                    payload["aliases"] = [
                        line.strip() for line in payload["aliases"].splitlines() if line.strip()
                    ]
                if self._member_id != "_new":
                    payload["id"] = self._member_id
                if payload.get("ha_user_id") == "_none":
                    payload["ha_user_id"] = None
                await runtime.engine.execute(
                    actor, "members.save", payload, f"options:{uuid.uuid4()}", dt_util.utcnow()
                )
                runtime.updated()
                return self.async_create_entry(title="", data=dict(self.config_entry.options))
            except DomainError as err:
                errors["base"] = err.code
        users = [{"value": "_none", "label": "—"}]
        users += [
            {"value": user.id, "label": user.name or user.id}
            for user in await self.hass.auth.async_get_users()
            if not user.system_generated
        ]
        return self.async_show_form(
            step_id="edit_member",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=existing.get("name", "")): str,
                    vol.Required("role", default=existing.get("role", "child")): select(
                        ROLES, "role"
                    ),
                    vol.Required("language", default=existing.get("language", "en")): select(
                        LANGUAGES
                    ),
                    vol.Optional(
                        "ha_user_id", default=existing.get("ha_user_id") or "_none"
                    ): select(users),
                    vol.Optional("active", default=existing.get("active", True)): bool,
                    vol.Optional(
                        "aliases", default="\n".join(existing.get("aliases", []))
                    ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                }
            ),
            errors=errors,
        )
