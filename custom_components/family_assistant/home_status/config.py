"""Bounded source configuration; no Home Assistant or physical inference."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from ..domain.validation import DomainError

MODULE = "home_status"
ROLES = ("owner", "parent", "adult", "child")
METRICS = ("battery_soc", "battery_power", "load_power", "pv_power", "grid_power")
DOMAINS = (
    "sensor",
    "switch",
    "light",
    "input_boolean",
    "binary_sensor",
    "media_player",
    "climate",
    "weather",
    "camera",
    "event",
)
STATES = {
    "switch": ("on", "off"),
    "light": ("on", "off"),
    "input_boolean": ("on", "off"),
    "binary_sensor": ("on", "off"),
    "media_player": ("on", "off", "playing", "paused", "buffering", "idle", "standby"),
    "climate": ("off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"),
}
# Factual group readouts do not confer an activity mapping or any device control.
GROUP_STATES = {
    **STATES,
    "camera": ("idle", "recording", "streaming"),
    "weather": (
        "clear-night",
        "cloudy",
        "fog",
        "hail",
        "lightning",
        "lightning-rainy",
        "partlycloudy",
        "pouring",
        "rainy",
        "snowy",
        "snowy-rainy",
        "sunny",
        "windy",
        "windy-variant",
        "exceptional",
    ),
}
MAX_SOURCES = 64
MAX_GROUPS = 32
DEFAULT = {"revision": 0, "max_age_seconds": 300, "groups": [], "sources": []}


def fail():
    raise DomainError("invalid_field")


def label(value, limit=80):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        fail()
    return value.strip()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", value):
        fail()
    return value


def roles(value):
    if (
        not isinstance(value, list)
        or not value
        or any(role not in ROLES for role in value)
        or len(set(value)) != len(value)
    ):
        fail()
    return list(value)


def validate(value):
    """Return a canonical copy, rejecting malformed persisted and UI configuration."""
    if value is None:
        return deepcopy(DEFAULT)
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        fail()
    if type(value["revision"]) is not int or not 0 <= value["revision"] <= 2**53 - 1:
        fail()
    if type(value["max_age_seconds"]) is not int or not 30 <= value["max_age_seconds"] <= 86400:
        fail()
    groups, sources = value["groups"], value["sources"]
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS:
        fail()
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        fail()
    seen_groups, seen_sources, seen_metrics = set(), set(), set()
    result = {**value, "groups": [], "sources": []}
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"id", "title", "roles"}:
            fail()
        key = identifier(group["id"])
        if key in seen_groups:
            fail()
        seen_groups.add(key)
        result["groups"].append(
            {"id": key, "title": label(group["title"]), "roles": roles(group["roles"])}
        )
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
            "id",
            "label",
            "entity_id",
            "registry_id",
            "section",
            "group_id",
            "metric",
            "roles",
            "active_states",
        }:
            fail()
        key = identifier(source["id"])
        entity = source["entity_id"]
        if (
            key in seen_sources
            or not isinstance(entity, str)
            or not re.fullmatch(r"(?:" + "|".join(DOMAINS) + r")\.[a-z0-9_]{1,200}", entity)
        ):
            fail()
        seen_sources.add(key)
        domain = entity.split(".", 1)[0]
        registry_id = label(source["registry_id"], 100)
        section = source["section"]
        active = source["active_states"]
        if not isinstance(active, list) or any(not isinstance(item, str) for item in active):
            fail()
        if section == "energy":
            if (
                domain != "sensor"
                or source["metric"] not in METRICS
                or source["metric"] in seen_metrics
            ):
                fail()
            seen_metrics.add(source["metric"])
            if source["group_id"] is not None or active:
                fail()
        elif section == "group":
            if (
                not isinstance(source["group_id"], str)
                or source["group_id"] not in seen_groups
                or source["metric"] is not None
                or active
            ):
                fail()
        elif section == "active":
            if domain not in STATES or not active or len(set(active)) != len(active):
                fail()
            if any(item not in STATES[domain] for item in active):
                fail()
            if source["group_id"] is not None or source["metric"] is not None:
                fail()
        else:
            fail()
        result["sources"].append(
            {
                **source,
                "id": key,
                "label": label(source["label"]),
                "registry_id": registry_id,
                "roles": roles(source["roles"]),
                "active_states": list(active),
            }
        )
    return result


def from_options(options):
    return validate(dict(options).get(MODULE))


def marker(config):
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def request(section="home", group_id=None):
    if section not in {"home", "energy", "active", "group"}:
        fail()
    if section == "group":
        identifier(group_id)
    elif group_id is not None:
        fail()
    return {"section": section, "group_id": group_id}


def visible_sources(config, role, query):
    groups = {item["id"]: item for item in config["groups"] if role in item["roles"]}
    return [
        source
        for source in config["sources"]
        if role in source["roles"]
        and (source["section"] != "group" or source["group_id"] in groups)
        and (query["section"] == "home" or source["section"] == query["section"])
        and (query["section"] != "group" or source["group_id"] == query["group_id"])
    ]
