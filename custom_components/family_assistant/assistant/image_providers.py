"""Explicit optional image transports; a text response is never an image.

ComfyUI follows its local server /prompt, /history and /view contract. The
separately installed AGY gateway implements our versioned asynchronous protocol.
Neither adapter executes a developer-PC command or accepts output URLs.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from copy import deepcopy
from uuid import UUID

import aiohttp

from ..domain.validation import DomainError, fields, text
from .http import endpoint

MAX_BYTES = 6_000_000
MIMES = {"image/png", "image/jpeg", "image/webp"}


class ImageError(DomainError):
    def __init__(self, code, *, uncertain=False, fallback=False):
        super().__init__(code)
        self.uncertain, self.fallback = uncertain, fallback


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise DomainError("invalid_field")
    return value


def normalize_provider(value):
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "providers")
    fields(
        value,
        {
            "id",
            "type",
            "name",
            "enabled",
            "url",
            "allow_http",
            "api_key",
            "model",
            "timeout",
            "workflow",
            "encoder",
            "vae",
        },
        {"id", "type"},
    )
    row = {
        "enabled": True,
        "name": "",
        "url": "",
        "allow_http": False,
        "api_key": "",
        "model": "",
        "timeout": 30,
        "workflow": "checkpoint",
        "encoder": "",
        "vae": "",
        **deepcopy(value),
    }
    if not isinstance(row["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", row["id"]):
        raise DomainError("invalid_field", "id")
    if row["type"] not in {"agy_gateway", "comfyui"}:
        raise DomainError("invalid_field", "type")
    for key in ("enabled", "allow_http"):
        if type(row[key]) is not bool:
            raise DomainError("invalid_field", key)
    for key, limit in (
        ("name", 80),
        ("model", 256),
        ("api_key", 2000),
        ("encoder", 256),
        ("vae", 256),
    ):
        if (
            not isinstance(row[key], str)
            or len(row[key]) > limit
            or any(ord(c) < 32 for c in row[key])
        ):
            raise DomainError("invalid_field", key)
        row[key] = row[key].strip()
    row["timeout"] = _integer(row["timeout"], 5, 60)
    if row["url"] or row["enabled"]:
        row["url"] = endpoint(row["url"], allow_http=row["allow_http"])
    if row["enabled"] and not row["model"]:
        raise DomainError("invalid_field", "model")
    if row["workflow"] not in {"checkpoint", "z_image_turbo"}:
        raise DomainError("invalid_field", "workflow")
    if (
        row["enabled"]
        and row["type"] == "comfyui"
        and row["workflow"] == "z_image_turbo"
        and (not row["encoder"] or not row["vae"])
    ):
        raise DomainError("invalid_field", "encoder")
    return row


def normalize_config(value):
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "image_generation")
    fields(
        value, {"enabled", "providers", "width", "height", "steps", "cfg", "negative_prompt"}, set()
    )
    result = {
        "enabled": False,
        "providers": [],
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg": 7,
        "negative_prompt": "",
        **deepcopy(value),
    }
    if (
        type(result["enabled"]) is not bool
        or not isinstance(result["providers"], list)
        or len(result["providers"]) > 8
    ):
        raise DomainError("invalid_field")
    result["providers"] = [normalize_provider(row) for row in result["providers"]]
    if len({row["id"] for row in result["providers"]}) != len(result["providers"]):
        raise DomainError("invalid_field", "id")
    for key in ("width", "height"):
        if type(result[key]) is not int or result[key] not in {512, 768, 1024}:
            raise DomainError("invalid_field", key)
    result["steps"] = _integer(result["steps"], 1, 50)
    if (
        type(result["cfg"]) not in {int, float}
        or not math.isfinite(result["cfg"])
        or not 1 <= result["cfg"] <= 20
    ):
        raise DomainError("invalid_field", "cfg")
    if not isinstance(result["negative_prompt"], str) or len(result["negative_prompt"]) > 2000:
        raise DomainError("invalid_field", "negative_prompt")
    if result["enabled"] and not any(row["enabled"] for row in result["providers"]):
        raise DomainError("provider_not_configured")
    return result


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ImageError("provider_bad_response") from None
    return value


def workflow(prompt, request_id, config, model):
    """Fixed local txt2img nodes only: never remote API/custom workflow nodes."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": config["cfg"],
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": UUID(request_id).int % (2**63),
                "steps": config["steps"],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": config["height"], "width": config["width"]},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": prompt}},
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": config["negative_prompt"]},
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "family_assistant_" + request_id, "images": ["8", 0]},
        },
    }


def z_image_workflow(prompt, request_id, config, provider):
    graph = workflow(prompt, request_id, config, provider["model"])
    graph["4"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": provider["model"], "weight_dtype": "default"},
    }
    graph["10"] = {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": provider["encoder"], "type": "lumina2", "device": "default"},
    }
    graph["11"] = {"class_type": "VAELoader", "inputs": {"vae_name": provider["vae"]}}
    graph["12"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["4", 0], "shift": 3}}
    graph["5"]["class_type"] = "EmptySD3LatentImage"
    graph["6"]["inputs"]["clip"] = ["10", 0]
    graph["7"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}
    graph["8"]["inputs"]["vae"] = ["11", 0]
    graph["3"]["inputs"].update(model=["12", 0], sampler_name="res_multistep", scheduler="simple")
    return graph


