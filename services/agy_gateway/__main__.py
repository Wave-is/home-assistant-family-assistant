"""Command-line entrypoint for running the AGY CLI gateway service."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from aiohttp import web

from .config import GatewayConfig
from .process import install_service_policy
from .server import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("agy_gateway")

    config = GatewayConfig.from_env()
    if not config.api_key:
        logger.error("Environment variable AGY_API_KEY is required but not set.")
        sys.exit(1)

    logger.info(
        "Starting AGY CLI Gateway on %s:%d with models=%s",
        config.host,
        config.port,
        list(config.models),
    )

    install_service_policy(Path.home())
    app = create_app(config)
    web.run_app(app, host=config.host, port=config.port, access_log=None)


if __name__ == "__main__":
    main()
