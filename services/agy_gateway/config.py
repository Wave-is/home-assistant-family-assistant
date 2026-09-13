"""Configuration for standalone optional AGY CLI gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import web


@dataclass(frozen=True)
class GatewayConfig:
    """Gateway configuration settings loaded from environment."""

    api_key: str = field(repr=False)
    models: tuple[str, ...] = ("gemini-3.8-flash-low",)
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("AGY_DATA_DIR", "./data")).resolve()
    )
    agy_bin: str = "agy"
    host: str = "127.0.0.1"
    port: int = 8080
    max_output_bytes: int = 8 * 1024 * 1024  # 8 MB
    max_image_bytes: int = 6_000_000
    max_chat_timeout: int = 60  # seconds
    worker_concurrency: int = 2
    queue_max_size: int = 16
    max_jobs: int = 10_000
    max_retained_jobs: int = 64
    max_request_bytes: int = 262_144

    def validate(self):
        if (
            not isinstance(self.api_key, str)
            or not self.api_key.strip()
            or len(self.api_key) > 2048
            or any(ord(c) < 32 or ord(c) == 127 for c in self.api_key)
        ):
            raise ValueError("gateway_api_key_required")
        if (
            not isinstance(self.models, tuple)
            or not 1 <= len(self.models) <= 32
            or any(
                not isinstance(model, str)
                or not model.strip()
                or len(model) > 128
                or any(ord(c) < 32 for c in model)
                for model in self.models
            )
            or len(set(self.models)) != len(self.models)
        ):
            raise ValueError("gateway_invalid_models")
        for value, lower, upper in (
            (self.port, 1, 65535),
            (self.max_output_bytes, 1024, 8 * 1024 * 1024),
            (self.max_image_bytes, 1024, 6_000_000),
            (self.max_chat_timeout, 5, 120),
            (self.worker_concurrency, 1, 4),
            (self.queue_max_size, 1, 32),
            (self.max_jobs, 1, 10000),
            (self.max_retained_jobs, 1, 64),
            (self.max_request_bytes, 1024, 1_048_576),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("gateway_invalid_limit")
        if (
            not isinstance(self.data_dir, Path)
            or not self.data_dir.is_absolute()
            or self.data_dir == Path(self.data_dir.anchor)
        ):
            raise ValueError("gateway_invalid_directory")
        if (
            not isinstance(self.agy_bin, str)
            or not self.agy_bin.strip()
            or any(ord(c) < 32 for c in self.agy_bin)
        ):
            raise ValueError("gateway_invalid_executable")

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Construct configuration from environment variables."""
        api_key = os.environ.get("AGY_API_KEY", "").strip()
        models_raw = os.environ.get("AGY_MODELS", "gemini-3.8-flash-low").strip()
        models = tuple(m.strip() for m in models_raw.split(",") if m.strip())
        if not models:
            models = ("gemini-3.8-flash-low",)

        data_dir_str = os.environ.get("AGY_DATA_DIR", "./data").strip()
        data_dir = Path(data_dir_str).resolve()

        agy_bin = os.environ.get("AGY_BIN", "agy").strip() or "agy"
        host = (
            os.environ.get("HOST", os.environ.get("AGY_HOST", "127.0.0.1")).strip() or "127.0.0.1"
        )
        try:
            port = int(os.environ.get("PORT", os.environ.get("AGY_PORT", "8080")).strip())
        except ValueError:
            port = 8080

        return cls(
            api_key=api_key,
            models=models,
            data_dir=data_dir,
            agy_bin=agy_bin,
            host=host,
            port=port,
        )


GATEWAY_CONFIG_KEY: web.AppKey[GatewayConfig] = web.AppKey("gateway_config", GatewayConfig)
