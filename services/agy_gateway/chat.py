"""Ollama-compatible /api/chat endpoint backed by AGY CLI."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from aiohttp import web
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .config import GATEWAY_CONFIG_KEY, GatewayConfig
from .events import error_code, result
from .process import OutputLimitExceededError, ProcessExecutionError, run_agy_command

logger = logging.getLogger(__name__)


def extract_stream_json_content(stdout: str) -> str:
    """Extract model response text from AGY stream-json lines."""
    terminal = result(stdout)
    if terminal:
        if terminal.get("status") != "SUCCESS":
            return ""
        structured = terminal.get("structured_output")
        return (
            json.dumps(structured, ensure_ascii=False)
            if isinstance(structured, dict)
            else terminal.get("response", "")
        )
    return ""


async def handle_chat(request: web.Request) -> web.Response:
    """Handle POST /api/chat with Ollama format and AGY CLI execution."""
    config: GatewayConfig = request.app.get(GATEWAY_CONFIG_KEY) or request.app["gateway_config"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json_body"}, status=400)

    if not isinstance(body, dict):
        return web.json_response({"error": "invalid_json_body"}, status=400)

    # Validate model
    model = body.get("model", config.models[0])
    if model not in config.models:
        return web.json_response({"error": "unsupported_model"}, status=400)

    # Validate messages
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return web.json_response({"error": "invalid_field", "field": "messages"}, status=400)

    # Extract options & bounded timeout
    options = body.get("options", {})
    requested_timeout = 60
    if isinstance(options, dict):
        val = options.get("timeout")
        if isinstance(val, (int, float)) and val > 0:
            requested_timeout = int(val)
    timeout = min(config.max_chat_timeout, max(5, requested_timeout))

    # The CLI's --json-schema can start extra turns and repeat JSON on current
    # versions. Pass the schema as instructions, independently validate here.
    schema_arg = body.get("format")
    if schema_arg is not None:
        if not isinstance(schema_arg, dict):
            return web.json_response({"error": "invalid_schema"}, status=400)
        try:
            pending = [(schema_arg, 0)]
            count = 0
            while pending:
                node, depth = pending.pop()
                count += 1
                if count > 10000 or depth > 32:
                    raise ValueError
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                            not isinstance(value, str) or not value.startswith("#")
                        ):
                            raise ValueError
                        pending.append((value, depth + 1))
                elif isinstance(node, list):
                    pending.extend((value, depth + 1) for value in node)
            Draft202012Validator.check_schema(schema_arg)
        except (SchemaError, ValueError, RecursionError):
            return web.json_response({"error": "invalid_schema"}, status=400)

    # Format stdin prompt text without logging sensitive contents
    prompt_lines: list[str] = []
    if schema_arg is not None:
        prompt_lines.append(
            "Return exactly one JSON object, without Markdown or prose, matching this JSON schema: "
            + json.dumps(schema_arg, ensure_ascii=False)
        )
    for msg in messages:
        if (
            not isinstance(msg, dict)
            or msg.get("role") not in {"user", "assistant", "system"}
            or not isinstance(msg.get("content"), str)
        ):
            return web.json_response({"error": "invalid_messages"}, status=400)
        if msg.get("images"):
            return web.json_response({"error": "vision_unsupported"}, status=501)
        prompt_lines.append(f"{msg['role'].capitalize()}: {msg['content']}")
    stdin_text = "\n\n".join(prompt_lines)

    # Command arguments for noninteractive stream-json execution
    args = [
        config.agy_bin,
        "--agent",
        "family-text",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--non-interactive",
    ]

    # Execute in temporary isolated job directory
    with tempfile.TemporaryDirectory(prefix="agy_chat_") as temp_dir:
        job_dir = Path(temp_dir)
        try:
            stdout = await run_agy_command(
                args,
                stdin_text=stdin_text,
                cwd=job_dir,
                timeout=timeout,
                max_output_bytes=config.max_output_bytes,
            )
        except TimeoutError:
            return web.json_response({"error": "timeout"}, status=504)
        except OutputLimitExceededError:
            return web.json_response({"error": "output_limit_exceeded"}, status=500)
        except ProcessExecutionError as error:
            code = error.code or "provider_bad_response"
            return web.json_response(
                {"error": code},
                status={"quota_exceeded": 429, "not_authenticated": 401}.get(code, 502),
            )

    code = error_code(stdout)
    if code:
        return web.json_response(
            {"error": code}, status={"quota_exceeded": 429, "not_authenticated": 401}.get(code, 502)
        )
    content_str = extract_stream_json_content(stdout)
    if not isinstance(content_str, str) or not content_str or len(content_str) > 20000:
        return web.json_response({"error": "provider_bad_response"}, status=502)
    if schema_arg is not None:
        try:
            value = json.loads(content_str)
            if not isinstance(value, dict):
                raise ValueError
            Draft202012Validator(schema_arg).validate(value)
        except (ValueError, ValidationError, RecursionError):
            return web.json_response({"error": "provider_bad_response"}, status=502)

    return web.json_response(
        {
            "model": model,
            "message": {
                "role": "assistant",
                "content": content_str,
            },
            "done": True,
        }
    )
