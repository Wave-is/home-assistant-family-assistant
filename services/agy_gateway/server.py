"""Aiohttp application factory and route registration for AGY gateway."""

from __future__ import annotations

import logging

from aiohttp import web

from .auth import create_auth_middleware
from .chat import handle_chat
from .config import GATEWAY_CONFIG_KEY, GatewayConfig
from .images import (
    JOB_MANAGER_KEY,
    ImageJobManager,
    StorageUnavailable,
    handle_get_image_content,
    handle_get_image_status,
    handle_models,
    handle_submit_image,
)
from .search import handle_search

logger = logging.getLogger(__name__)


async def handle_health(request: web.Request) -> web.Response:
    """Public health check endpoint returning non-sensitive operational status."""
    return web.json_response({"status": "ok"})


def create_app(config: GatewayConfig | None = None) -> web.Application:
    """Create and configure the aiohttp application."""
    if config is None:
        config = GatewayConfig.from_env()
    if not isinstance(config, GatewayConfig):
        raise ValueError("gateway_invalid_config")
    config.validate()

    @web.middleware
    async def safe_errors(request, handler):
        try:
            return await handler(request)
        except web.HTTPRequestEntityTooLarge:
            return web.json_response({"error": "body_too_large"}, status=413)
        except web.HTTPException:
            raise
        except (StorageUnavailable, OSError):
            return web.json_response({"error": "storage_unavailable"}, status=503)
        except Exception:
            # No framework traceback with request/job/process locals in responses.
            return web.json_response({"error": "gateway_unavailable"}, status=503)

    auth_middleware = create_auth_middleware(config.api_key)

    @web.middleware
    async def bounded_body(request, handler):
        if request.can_read_body:
            await request.read()
        return await handler(request)

    app = web.Application(
        middlewares=[safe_errors, auth_middleware, bounded_body],
        client_max_size=config.max_request_bytes,
    )

    job_manager = ImageJobManager(config)

    app[GATEWAY_CONFIG_KEY] = config
    app[JOB_MANAGER_KEY] = job_manager

    # Register lifecycle hooks
    async def on_startup(application: web.Application) -> None:
        await job_manager.start_workers()

    async def on_cleanup(application: web.Application) -> None:
        await job_manager.stop_workers()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # Routes
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/tags", handle_models)
    app.router.add_get("/v1/images/models", handle_models)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/v1/search", handle_search)
    app.router.add_post("/v1/images", handle_submit_image)
    app.router.add_get("/v1/images/{jobid}", handle_get_image_status)
    app.router.add_get("/v1/images/{jobid}/content", handle_get_image_content)

    return app
