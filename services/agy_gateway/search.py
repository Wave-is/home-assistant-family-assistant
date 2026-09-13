"""Web search endpoint backed by AGY CLI and search_web tool outputs."""

from __future__ import annotations

import ipaddress
import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

from .config import GATEWAY_CONFIG_KEY, GatewayConfig
from .events import tool_outputs
from .process import OutputLimitExceededError, ProcessExecutionError, run_agy_command

logger = logging.getLogger(__name__)


def is_public_url(url: str) -> bool:
    """Validate that a URL is a syntactically valid public http/https address."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.port not in {None, 80, 443}:
            return False
        if not parsed.hostname or "." not in parsed.hostname:
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname.endswith((".local", ".localhost", ".internal", ".home", ".lan")):
            return False
        # Check literal IP address
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_global
        except ValueError:
            # Hostname with dots (domain name)
            return True
    except Exception:
        return False


def _parse_tool_items(output_data: Any) -> list[dict[str, str]]:
    """Extract result dictionaries containing url, title, and snippet/content."""
    items: list[dict[str, str]] = []
    if isinstance(output_data, str):
        try:
            output_data = json.loads(output_data)
        except Exception:
            return items

    candidate_list: list[Any] = []
    if isinstance(output_data, list):
        candidate_list = output_data
    elif isinstance(output_data, dict):
        if isinstance(output_data.get("results"), list):
            candidate_list = output_data["results"]
        elif isinstance(output_data.get("items"), list):
            candidate_list = output_data["items"]
        else:
            candidate_list = [output_data]

    for item in candidate_list:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        title = item.get("title", "")
        if not isinstance(title, str):
            title = str(title)
        snippet = item.get("snippet", item.get("content", ""))
        if not isinstance(snippet, str):
            snippet = str(snippet)
        items.append(
            {
                "url": url.strip(),
                "title": title[:200],
                "snippet": snippet[:1200],
            }
        )
    return items


def extract_verified_search_results(stdout: str, limit: int) -> list[dict[str, str]]:
    """Parse tool outputs from stream-json; only proven tool output URLs are allowed."""
    verified, seen = [], set()
    for output in tool_outputs(stdout, "search_web"):
        for item in _parse_tool_items(output):
            if item["url"] not in seen and len(item["url"]) <= 512 and is_public_url(item["url"]):
                seen.add(item["url"])
                verified.append(item)
    return verified[:limit]


async def handle_search(request: web.Request) -> web.Response:
    """Handle POST /v1/search endpoint with evidence verification."""
    config: GatewayConfig = request.app.get(GATEWAY_CONFIG_KEY) or request.app["gateway_config"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json_body"}, status=400)

    if not isinstance(body, dict):
        return web.json_response({"error": "invalid_json_body"}, status=400)

    # Reject child safesearch = 2 as 501
    safesearch = body.get("safesearch")
    if safesearch == 2 or str(safesearch) == "2" or body.get("child") is True:
        return web.json_response({"error": "child_safesearch_unsupported"}, status=501)

    query = body.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        return web.json_response({"error": "invalid_field", "field": "query"}, status=400)
    query = query.strip()

    limit_val = body.get("limit", 5)
    try:
        limit = int(limit_val)
        if limit < 1 or limit > 5:
            return web.json_response({"error": "invalid_field", "field": "limit"}, status=400)
    except (ValueError, TypeError):
        return web.json_response({"error": "invalid_field", "field": "limit"}, status=400)

    model = body.get("model", config.models[0])
    if model not in config.models:
        return web.json_response({"error": "unsupported_model"}, status=400)

    args = [
        config.agy_bin,
        "--agent",
        "family-search",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--non-interactive",
    ]

    stdin_text = query

    with tempfile.TemporaryDirectory(prefix="agy_search_") as temp_dir:
        job_dir = Path(temp_dir)
        try:
            stdout = await run_agy_command(
                args,
                stdin_text=stdin_text,
                cwd=job_dir,
                timeout=30,
                max_output_bytes=config.max_output_bytes,
            )
        except TimeoutError:
            return web.json_response({"error": "provider_timeout"}, status=504)
        except OutputLimitExceededError:
            return web.json_response({"error": "output_limit_exceeded"}, status=500)
        except ProcessExecutionError:
            return web.json_response({"error": "provider_bad_response"}, status=502)

    results = extract_verified_search_results(stdout, limit=limit)
    return web.json_response({"results": results})
