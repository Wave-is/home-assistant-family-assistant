"""Public static Mini App shell; all private operations require Telegram scope.

The reverse proxy must route only this exact Academy prefix, not generic HA.
"""
import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .academy import courses, mini_auth, providers
from .academy.household import AcademyError
from .command_scope import _entry_runtime
from .domain.validation import DomainError

HEADERS = {
    "Cache-Control":"private, no-store",
    "X-Content-Type-Options":"nosniff",
    "Referrer-Policy":"no-referrer",
    "Cross-Origin-Resource-Policy":"same-origin",
    "Content-Security-Policy":"default-src 'none'; script-src 'self' https://telegram.org; "
        "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'; "
        "frame-ancestors 'self' https://web.telegram.org",
}
ASSETS = {"index":("academy-mini.html","text/html"),
          "app.js":("academy-mini.js","application/javascript"),
          "style.css":("academy-mini.css","text/css")}


def _scope(request,entry_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",entry_id):
        raise AcademyError("forbidden")
    hass = request.app[KEY_HASS]
    entry,runtime,engine = _entry_runtime(hass,entry_id)
    if engine.shadow_mode or runtime.telegram is None:
        raise AcademyError("forbidden")
    manager = runtime.telegram
    manager._manager_guard()
    config = mini_auth.policy(engine.snapshot())
    if request.host != urlsplit(config["origin"]).netloc:
        raise AcademyError("forbidden")
    return hass,entry,runtime,engine,manager,config


async def _body(request):
    if request.content_type != "application/json" or request.headers.get("Content-Encoding"):
        raise AcademyError("invalid_field")
    if request.content_length is not None and request.content_length > 16384:
        raise AcademyError("invalid_field")
    raw = bytearray()
    async with asyncio.timeout(5):
        async for chunk in request.content.iter_chunked(4096):
            raw.extend(chunk)
            if len(raw) > 16384:
                raise AcademyError("invalid_field")
    body = json.loads(raw)
    if type(body) is not dict:
        raise AcademyError("invalid_field")
    return body


class AcademyMiniView(HomeAssistantView):
    url = mini_auth.PATH + "/{entry_id}/{asset}"
    name = "api:family_assistant:academy_mini"
    requires_auth = False

    def __init__(self):
        self.sessions = mini_auth.Sessions()
        self.busy = set()
        self.last_provider = {}

    async def get(self,request,entry_id,asset):
        try:
            hass,*_ = _scope(request,entry_id)
            if asset not in ASSETS:
                raise AcademyError("forbidden")
            filename,mime = ASSETS[asset]
            path = Path(__file__).with_name("frontend") / filename
            content = await hass.async_add_executor_job(path.read_bytes)
            _scope(request,entry_id)
            return web.Response(body=content,content_type=mime,headers=HEADERS)
        except (AcademyError,DomainError,ValueError,TypeError,KeyError,AttributeError,OSError):
            return web.json_response({"code":"forbidden"},status=403,headers=HEADERS)

    async def post(self,request,entry_id,asset):
        try:
            if asset != "api":
                raise AcademyError("forbidden")
            hass,entry,runtime,engine,manager,config = _scope(request,entry_id)
            if request.headers.getall("Origin",[]) != [config["origin"]]:
                raise AcademyError("forbidden")
            body = await _body(request)
            now = dt_util.utcnow()
            now_sec = int(now.timestamp())
            bot_id = manager.bot["id"]

            def structural():
                _,current_entry,current_runtime,current_engine,current_manager,current_config = (
                    _scope(request,entry_id)
                )
                if (current_entry is not entry or current_runtime is not runtime
                        or current_engine is not engine or current_manager is not manager
                        or current_config != config):
                    raise AcademyError("forbidden")

            structural()
            action = body.get("action")
            if action == "auth":
                if set(body) != {"action","init_data"}:
                    raise AcademyError("invalid_field")
                token = entry.options["telegram"]["token"]
                if int(token.split(":",1)[0]) != bot_id:
                    raise AcademyError("forbidden")
                uid,digest = mini_auth.verify_init(body["init_data"],token,now_sec)
                stamp = mini_auth.binding(engine.snapshot(),uid,bot_id)

                def authorize(ctx):
                    if mini_auth.binding(ctx.state,uid,bot_id) != stamp:
                        raise AcademyError("forbidden")
                    mini_auth.consume(ctx.state,digest,now_sec)

                await engine.system_update("academy_mini_auth",now,authorize,
                                           guard=lambda state:structural())
                structural()
                if mini_auth.binding(engine.snapshot(),uid,bot_id) != stamp:
                    raise AcademyError("forbidden")
                result = {"session":self.sessions.issue(entry_id,stamp,now_sec)}
            else:
                token = request.headers.get("X-Academy-Session")
                stamp = self.sessions.check(token,entry_id,engine.snapshot(),bot_id,now_sec)
                actor = stamp["actor"]

                def guard(state=None):
                    structural()
                    if self.sessions.check(token,entry_id,
                            engine.snapshot() if state is None else state,
                            bot_id,int(time.time())) != stamp:
                        raise AcademyError("forbidden")

                guard()
                if action == "read" and set(body) == {"action"}:
                    result = courses.read(engine.snapshot(),actor,now)
                elif action == "act" and set(body) == {"action","payload"}:
                    result = await engine.system_update("academy_course",now,
                        lambda ctx:courses.action(ctx.state,actor,now,body["payload"]),guard=guard)
                    guard()
                    runtime.updated()
                elif action in {"tutor","videos"}:
                    expected = {"action","question"} if action == "tutor" else {"action"}
                    if set(body) != expected:
                        raise AcademyError("invalid_field")
                    key = (entry_id,actor)
                    if key in self.busy or len(self.busy) >= 8:
                        raise AcademyError("conflict")
                    clock = time.monotonic()
                    self.last_provider = {k:v for k,v in self.last_provider.items() if clock-v < 60}
                    if key in self.last_provider:
                        raise AcademyError("provider_rate_limited")
                    self.last_provider[key] = clock
                    self.busy.add(key)
                    try:
                        state = engine.snapshot()
                        cfg = providers.public(state)
                        before = courses.read(state,actor,now)["plan"]

                        def provider_guard():
                            guard()
                            current = engine.snapshot()
                            if (providers.public(current) != cfg or
                                courses.read(current,actor,dt_util.utcnow())["plan"] != before):
                                raise AcademyError("conflict")

                        if action == "tutor":
                            result = await providers.tutor(runtime,state,actor,now,
                                                          body["question"],provider_guard)
                        else:
                            result = await providers.videos(async_get_clientsession(hass),
                                                           state,actor,now,provider_guard)
                        provider_guard()
                    finally:
                        self.busy.discard(key)
                else:
                    raise AcademyError("invalid_field")
            return web.json_response(result,headers=HEADERS)
        except (AcademyError,DomainError) as error:
            allowed = {"conflict","invalid_field","forbidden","provider_rate_limited",
                       "course_capacity","course_session_active","backup_in_progress"}
            code = error.code if error.code in allowed else "forbidden"
            status = 400 if code == "invalid_field" else 403 if code == "forbidden" else 409
            return web.json_response({"code":code},status=status,headers=HEADERS)
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError,TimeoutError):
            return web.json_response({"code":"invalid_field"},status=400,headers=HEADERS)
        except OSError:
            return web.json_response({"code":"storage_error"},status=503,headers=HEADERS)


def async_register_mini(hass):
    hass.http.register_view(AcademyMiniView())
