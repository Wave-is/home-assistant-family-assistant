"""Safe registration of the Family Assistant Lovelace module resource."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FRONTEND_URL_ROOT = "/family_assistant/frontend"
FRONTEND_ENTRYPOINT = "family-assistant.js"
OWNERSHIP_QUERY = "family_assistant_resource=1"
LEGACY_RESOURCE_URL = f"{FRONTEND_URL_ROOT}/{FRONTEND_ENTRYPOINT}"
_VERSIONED_ENTRYPOINT_RE = re.compile(
    rf"{re.escape(FRONTEND_URL_ROOT)}/([0-9a-f]{{64}})/{re.escape(FRONTEND_ENTRYPOINT)}"
)
_LOCK_KEY = "frontend_resource_lock"

ResourceStatus = Literal[
    "created",
    "updated",
    "current",
    "yaml_current",
    "yaml_manual",
    "manual_conflict",
    "owned_conflict",
    "lovelace_unavailable",
]


@dataclass(frozen=True, slots=True)
class StaticPath:
    """A static path for runtime to register before HTTP starts."""

    url_path: str
    filesystem_path: str
    cache_headers: bool


@dataclass(frozen=True, slots=True)
class FrontendResource:
    """Content-addressed paths for the complete local JavaScript module graph."""

    fingerprint: str
    resource_url: str
    static_paths: tuple[StaticPath, StaticPath]


@dataclass(frozen=True, slots=True)
class FrontendResourceResult:
    """Outcome of a non-destructive resource reconciliation."""

    status: ResourceStatus
    resource_url: str


@dataclass(frozen=True, slots=True)
class ResourceMutation:
    """A mutation which is safe for the integration to apply."""

    kind: Literal["create", "update", "current", "manual_conflict", "owned_conflict"]
    item_id: str | None = None


def _frontend_directory() -> Path:
    return Path(__file__).resolve().parent / "frontend"


def frontend_fingerprint(directory: Path) -> str:
    """Hash every local JavaScript module and its relative path."""
    root = directory.resolve(strict=True)
    files = sorted(directory.rglob("*.js"), key=lambda path: path.relative_to(directory).as_posix())
    if not files:
        raise RuntimeError("frontend_missing")

    digest = hashlib.sha256()
    for path in files:
        resolved = path.resolve(strict=True)
        if path.is_symlink() or not resolved.is_relative_to(root):
            raise RuntimeError("frontend_invalid_path")
        relative = resolved.relative_to(root).as_posix().encode("utf-8")
        content = resolved.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def prepare_frontend_resource(directory: Path | None = None) -> FrontendResource:
    """Build deterministic paths without touching Home Assistant state."""
    frontend = (directory or _frontend_directory()).resolve(strict=True)
    fingerprint = frontend_fingerprint(frontend)
    versioned_root = f"{FRONTEND_URL_ROOT}/{fingerprint}"
    resource_url = f"{versioned_root}/{FRONTEND_ENTRYPOINT}?{OWNERSHIP_QUERY}"
    return FrontendResource(
        fingerprint=fingerprint,
        resource_url=resource_url,
        static_paths=(
            StaticPath(versioned_root, str(frontend), True),
            StaticPath(FRONTEND_URL_ROOT, str(frontend), False),
        ),
    )


async def async_prepare_frontend_resource(hass: Any) -> FrontendResource:
    """Hash the module graph outside Home Assistant's event loop."""
    return await hass.async_add_executor_job(prepare_frontend_resource)


def owned_fingerprint(url: object) -> str | None:
    """Return the fingerprint only for an exact integration-owned URL."""
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or parsed.fragment or parsed.query != OWNERSHIP_QUERY:
        return None
    match = _VERSIONED_ENTRYPOINT_RE.fullmatch(parsed.path)
    return match.group(1) if match else None


def _collides_with_entrypoint(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return parsed.path == LEGACY_RESOURCE_URL or bool(
        _VERSIONED_ENTRYPOINT_RE.fullmatch(parsed.path)
    )


def plan_resource_mutation(
    items: Iterable[Mapping[str, object]], desired_url: str
) -> ResourceMutation:
    """Classify current records without adopting or deleting manual resources."""
    owned: list[Mapping[str, object]] = []
    manual: list[Mapping[str, object]] = []
    for item in items:
        url = item.get("url")
        if owned_fingerprint(url) is not None:
            owned.append(item)
        elif _collides_with_entrypoint(url):
            manual.append(item)

    if len(owned) > 1:
        return ResourceMutation("owned_conflict")
    if manual:
        return ResourceMutation("manual_conflict")
    if not owned:
        return ResourceMutation("create")

    item = owned[0]
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        return ResourceMutation("owned_conflict")
    if item.get("url") == desired_url and item.get("type") == "module":
        return ResourceMutation("current", item_id)
    return ResourceMutation("update", item_id)


async def async_ensure_frontend_resource(
    hass: Any, resource: FrontendResource
) -> FrontendResourceResult:
    """Create or update only the resource bearing our exact ownership marker."""
    # Imports stay local so pure unit tests do not need Home Assistant installed.
    from homeassistant.components.lovelace.const import (  # noqa: PLC0415
        LOVELACE_DATA,
        MODE_STORAGE,
    )

    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        _LOGGER.warning("Lovelace is unavailable; Family Assistant resource was not registered")
        return FrontendResourceResult("lovelace_unavailable", resource.resource_url)

    if lovelace.resource_mode != MODE_STORAGE:
        items = list(lovelace.resources.async_items() or [])
        current = any(
            item.get("url") in {resource.resource_url, LEGACY_RESOURCE_URL}
            and item.get("type") == "module"
            for item in items
        )
        status: ResourceStatus = "yaml_current" if current else "yaml_manual"
        if not current:
            _LOGGER.warning(
                "Lovelace resources use YAML mode; add the Family Assistant module "
                "resource manually as documented: %s",
                LEGACY_RESOURCE_URL,
            )
        return FrontendResourceResult(status, resource.resource_url)

    domain_data = hass.data.setdefault(DOMAIN, {})
    lock = domain_data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        collection = lovelace.resources
        # ResourceStorageCollection.async_get_info() performs its supported lazy load.
        await collection.async_get_info()
        mutation = plan_resource_mutation(
            list(collection.async_items() or []), resource.resource_url
        )
        if mutation.kind == "manual_conflict":
            _LOGGER.warning(
                "A manual Family Assistant frontend resource already exists; "
                "automatic registration left all Lovelace resources unchanged"
            )
            return FrontendResourceResult("manual_conflict", resource.resource_url)
        if mutation.kind == "owned_conflict":
            _LOGGER.error(
                "Multiple or malformed integration-owned Family Assistant resources exist; "
                "automatic registration left all Lovelace resources unchanged"
            )
            return FrontendResourceResult("owned_conflict", resource.resource_url)
        if mutation.kind == "current":
            return FrontendResourceResult("current", resource.resource_url)
        if mutation.kind == "create":
            await collection.async_create_item({"res_type": "module", "url": resource.resource_url})
            return FrontendResourceResult("created", resource.resource_url)

        await collection.async_update_item(
            mutation.item_id,
            {"res_type": "module", "url": resource.resource_url},
        )
        return FrontendResourceResult("updated", resource.resource_url)