class ImageProvider:
    def __init__(self, session, config):
        self.session, self.config = session, normalize_provider(config)

    def __repr__(self):
        return "ImageProvider(<redacted>)"

    async def _request(self, method, path, *, binary=False, **kwargs):
        headers = (
            {"Authorization": "Bearer " + self.config["api_key"]} if self.config["api_key"] else {}
        )
        submitted = method == "POST"
        try:
            async with self.session.request(
                method,
                self.config["url"] + path,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=self.config["timeout"], connect=5),
                **kwargs,
            ) as response:
                if response.status in {401, 403}:
                    raise ImageError("provider_authentication")
                if response.status == 429:
                    raise ImageError("provider_quota_exceeded", fallback=submitted)
                if response.status == 400:
                    raise ImageError("image_rejected")
                if not 200 <= response.status < 300:
                    raise ImageError("provider_unreachable", uncertain=submitted)
                limit = MAX_BYTES if binary else 262144
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > limit:
                        raise ImageError(
                            "image_too_large" if binary else "provider_bad_response",
                            uncertain=submitted,
                        )
                    chunks.append(chunk)
                body = b"".join(chunks)
                if binary:
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if mime not in MIMES or not body:
                        raise ImageError("image_invalid")
                    return body, mime
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except ImageError:
            raise
        except aiohttp.ClientConnectorError:
            raise ImageError("provider_unreachable", fallback=submitted) from None
        except (aiohttp.ClientError, TimeoutError, OSError):
            raise ImageError("provider_timeout", uncertain=submitted) from None
        except (ValueError, UnicodeError, RecursionError):
            raise ImageError("provider_bad_response", uncertain=submitted) from None
        except asyncio.CancelledError:
            raise

    async def inspect(self):
        extra = {}
        if self.config["type"] == "agy_gateway":
            value = await self._request("GET", "/v1/images/models")
            models = value.get("models")
        else:
            node, field = (
                ("UNETLoader", "unet_name")
                if self.config["workflow"] == "z_image_turbo"
                else ("CheckpointLoaderSimple", "ckpt_name")
            )
            value = await self._request("GET", "/object_info/" + node)
            try:
                models = value[node]["input"]["required"][field][0]
                if self.config["workflow"] == "z_image_turbo":
                    for key, node, field in (
                        ("encoders", "CLIPLoader", "clip_name"),
                        ("vaes", "VAELoader", "vae_name"),
                    ):
                        value = await self._request("GET", "/object_info/" + node)
                        extra[key] = value[node]["input"]["required"][field][0]
            except (KeyError, TypeError, IndexError):
                models = None
        for items in (models, *extra.values()):
            if (
                not isinstance(items, list)
                or len(items) > 1000
                or any(not isinstance(model, str) or not 1 <= len(model) <= 256 for model in items)
            ):
                raise ImageError("provider_bad_response")
        return {"available": True, "models": models, **extra}

    async def submit(self, prompt, request_id, config):
        _uuid(request_id)
        prompt = text(prompt, "prompt", 2000)
        if self.config["type"] == "agy_gateway":
            value = await self._request(
                "POST",
                "/v1/images",
                json={
                    "request_id": request_id,
                    "prompt": prompt,
                    "model": self.config["model"],
                    "width": config["width"],
                    "height": config["height"],
                },
            )
            if value.get("job_id") != request_id:
                raise ImageError("provider_bad_response", uncertain=True)
            return request_id
        value = await self._request(
            "POST",
            "/prompt",
            json={
                "prompt": z_image_workflow(prompt, request_id, config, self.config)
                if self.config["workflow"] == "z_image_turbo"
                else workflow(prompt, request_id, config, self.config["model"]),
                "client_id": request_id,
            },
        )
        try:
            return _uuid(value.get("prompt_id"))
        except ImageError:
            raise ImageError("provider_bad_response", uncertain=True) from None

    async def poll(self, job_id):
        _uuid(job_id)
        if self.config["type"] == "agy_gateway":
            value = await self._request("GET", "/v1/images/" + job_id)
            if value.get("job_id") != job_id or value.get("status") not in {
                "queued",
                "running",
                "succeeded",
                "failed",
                "uncertain",
            }:
                raise ImageError("provider_bad_response")
            if value["status"] == "uncertain":
                raise ImageError("image_submission_uncertain", uncertain=True)
            if value["status"] == "failed":
                code = (
                    value.get("error", {}).get("code")
                    if isinstance(value.get("error"), dict)
                    else None
                )
                raise ImageError(
                    "provider_quota_exceeded" if code == "quota_exceeded" else "image_rejected",
                    fallback=code in {"quota_exceeded", "unavailable"},
                )
            return {} if value["status"] == "succeeded" else None
        value = await self._request("GET", "/history/" + job_id)
        if job_id not in value:
            return None
        row = value[job_id]
        if not isinstance(row, dict) or not isinstance(row.get("status"), dict):
            raise ImageError("provider_bad_response")
        if row["status"].get("status_str") == "error":
            raise ImageError("image_rejected")
        if row["status"].get("completed") is not True:
            return None
        try:
            images = row["outputs"]["9"]["images"]
            if not isinstance(images, list) or len(images) != 1:
                raise ValueError
            output = images[0]
            filename, subfolder = output["filename"], output.get("subfolder", "")
            if (
                output.get("type") != "output"
                or not isinstance(filename, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", filename)
                or filename in {".", ".."}
                or not isinstance(subfolder, str)
                or len(subfolder) > 200
                or any(
                    not re.fullmatch(r"[A-Za-z0-9_-]+", part)
                    for part in subfolder.split("/")
                    if subfolder
                )
            ):
                raise ValueError
            return {"filename": filename, "subfolder": subfolder, "type": "output"}
        except (KeyError, TypeError, ValueError, IndexError):
            raise ImageError("provider_bad_response") from None

    async def content(self, job_id, output):
        _uuid(job_id)
        if self.config["type"] == "agy_gateway":
            return await self._request("GET", "/v1/images/" + job_id + "/content", binary=True)
        return await self._request("GET", "/view", params=output, binary=True)
