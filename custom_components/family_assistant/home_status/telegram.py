"""Deterministic private reads; recognized errors never fall through to a model."""

from ..domain.validation import DomainError
from ..telegram.context import PersonalReply
from . import config, observations
from .copy import COPY

ALIASES = {
    "/home": "home",
    "home status": "home",
    "состояние дома": "home",
    "стан дому": "home",
    "/energy": "energy",
    "energy readings": "energy",
    "энергетические показания": "energy",
    "енергетичні показники": "energy",
    "/active": "active",
    "activity states": "active",
    "состояния активности": "active",
    "стани активності": "active",
}


class StatusReply(PersonalReply):
    """Only an opaque request is durable; no state value or source label is kept."""

    def __new__(cls, descriptor):
        result = super().__new__(cls, "home_status")
        result.descriptor = descriptor
        return result


def parse(content):
    text = " ".join(content.split()).casefold()
    if text in ALIASES:
        return config.request(ALIASES[text])
    if text.split(" ", 1)[0] in {"/home", "/energy", "/active", "/status"}:
        if text.startswith("/status "):
            return config.request("group", text[8:])
        raise DomainError("invalid_field")
    return None


async def route(manager, actor_id, content, guard, *, private):
    state = manager.runtime.engine.snapshot()
    language = state["members"][actor_id].get("language", "en")
    t = COPY.get(language, COPY["en"])
    try:
        query = parse(content)
    except DomainError:
        return PersonalReply(t["invalid"]) if private else t["private"]
    if query is None:
        return None
    if not private:
        return t["private"]
    try:
        user = await observations.actor_user(
            manager.hass, manager.entry, manager.runtime, actor_id, guard
        )
        configured, sources = observations.select(
            manager.hass, manager.entry, manager.runtime, actor_id, user, query
        )
        if not sources:
            return PersonalReply(t["empty"])
        return StatusReply(
            {
                **query,
                "config_marker": observations.configuration_marker(manager.runtime, configured),
            }
        )
    except DomainError:
        return PersonalReply(t["denied"])
