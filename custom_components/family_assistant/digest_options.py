"""Named owner review of the global digest policy, with exact in-process retry."""

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant.util import dt as dt_util

from .domain import digest_settings as policy
from .domain.validation import DomainError


def _scope(flow):
    runtime, actor = flow._authorized_runtime()
    state = runtime.engine.snapshot()
    return {
        "runtime": runtime,
        "actor": actor,
        "revision": state["members"][actor]["revision"],
        "fingerprint": policy.fingerprint(state),
        "values": policy.values(state),
        "timezone": state["settings"]["timezone"],
        "language": state["members"][actor]["language"],
        "state": state,
    }


def _identity(left, right):
    return (
        left["runtime"] is right["runtime"]
        and left["actor"] == right["actor"]
        and left["revision"] == right["revision"]
    )


def _review_current(scope, review):
    if not _identity(scope, review["scope"]):
        return False
    if scope["fingerprint"] == review["payload"]["policy_fingerprint"]:
        return True
    # A committed response may have been lost. Only that exact current receipt
    # permits reviewing/retrying the frozen request; Engine validates its hash.
    prior = scope["state"]["processed"].get(review["operation_id"], {})
    return prior.get("result") == {"policy_fingerprint": scope["fingerprint"]}


def _schema(values):
    return vol.Schema(
        {
            vol.Required(key, default=value): (
                bool if key.endswith("_enabled") else int if key.endswith("_weekday") else str
            )
            for key, value in values.items()
        }
    )


async def policy_step(flow, user_input=None):
    try:
        current = _scope(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        old = getattr(flow, "_digest_displayed", None)
        if (
            old is None
            or not _identity(current, old)
            or current["fingerprint"] != old["fingerprint"]
        ):
            errors["base"] = "conflict"
        else:
            try:
                if not isinstance(user_input, dict) or set(user_input) != set(policy.DEFAULTS):
                    raise DomainError("invalid_field")
                supplied = policy.validate(user_input)
                if supplied == current["values"]:
                    raise DomainError("invalid_transition")
                flow._digest_review = {
                    "scope": current,
                    "payload": {
                        "actor_revision": current["revision"],
                        "policy_fingerprint": current["fingerprint"],
                        **supplied,
                    },
                    "operation_id": "digest-policy:" + uuid4().hex,
                }
                return await review_step(flow)
            except DomainError as error:
                errors["base"] = error.code
    flow._digest_displayed = current
    return flow.async_show_form(
        step_id="digests", data_schema=_schema(current["values"]), errors=errors
    )


async def review_step(flow, user_input=None):
    review = getattr(flow, "_digest_review", None)
    if not isinstance(review, dict):
        return await policy_step(flow)
    try:
        current = _scope(flow)
        if not _review_current(current, review):
            raise DomainError("conflict")
    except DomainError as error:
        flow._digest_review = None
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        if (
            not isinstance(user_input, dict)
            or set(user_input) != {"confirmed"}
            or type(user_input["confirmed"]) is not bool
        ):
            errors["base"] = "invalid_field"
        elif not user_input["confirmed"]:
            flow._digest_review = None
            return await policy_step(flow)
        else:
            try:
                await current["runtime"].engine.execute(
                    current["actor"],
                    "settings.digest_policy",
                    deepcopy(review["payload"]),
                    review["operation_id"],
                    dt_util.utcnow(),
                )
                after = _scope(flow)
                if not _review_current(after, review):
                    raise DomainError("conflict")
                current["runtime"].updated()
                result = flow.async_create_entry(title="", data=dict(flow.config_entry.options))
                if result.get("type") != "abort":
                    flow._digest_review = None
                return result
            except DomainError as error:
                flow._digest_review = None
                return flow.async_abort(reason=error.code)
            except OSError:
                errors["base"] = "storage_error"
    language = current["language"]
    on, off = {"ru": ("включён", "выключен"), "uk": ("увімкнено", "вимкнено")}.get(
        language, ("enabled", "disabled")
    )
    selected = review["payload"]
    return flow.async_show_form(
        step_id="digest_policy_review",
        data_schema=vol.Schema({vol.Required("confirmed", default=False): bool}),
        errors=errors,
        description_placeholders={
            "timezone": review["scope"]["timezone"],
            "morning": on if selected["digest_morning_enabled"] else off,
            "morning_time": selected["digest_morning_time"],
            "evening": on if selected["digest_evening_enabled"] else off,
            "evening_time": selected["digest_evening_time"],
            "weekly": on if selected["digest_weekly_enabled"] else off,
            "weekly_time": selected["digest_weekly_time"],
            "weekly_weekday": str(selected["digest_weekly_weekday"]),
        },
    )
