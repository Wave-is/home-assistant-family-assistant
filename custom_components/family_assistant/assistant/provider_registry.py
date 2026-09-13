"""Ordered optional inference providers; legacy slots are read, never rewritten."""

import re
from copy import deepcopy

from ..domain.validation import DomainError, text
from .provider import AGY, Ollama

MAX_PROVIDERS = 8
KINDS = {"agy", "ollama", "ha_agent"}


def normalize_provider(row, *, allow_missing_model=False):
    """Validate one local config row without probing or disclosing credentials."""
    common = {"id", "kind", "name", "enabled"}
    http = {"url", "model", "api_key", "allow_http", "timeout", "search_enabled"}
    if not isinstance(row, dict) or not {"id", "kind"} <= set(row):
        raise DomainError("invalid_field", "providers")
    identifier, kind = row["id"], row["kind"]
    if (
        not isinstance(identifier, str)
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", identifier)
        or not isinstance(kind, str)
        or kind not in KINDS
        or not set(row) <= (common if kind == "ha_agent" else common | http)
    ):
        raise DomainError("invalid_field", "providers")
    enabled = row.get("enabled", True)
    if type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")
    result = {
        "id": identifier,
        "kind": kind,
        "name": text(row.get("name", identifier), "name", 80),
        "enabled": enabled,
    }
    if kind == "ha_agent":
        return result
    search = row.get("search_enabled", False)
    if type(search) is not bool or search and kind != "agy":
        raise DomainError("invalid_field", "search_enabled")
    result.update(
        url=row.get("url", ""),
        model=row.get("model", ""),
        allow_http=row.get("allow_http", False),
        timeout=row.get("timeout", 15),
    )
    if "api_key" in row:
        result["api_key"] = row["api_key"]
    # Constructors validate only their configuration. No session or network yet.
    client = http_provider(None, result, require_model=enabled and not allow_missing_model)
    result.update(url=client.url, model=client.model)
    if kind == "agy":
        result["search_enabled"] = search
    return result


def normalize_providers(rows):
    if not isinstance(rows, list) or len(rows) > MAX_PROVIDERS:
        raise DomainError("invalid_field", "providers")
    result = [normalize_provider(row) for row in rows]
    if len({row["id"] for row in result}) != len(result):
        raise DomainError("invalid_field", "providers")
    if sum(row["kind"] == "ha_agent" for row in result) > 1:
        raise DomainError("invalid_field", "providers")
    return result


def provider_rows(config):
    """An explicit list, even empty, takes precedence over dormant legacy slots."""
    if not isinstance(config, dict):
        raise DomainError("invalid_field", "conversation")
    if "providers" in config:
        return normalize_providers(config["providers"])
    rows = []
    for key, kind in (
        ("agy", "agy"),
        ("ha_agent", "ha_agent"),
        ("primary", "ollama"),
        ("fallback", "ollama"),
    ):
        saved = config.get(key)
        if not saved:
            continue
        if not isinstance(saved, dict):
            raise DomainError("invalid_field", "providers")
        row = {} if kind == "ha_agent" else deepcopy(saved)
        rows.append({**row, "id": key, "kind": kind})
    return normalize_providers(rows)


configured_providers = provider_rows


def http_provider(session, row, *, require_model=True):
    """Construct a configured HTTP adapter; HA agents require reviewed HA scope."""
    if row.get("kind") == "agy":
        return AGY(session, row, require_model=require_model)
    if row.get("kind") == "ollama":
        return Ollama(session, row, require_model=require_model)
    raise DomainError("invalid_field", "kind")


async def inspect_provider(session, row):
    """Explicit read-only metadata discovery; a model selection is not required."""
    checked = normalize_provider(row, allow_missing_model=True)
    client = http_provider(session, checked, require_model=False)
    models = await client.models()
    if client.model and client.model not in models:
        raise DomainError("provider_model_missing")
    return {"available": True, "models": models}
