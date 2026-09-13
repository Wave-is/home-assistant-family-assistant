"""Allowlisted HA facts; a report timestamp is not a physical measurement time."""

from datetime import datetime
from math import isfinite

from .config import STATES

UNITS = frozenset(
    {"%", "W", "kW", "Wh", "kWh", "V", "A", "°C", "°F", "hPa", "bar", "lx", "ppm", "Hz"}
)


def normalize(source, observed, now, max_age):
    result = {
        "id": source["id"],
        "label": source["label"],
        "metric": source["metric"],
        "value": None,
        "unit": None,
        "reported_state": None,
        "active": None,
        "quality": "missing",
        "ha_reported_at": None,
        "freshness_basis": None,
        "report_age_seconds": None,
    }
    if observed is None:
        return result
    attrs = getattr(observed, "attributes", {})
    if not hasattr(attrs, "get"):
        return {**result, "quality": "invalid_metadata"}
    if attrs.get("restored", False) is not False:
        return {**result, "quality": "restored"}
    basis = "last_reported" if hasattr(observed, "last_reported") else "last_updated"
    reported = getattr(observed, basis, None)
    if (
        not isinstance(reported, datetime)
        or reported.tzinfo is None
        or reported.utcoffset() is None
    ):
        return {**result, "quality": "missing_timestamp"}
    age = (now - reported).total_seconds()
    if age < 0:
        return {**result, "quality": "future_timestamp"}
    result.update(
        ha_reported_at=reported.isoformat(), freshness_basis=basis, report_age_seconds=age
    )
    if age > max_age:
        return {**result, "quality": "stale"}
    state = getattr(observed, "state", None)
    if state in ("unknown", "unavailable"):
        return {**result, "quality": state}
    domain = source["entity_id"].split(".", 1)[0]
    if domain in STATES:
        if not isinstance(state, str) or state not in STATES[domain]:
            return {**result, "quality": "invalid_state"}
        result.update(quality="ok", reported_state=state)
        if source["section"] == "active":
            result["active"] = state in source["active_states"]
        return result
    unit = attrs.get("unit_of_measurement")
    if not isinstance(unit, str) or unit not in UNITS:
        return {**result, "quality": "invalid_unit"}
    metric = source["metric"]
    if metric == "battery_soc":
        if unit != "%" or attrs.get("device_class") not in (None, "battery"):
            return {**result, "quality": "invalid_unit"}
    elif metric is not None:
        if unit not in {"W", "kW"} or attrs.get("device_class") not in (None, "power"):
            return {**result, "quality": "invalid_unit"}
    try:
        if not isinstance(state, str) or len(state) > 60:
            raise ValueError
        value = float(state)
        if not isfinite(value) or (metric == "battery_soc" and not 0 <= value <= 100):
            raise ValueError
        if metric is not None and unit == "kW":
            value, unit = value * 1000, "W"
        if not isfinite(value) or abs(value) > 1e15:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        return {**result, "quality": "invalid_value"}
    return {**result, "quality": "ok", "value": value, "unit": unit}
