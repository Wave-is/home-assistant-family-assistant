"""Recipe provider checks through actual Home Assistant options and WebSockets."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime

from aiohttp import ClientSession, TCPConnector, ThreadedResolver, web
from voluptuous import UNDEFINED


class SyntheticMealie:
    """Small authenticated Mealie v3 wire fixture bound only to loopback."""

    def __init__(self) -> None:
        self.token = "synthetic-recipe-token"
        self.version = "3.2.1"
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.pause = False
        self.fail_next = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.runner: web.AppRunner | None = None
        self.url = ""

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/api/app/about", self.about)
        app.router.add_get("/api/recipes", self.search)
        app.router.add_get("/api/recipes/{slug}", self.recipe)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        sockets = site._server.sockets  # type: ignore[union-attr]  # aiohttp test fixture
        self.url = f"http://127.0.0.1:{sockets[0].getsockname()[1]}"

    async def close(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def _record(self, request: web.Request, *, authenticated: bool = False) -> None:
        self.requests.append((request.method, request.path, dict(request.query)))
        if authenticated and request.headers.get("Authorization") != f"Bearer {self.token}":
            raise web.HTTPUnauthorized()
        if self.pause:
            self.pause = False
            self.started.set()
            await self.release.wait()
        if self.fail_next:
            self.fail_next = False
            raise web.HTTPInternalServerError()

    def pause_once(self) -> None:
        self.pause = True
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def about(self, request: web.Request) -> web.Response:
        await self._record(request)
        return web.json_response({"version": self.version})

    async def search(self, request: web.Request) -> web.Response:
        await self._record(request, authenticated=True)
        page = int(request.query.get("page", "0"))
        per_page = int(request.query.get("perPage", "0"))
        items = (
            [{"id": "recipe-1", "slug": "tomato-soup", "name": "Tomato soup"}] if page == 1 else []
        )
        return web.json_response(
            {
                "page": page,
                "per_page": per_page,
                "total": 1,
                "total_pages": 1,
                "items": items,
                "next": None,
                "previous": None,
            }
        )

    async def recipe(self, request: web.Request) -> web.Response:
        await self._record(request, authenticated=True)
        slug = request.match_info["slug"]
        if slug != "tomato-soup":
            raise web.HTTPNotFound()
        return web.json_response(
            {
                "id": "recipe-1",
                "slug": slug,
                "name": "Tomato soup",
                "recipeServings": 4,
                "settings": {"disableAmount": False},
                "recipeIngredient": [
                    {
                        "display": "2 kg tomatoes",
                        "quantity": 2,
                        "food": {"name": "Tomatoes"},
                        "unit": {"name": "kg"},
                    }
                ],
            }
        )


async def _recipes_form(hass, entry, user):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    return await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "recipes"}
    )


async def _configure(hass, entry, user, values):
    form = await _recipes_form(hass, entry, user)
    assert form["type"] == "form" and form["step_id"] == "recipes", form
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/recipe-smoke"
    )
    token = hass.auth.async_create_access_token(refresh)
    session = ClientSession()
    try:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        assert (await ws.receive_json())["type"] == "auth_required"
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        yield ws
        await ws.close()
    finally:
        await session.close()
        hass.auth.async_remove_refresh_token(refresh)


async def _message(hass, entry, user, identifier, kind, **values):
    async with _socket(hass, user) as ws:
        await ws.send_json(
            {
                "id": identifier,
                "type": "family_assistant/recipes",
                "entry_id": entry.entry_id,
                "kind": kind,
                **values,
            }
        )
        return await ws.receive_json()


async def _paused_message(hass, entry, user, server, identifier):
    server.pause_once()
    socket = _socket(hass, user)
    ws = await socket.__aenter__()
    await ws.send_json(
        {
            "id": identifier,
            "type": "family_assistant/recipes",
            "entry_id": entry.entry_id,
            "kind": "search",
            "query": "soup",
            "page": 1,
        }
    )
    await asyncio.wait_for(server.started.wait(), 5)
    return socket, ws


async def verify_recipes(hass, entry, owner, child_id):
    """Exercise recipe options, real HTTP parsing, privacy and in-flight revocation."""
    from homeassistant.data_entry_flow import InvalidData
    from homeassistant.helpers import aiohttp_client as ha_aiohttp_client

    from custom_components.family_assistant.recipes import options as recipe_options

    engine = entry.runtime_data.engine
    child_user_id = engine.snapshot()["members"][child_id]["ha_user_id"]
    child = await hass.auth.async_get_user(child_user_id)
    assert child is not None
    server = SyntheticMealie()
    await server.start()
    # HA's multicast-aware resolver cannot initialize in the network-none lab.
    # Keep the provider on a separately owned real aiohttp transport with the
    # standard threaded resolver; every requested URL remains numeric loopback.
    resolver = ThreadedResolver()
    connector = TCPConnector(resolver=resolver)
    provider_session = ClientSession(connector=connector)
    original_ha_session = ha_aiohttp_client.async_get_clientsession
    original_options_session = recipe_options.async_get_clientsession

    def loopback_session(_hass, *_args, **_kwargs):
        return provider_session

    ha_aiohttp_client.async_get_clientsession = loopback_session
    recipe_options.async_get_clientsession = loopback_session
    original_settings = deepcopy(engine.snapshot()["settings"])
    original_child = deepcopy(engine.snapshot()["members"][child_id])
    try:
        # The password selector is intentionally blank on every form rendering.
        form = await _recipes_form(hass, entry, owner)
        token_marker = next(
            marker for marker in form["data_schema"].schema if marker.schema == "token"
        )
        assert token_marker.default is UNDEFINED

        denied = await _recipes_form(hass, entry, child)
        assert denied["type"] == "abort" and denied["reason"] == "forbidden", denied

        configured = await _configure(
            hass,
            entry,
            owner,
            {
                "enabled": True,
                "url": server.url,
                "token": server.token,
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert configured["type"] == "create_entry", configured
        first_revision = entry.options["recipes"]["revision"]
        assert entry.runtime_data.recipes is not None

        # Blank on the same URL preserves the credential; changing its scope does not.
        preserved = await _configure(
            hass,
            entry,
            owner,
            {
                "enabled": True,
                "url": server.url,
                "token": "",
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert preserved["type"] == "create_entry", preserved
        assert entry.options["recipes"]["token"] == server.token
        assert entry.options["recipes"]["revision"] != first_revision
        preserved_revision = entry.options["recipes"]["revision"]

        # Two independently displayed forms cannot overwrite one another. A stale
        # re-enable is rejected before it can contact the provider.
        stale_form = await _recipes_form(hass, entry, owner)
        current_form = await _recipes_form(hass, entry, owner)
        disabled_result = await hass.config_entries.options.async_configure(
            current_form["flow_id"],
            {
                "enabled": False,
                "url": server.url,
                "token": "",
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        await hass.async_block_till_done()
        assert disabled_result["type"] == "create_entry", disabled_result
        request_count = len(server.requests)
        stale_result = await hass.config_entries.options.async_configure(
            stale_form["flow_id"],
            {
                "enabled": True,
                "url": server.url,
                "token": "",
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert stale_result["type"] == "form"
        assert stale_result["errors"]["base"] == "conflict", stale_result
        assert len(server.requests) == request_count
        assert entry.runtime_data.recipes is None
        reenabled = await _configure(
            hass,
            entry,
            owner,
            {
                "enabled": True,
                "url": server.url,
                "token": "",
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert reenabled["type"] == "create_entry", reenabled
        preserved_revision = entry.options["recipes"]["revision"]

        # Even same-actor/same-role membership ABA during provider inspection is stale.
        aba_form = await _recipes_form(hass, entry, owner)
        server.pause_once()
        aba_task = asyncio.create_task(
            hass.config_entries.options.async_configure(
                aba_form["flow_id"],
                {
                    "enabled": True,
                    "url": server.url,
                    "token": "",
                    "clear_token": False,
                    "allow_http": True,
                    "timeout": 5,
                },
            )
        )
        await asyncio.wait_for(server.started.wait(), 5)
        owner_record = engine.snapshot()["members"]["owner"]
        changed_owner = await engine.execute(
            "owner",
            "members.save",
            {
                "id": "owner",
                "revision": owner_record["revision"],
                "name": "Synthetic owner during recipe inspection",
                "role": "owner",
            },
            "recipe-options-owner-change",
            datetime.now(UTC),
        )
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "owner",
                "revision": changed_owner["revision"],
                "name": owner_record["name"],
                "role": "owner",
            },
            "recipe-options-owner-restore",
            datetime.now(UTC),
        )
        server.release.set()
        aba_result = await asyncio.wait_for(aba_task, 5)
        assert aba_result["type"] == "form"
        assert aba_result["errors"]["base"] == "conflict", aba_result
        assert entry.options["recipes"]["revision"] == preserved_revision

        # A provider failure after the initiating owner loses authority must not
        # redisplay the private URL or replace the authorization error.
        current_child = engine.snapshot()["members"][child_id]
        promoted_owner = await engine.execute(
            "owner",
            "members.save",
            {
                "id": child_id,
                "revision": current_child["revision"],
                "name": current_child["name"],
                "role": "owner",
            },
            "recipe-options-promote-owner",
            datetime.now(UTC),
        )
        revoked_form = await _recipes_form(hass, entry, child)
        server.pause_once()
        server.fail_next = True
        revoked_task = asyncio.create_task(
            hass.config_entries.options.async_configure(
                revoked_form["flow_id"],
                {
                    "enabled": True,
                    "url": server.url,
                    "token": "",
                    "clear_token": False,
                    "allow_http": True,
                    "timeout": 5,
                },
            )
        )
        await asyncio.wait_for(server.started.wait(), 5)
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": child_id,
                "revision": promoted_owner["revision"],
                "name": current_child["name"],
                "role": current_child["role"],
            },
            "recipe-options-role-revoke",
            datetime.now(UTC),
        )
        server.release.set()
        revoked_result = await asyncio.wait_for(revoked_task, 5)
        assert revoked_result["type"] == "abort"
        assert revoked_result["reason"] == "forbidden", revoked_result
        assert server.url not in str(revoked_result) and server.token not in str(revoked_result)
        assert entry.options["recipes"]["revision"] == preserved_revision

        blocked = await _configure(
            hass,
            entry,
            owner,
            {
                "enabled": True,
                "url": server.url + "/different",
                "token": "",
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert blocked["type"] == "form"
        assert blocked["errors"]["base"] == "provider_key_scope", blocked

        server.version = "4.0.0"
        bad_version = await _configure(
            hass,
            entry,
            owner,
            {
                "enabled": True,
                "url": server.url,
                "token": server.token,
                "clear_token": False,
                "allow_http": True,
                "timeout": 5,
            },
        )
        assert bad_version["type"] == "form"
        assert bad_version["errors"]["base"] == "provider_bad_response", bad_version
        assert entry.options["recipes"]["revision"] == preserved_revision
        server.version = "3.2.1"
        for invalid_timeout in (True, 5.0, "5", 4, 31):
            request_count = len(server.requests)
            current_revision = entry.options["recipes"]["revision"]
            try:
                invalid = await _configure(
                    hass,
                    entry,
                    owner,
                    {
                        "enabled": True,
                        "url": server.url,
                        "token": server.token,
                        "clear_token": False,
                        "allow_http": True,
                        "timeout": invalid_timeout,
                    },
                )
            except InvalidData:
                pass
            else:
                # `bool` can pass HA's int schema because bool subclasses int;
                # the provider constructor still enforces a strict integer.
                assert invalid["type"] == "form" and invalid.get("errors"), invalid
            assert len(server.requests) == request_count
            assert entry.options["recipes"]["revision"] == current_revision

        before_reads = deepcopy(engine.snapshot())
        view = await _message(hass, entry, owner, 1, "search", query="soup", page=1)
        assert view["success"], view
        assert view["result"] == {
            "source_revision": entry.runtime_data.recipes_revision,
            "page": 1,
            "total_pages": 1,
            "items": [{"id": "recipe-1", "slug": "tomato-soup", "name": "Tomato soup"}],
        }
        detail = await _message(hass, entry, owner, 2, "get", slug="tomato-soup")
        assert detail["success"], detail
        candidate = detail["result"]["candidate"]
        assert candidate["source"] == {
            "provider": "mealie",
            "id": "recipe-1",
            "slug": "tomato-soup",
        }
        assert candidate["source_servings"] == {"value": 4, "display": "4"}
        assert candidate["ingredients"] == [
            {
                "display": "2 kg tomatoes",
                "name": "Tomatoes",
                "unit": "kg",
                "quantity": 2.0,
                "blockers": [],
            }
        ]
        request_count = len(server.requests)
        invalid_get = await _message(hass, entry, owner, 6, "get", slug="tomato-soup", page=True)
        assert not invalid_get["success"]
        assert invalid_get["error"]["code"] == "invalid_field", invalid_get
        assert len(server.requests) == request_count
        assert engine.snapshot() == before_reads
        assert all(method == "GET" for method, _, _ in server.requests)
        recipe_lists = [query for _, path, query in server.requests if path == "/api/recipes"]
        assert any(query.get("perPage") == "1" for query in recipe_lists)
        assert any(query.get("perPage") == "10" for query in recipe_lists)

        child_denied = await _message(hass, entry, child, 3, "search", query="", page=1)
        assert not child_denied["success"]
        assert child_denied["error"]["code"] == "forbidden"
        async with _socket(hass, owner) as ws:
            await ws.send_json(
                {"id": 4, "type": "family_assistant/view", "entry_id": entry.entry_id}
            )
            parent_view = await ws.receive_json()
        assert parent_view["success"]
        source = parent_view["result"]["recipe_source"]
        assert source == {
            "enabled": True,
            "provider": "mealie",
            "revision": entry.runtime_data.recipes_revision,
        }
        assert server.url not in str(parent_view) and server.token not in str(parent_view)
        async with _socket(hass, child) as ws:
            await ws.send_json(
                {"id": 5, "type": "family_assistant/view", "entry_id": entry.entry_id}
            )
            child_view = await ws.receive_json()
        assert child_view["success"] and "recipe_source" not in child_view["result"]

        # A request is authorized again after transport. Configuration, membership,
        # role and module changes must prevent the old response from being released.
        config_socket, config_ws = await _paused_message(hass, entry, owner, server, 10)
        options = dict(entry.options)
        options["recipes"] = {
            **dict(entry.options["recipes"]),
            "revision": "synthetic-source-revision-change",
        }
        hass.config_entries.async_update_entry(entry, options=options)
        async with asyncio.timeout(5):
            while entry.runtime_data.recipes_revision != options["recipes"]["revision"]:
                await asyncio.sleep(0.01)
        server.fail_next = True
        server.release.set()
        response = await config_ws.receive_json()
        await config_socket.__aexit__(None, None, None)
        assert not response["success"] and response["error"]["code"] == "conflict", response

        # Promote the already-bound synthetic child only for parent-source race checks.
        current = engine.snapshot()["members"][child_id]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": child_id,
                "revision": current["revision"],
                "name": current["name"],
                "role": "parent",
            },
            "recipe-promote-child",
            datetime.now(UTC),
        )
        async with _socket(hass, child) as ws:
            await ws.send_json(
                {"id": 9, "type": "family_assistant/view", "entry_id": entry.entry_id}
            )
            promoted_view = await ws.receive_json()
        assert promoted_view["success"]
        assert promoted_view["result"]["recipe_source"]["provider"] == "mealie"
        assert server.url not in str(promoted_view) and server.token not in str(promoted_view)
        member_socket, member_ws = await _paused_message(hass, entry, child, server, 11)
        current = engine.snapshot()["members"][child_id]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": child_id,
                "revision": current["revision"],
                "name": "Synthetic child renamed during recipe request",
                "role": "parent",
            },
            "recipe-member-change",
            datetime.now(UTC),
        )
        server.fail_next = True
        server.release.set()
        response = await member_ws.receive_json()
        await member_socket.__aexit__(None, None, None)
        assert not response["success"] and response["error"]["code"] == "conflict", response

        role_socket, role_ws = await _paused_message(hass, entry, child, server, 12)
        current = engine.snapshot()["members"][child_id]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": child_id,
                "revision": current["revision"],
                "name": current["name"],
                "role": "child",
            },
            "recipe-role-revoke",
            datetime.now(UTC),
        )
        server.fail_next = True
        server.release.set()
        response = await role_ws.receive_json()
        await role_socket.__aexit__(None, None, None)
        assert not response["success"] and response["error"]["code"] == "forbidden", response

        module_socket, module_ws = await _paused_message(hass, entry, owner, server, 13)
        settings = engine.snapshot()["settings"]
        await engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": [m for m in settings["modules"] if m != "pantry"],
            },
            "recipe-module-revoke",
            datetime.now(UTC),
        )
        server.fail_next = True
        server.release.set()
        response = await module_ws.receive_json()
        await module_socket.__aexit__(None, None, None)
        assert not response["success"]
        assert response["error"]["code"] == "module_disabled", response
    finally:
        # Restore shared synthetic household state before later smoke helpers run.
        server.release.set()
        settings = engine.snapshot()["settings"]
        if settings["modules"] != original_settings["modules"]:
            await engine.execute(
                "owner",
                "settings.save",
                {
                    "name": settings["name"],
                    "language": settings["language"],
                    "modules": original_settings["modules"],
                },
                "recipe-restore-modules",
                datetime.now(UTC),
            )
        child_record = engine.snapshot()["members"][child_id]
        if (
            child_record["name"] != original_child["name"]
            or child_record["role"] != original_child["role"]
        ):
            await engine.execute(
                "owner",
                "members.save",
                {
                    "id": child_id,
                    "revision": child_record["revision"],
                    "name": original_child["name"],
                    "role": original_child["role"],
                },
                "recipe-restore-child",
                datetime.now(UTC),
            )
        try:
            disabled = await _configure(
                hass,
                entry,
                owner,
                {
                    "enabled": False,
                    "url": server.url,
                    "token": "",
                    "clear_token": True,
                    "allow_http": True,
                    "timeout": 5,
                },
            )
            async with _socket(hass, owner) as ws:
                await ws.send_json(
                    {"id": 20, "type": "family_assistant/view", "entry_id": entry.entry_id}
                )
                disabled_view = await ws.receive_json()
        finally:
            recipe_options.async_get_clientsession = original_options_session
            ha_aiohttp_client.async_get_clientsession = original_ha_session
            await provider_session.close()
            await resolver.close()
            await server.close()
        assert disabled["type"] == "create_entry", disabled
        assert not entry.options["recipes"]["enabled"]
        assert "token" not in entry.options["recipes"]
        assert entry.runtime_data.recipes is None
        assert disabled_view["success"]
        assert disabled_view["result"]["recipe_source"] == {
            "enabled": False,
            "provider": "mealie",
            "revision": entry.runtime_data.recipes_revision,
        }
        assert server.url not in str(disabled_view) and server.token not in str(disabled_view)
    print("PASS: actual HA recipe options, authenticated GET parsing, privacy and revocation")
