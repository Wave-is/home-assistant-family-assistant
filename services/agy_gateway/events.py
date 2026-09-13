"""The documented CLI stream-json protocol; no invented OpenAI envelopes."""

import json


def events(stdout):
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            yield value


def result(stdout):
    terminal = [value.get("result") for value in events(stdout) if value.get("event") == "result"]
    return terminal[-1] if terminal and isinstance(terminal[-1], dict) else {}


def tool_outputs(stdout, name):
    for value in events(stdout):
        step = value.get("step_update", {})
        if (
            value.get("event") == "step_update"
            and step.get("state") == "DONE"
            and step.get("step_type") == "tool"
            and step.get("tool_name") == name
            and isinstance(step.get("tool_info"), dict)
            and not step["tool_info"].get("error")
        ):
            yield step["tool_info"].get("output")


def error_code(stdout):
    value = result(stdout)
    if value.get("status") == "SUCCESS":
        return None
    # Classification only. Never expose provider error contents to callers/logs.
    error = json.dumps(value.get("error", "")).lower()
    if any(word in error for word in ("quota", "resource_exhausted", "rate limit", "429")):
        return "quota_exceeded"
    if any(word in error for word in ("authentication", "not_authenticated", "unauthorized")):
        return "not_authenticated"
    return "provider_bad_response"
